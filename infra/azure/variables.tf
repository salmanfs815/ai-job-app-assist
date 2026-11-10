# Defaults match the live resources that were created by hand and are adopted with `import`
# blocks (see imports.tf). Changing a name here would make Terraform plan a replacement,
# which `prevent_destroy` on the stateful resources blocks.

variable "subscription_id" {
  description = "Azure subscription ID. Supplied by CI as TF_VAR_subscription_id."
  type        = string
}

variable "location" {
  description = "Azure region of the existing resources."
  type        = string
  default     = "westus2"
}

variable "resource_group_name" {
  type    = string
  default = "rg-job-assist"
}

variable "cosmos_account_name" {
  type    = string
  default = "jobassist-cosmos-prod"
}

variable "cosmos_database_name" {
  type    = string
  default = "jobassist"
}

variable "container_app_environment_name" {
  type    = string
  default = "cae-ai-job-assist"
}

variable "backend_app_name" {
  type    = string
  default = "ai-job-assist-backend"
}

variable "static_web_app_name" {
  type    = string
  default = "ai-job-assist-frontend"
}

variable "backend_image" {
  description = <<-EOT
    Image used only when Terraform creates the Container App. After that the backend workflow
    owns the running image (Terraform ignores it), so this never rolls back a deployment.
  EOT
  type        = string
  default     = "ghcr.io/salmanfs815/ai-job-assist-backend:latest"
}

variable "frontend_origin" {
  description = "Browser origin allowed by the API's CORS policy."
  type        = string
  default     = "https://agreeable-field-0639e271e.7.azurestaticapps.net"
}

variable "openai_api_key" {
  description = "OpenAI API key, stored as a Container Apps secret. Empty = mock mode."
  type        = string
  sensitive   = true
}

variable "openai_model" {
  type    = string
  default = "gpt-4.1-mini"
}

# --- Phase 1 rollout ------------------------------------------------------------------------
#
# The first apply must only adopt existing resources. Everything Phase 1 adds or changes is
# behind this switch so it lands in a second, separately reviewed plan:
#   * new Cosmos containers: users, resumes, usage
#   * API settings for auth, limits and guest mode, plus the IP-hash salt secret
#   * maxReplicas 2 -> 1 (the in-memory rate limiter assumes a single replica)

variable "enable_phase1" {
  description = "Create the Phase 1 containers and API settings. Keep false for the import-only first apply."
  type        = bool
  default     = false
}

variable "entra_tenant_id" {
  description = "External ID tenant ID (output of infra/entra). Empty keeps sign-in off; guests still work."
  type        = string
  default     = ""
}

variable "entra_tenant_subdomain" {
  description = "External ID tenant subdomain, e.g. 'jobassist' for jobassist.ciamlogin.com."
  type        = string
  default     = ""
}

variable "entra_api_client_id" {
  description = "Client ID of the API app registration (output of infra/entra)."
  type        = string
  default     = ""
}

variable "entra_api_app_id_uri" {
  description = "App ID URI of the API registration, published as an output for the watcher repo."
  type        = string
  default     = ""
}

variable "user_daily_generation_limit" {
  type    = number
  default = 20
}

variable "guest_daily_generation_limit" {
  type    = number
  default = 3
}

variable "global_daily_llm_budget_usd" {
  type    = number
  default = 1.0
}
