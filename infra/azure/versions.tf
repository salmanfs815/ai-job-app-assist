terraform {
  required_version = ">= 1.14.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.13"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9"
    }
  }

  # Remote state in HCP Terraform (Free). The organization and workspace come from the
  # TF_CLOUD_ORGANIZATION and TF_WORKSPACE environment variables, so nothing account-specific
  # is committed. The workspace runs in "Local" execution mode: plans and applies run on the
  # GitHub Actions runner (with Azure OIDC credentials) and HCP Terraform only stores state.
  # See docs/setup/terraform.md.
  cloud {}
}
