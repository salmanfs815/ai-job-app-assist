resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location

  lifecycle {
    prevent_destroy = true
  }
}

module "cosmos" {
  source = "./modules/cosmos"

  resource_group_name   = azurerm_resource_group.main.name
  location              = azurerm_resource_group.main.location
  account_name          = var.cosmos_account_name
  database_name         = var.cosmos_database_name
  create_app_containers = var.enable_phase1
}

# Salt for hashing guest IP addresses before they are stored (see ADR 0003).
resource "random_password" "ip_hash_salt" {
  count = var.enable_phase1 ? 1 : 0

  length  = 48
  special = false
}

locals {
  entra_configured = var.entra_tenant_id != "" && var.entra_tenant_subdomain != "" && var.entra_api_client_id != ""

  # Matches the live Container App exactly (including order) so the first apply is a no-op.
  base_env = [
    { name = "PERSISTENCE_ENABLED", value = "true" },
    { name = "COSMOS_ENDPOINT", value = module.cosmos.endpoint },
    { name = "COSMOS_DATABASE_NAME", value = module.cosmos.database_name },
    { name = "COSMOS_CONTAINER_NAME", value = module.cosmos.container_names.results },
    { name = "OPENAI_MODEL", value = var.openai_model },
    { name = "MAX_UPLOAD_BYTES", value = "5242880" },
    { name = "ENABLE_PDF_OCR_FALLBACK", value = "true" },
    { name = "FRONTEND_ORIGIN", value = var.frontend_origin },
    { name = "COSMOS_KEY", secret_name = "cosmos-key" },
    { name = "OPENAI_API_KEY", secret_name = "openai-api-key" },
  ]

  # Settings added by Phase 1. Empty during the import-only first apply.
  phase1_env = var.enable_phase1 ? concat(
    [
      { name = "ENVIRONMENT", value = "production" },
      { name = "AUTH_MODE", value = "entra" },
      { name = "GUEST_MODE_ENABLED", value = "true" },
      { name = "TRUSTED_PROXY_HOPS", value = "1" },
      { name = "IP_HASH_SALT", secret_name = "ip-hash-salt" },
      { name = "USER_DAILY_GENERATION_LIMIT", value = tostring(var.user_daily_generation_limit) },
      { name = "GUEST_DAILY_GENERATION_LIMIT", value = tostring(var.guest_daily_generation_limit) },
      { name = "GLOBAL_DAILY_LLM_BUDGET_USD", value = tostring(var.global_daily_llm_budget_usd) },
      { name = "COSMOS_USERS_CONTAINER_NAME", value = module.cosmos.container_names.users },
      { name = "COSMOS_RESUMES_CONTAINER_NAME", value = module.cosmos.container_names.resumes },
      { name = "COSMOS_USAGE_CONTAINER_NAME", value = module.cosmos.container_names.usage },
    ],
    local.entra_configured ? [
      { name = "ENTRA_TENANT_ID", value = var.entra_tenant_id },
      { name = "ENTRA_TENANT_SUBDOMAIN", value = var.entra_tenant_subdomain },
      { name = "ENTRA_API_CLIENT_ID", value = var.entra_api_client_id },
    ] : [],
  ) : []

  secrets = merge(
    {
      "cosmos-key"     = module.cosmos.primary_key
      "openai-api-key" = var.openai_api_key
    },
    var.enable_phase1 ? { "ip-hash-salt" = random_password.ip_hash_salt[0].result } : {},
  )
}

module "backend" {
  source = "./modules/backend"

  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  environment_name    = var.container_app_environment_name
  app_name            = var.backend_app_name
  image               = var.backend_image
  max_replicas        = var.enable_phase1 ? 1 : 2
  env                 = concat(local.base_env, local.phase1_env)
  secrets             = local.secrets
}

module "frontend" {
  source = "./modules/frontend"

  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  name                = var.static_web_app_name
}
