# App registrations in the Microsoft Entra External ID tenant.
#
# This root is applied by the owner from a workstation, signed in to the external tenant
# with the Azure CLI (`az login --tenant <tenant> --allow-no-subscriptions`). It is
# deliberately not applied from CI: a CI identity in an external tenant would authenticate
# with client credentials, which External ID bills as the paid "M2M Authentication" add-on,
# and it would need standing directory permissions. See docs/setup/entra-external-id.md.
#
# The external tenant itself, the sign-up/sign-in user flow and linking the SPA to that flow
# are created in the Entra admin center (the azuread provider does not manage them).

terraform {
  required_version = ">= 1.14.0"

  required_providers {
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.10"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9"
    }
  }

  # Small, rarely changed state with no secrets (no client secrets are created here).
  # Keep it in HCP Terraform under a separate workspace; see the setup guide.
  cloud {}
}

provider "azuread" {
  tenant_id = var.tenant_id
}

variable "tenant_id" {
  description = "External ID tenant ID."
  type        = string
}

variable "spa_redirect_origins" {
  description = "Origins that serve the frontend. The redirect URI is <origin>/redirect.html."
  type        = list(string)
  default = [
    "https://agreeable-field-0639e271e.7.azurestaticapps.net",
    "http://localhost:5173",
    "http://localhost:3000",
  ]
}

variable "admin_object_ids" {
  description = "Object IDs of users (in the external tenant) who get the Admin app role."
  type        = list(string)
  default     = []
}

variable "create_watcher_app" {
  description = <<-EOT
    Create a confidential client for the job-posting watcher (client-credentials flow).
    Off by default: client credentials in External ID tenants are a paid add-on, so the
    watcher authenticates with HMAC request signing instead (ADR 0006).
  EOT
  type        = bool
  default     = false
}

data "azuread_client_config" "current" {}

resource "random_uuid" "scope_access_as_user" {}
resource "random_uuid" "role_admin" {}
resource "random_uuid" "role_postings_ingest" {}

# --- API -----------------------------------------------------------------------------------

resource "azuread_application" "api" {
  display_name     = "Job Application Assistant API"
  sign_in_audience = "AzureADMyOrg" # External tenants only support single-tenant apps.
  owners           = [data.azuread_client_config.current.object_id]

  api {
    # v2.0 tokens: issuer https://<tenant-id>.ciamlogin.com/<tenant-id>/v2.0, aud = client ID.
    requested_access_token_version = 2

    oauth2_permission_scope {
      id                         = random_uuid.scope_access_as_user.result
      value                      = "access_as_user"
      type                       = "User"
      enabled                    = true
      admin_consent_display_name = "Use the Job Application Assistant API"
      admin_consent_description  = "Lets the app call the Job Application Assistant API as the signed-in user."
      user_consent_display_name  = "Use the Job Application Assistant API"
      user_consent_description   = "Lets the app access your saved resumes and usage on your behalf."
    }
  }

  app_role {
    id                   = random_uuid.role_admin.result
    value                = "Admin"
    display_name         = "Admin"
    description          = "Can view the admin analytics pages."
    allowed_member_types = ["User"]
    enabled              = true
  }

  app_role {
    id                   = random_uuid.role_postings_ingest.result
    value                = "Postings.Ingest"
    display_name         = "Postings.Ingest"
    description          = "Can call the internal ingestion endpoints (watcher service)."
    allowed_member_types = ["Application"]
    enabled              = true
  }
}

resource "azuread_application_identifier_uri" "api" {
  application_id = azuread_application.api.id
  identifier_uri = "api://${azuread_application.api.client_id}"
}

resource "azuread_service_principal" "api" {
  client_id = azuread_application.api.client_id
  owners    = [data.azuread_client_config.current.object_id]
}

# --- SPA (authorization code + PKCE, no secret) ----------------------------------------------

resource "azuread_application" "spa" {
  display_name     = "Job Application Assistant"
  sign_in_audience = "AzureADMyOrg"
  owners           = [data.azuread_client_config.current.object_id]

  single_page_application {
    # MSAL Browser v5 returns sign-in responses to a dedicated redirect bridge page.
    redirect_uris = [for origin in var.spa_redirect_origins : "${origin}/redirect.html"]
  }

  required_resource_access {
    resource_app_id = azuread_application.api.client_id

    resource_access {
      id   = random_uuid.scope_access_as_user.result
      type = "Scope"
    }
  }

  # openid and offline_access are granted implicitly; nothing from Microsoft Graph is needed.
}

resource "azuread_service_principal" "spa" {
  client_id = azuread_application.spa.client_id
  owners    = [data.azuread_client_config.current.object_id]
}

# Tenant-wide consent so users are not asked to approve the API scope at first sign-in.
resource "azuread_service_principal_delegated_permission_grant" "spa_to_api" {
  service_principal_object_id          = azuread_service_principal.spa.object_id
  resource_service_principal_object_id = azuread_service_principal.api.object_id
  claim_values                         = ["access_as_user"]
}

resource "azuread_app_role_assignment" "admins" {
  for_each = toset(var.admin_object_ids)

  app_role_id         = random_uuid.role_admin.result
  principal_object_id = each.value
  resource_object_id  = azuread_service_principal.api.object_id
}

# --- Watcher (optional confidential client) -------------------------------------------------

resource "azuread_application" "watcher" {
  count = var.create_watcher_app ? 1 : 0

  display_name     = "Job Posting Watcher"
  sign_in_audience = "AzureADMyOrg"
  owners           = [data.azuread_client_config.current.object_id]

  required_resource_access {
    resource_app_id = azuread_application.api.client_id

    resource_access {
      id   = random_uuid.role_postings_ingest.result
      type = "Role"
    }
  }
}

resource "azuread_service_principal" "watcher" {
  count = var.create_watcher_app ? 1 : 0

  client_id = azuread_application.watcher[0].client_id
  owners    = [data.azuread_client_config.current.object_id]
}

resource "azuread_app_role_assignment" "watcher_ingest" {
  count = var.create_watcher_app ? 1 : 0

  app_role_id         = random_uuid.role_postings_ingest.result
  principal_object_id = azuread_service_principal.watcher[0].object_id
  resource_object_id  = azuread_service_principal.api.object_id
}

# --- Outputs: copy these into infra/azure variables and the frontend build variables ---------

output "tenant_id" {
  value = var.tenant_id
}

output "api_client_id" {
  value = azuread_application.api.client_id
}

output "api_app_id_uri" {
  value = azuread_application_identifier_uri.api.identifier_uri
}

output "api_scope" {
  description = "VITE_ENTRA_API_SCOPE for the frontend."
  value       = "${azuread_application_identifier_uri.api.identifier_uri}/access_as_user"
}

output "spa_client_id" {
  description = "VITE_ENTRA_SPA_CLIENT_ID for the frontend."
  value       = azuread_application.spa.client_id
}

output "watcher_client_id" {
  value = var.create_watcher_app ? azuread_application.watcher[0].client_id : null
}
