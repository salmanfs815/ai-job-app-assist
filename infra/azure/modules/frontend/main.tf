terraform {
  required_providers {
    azurerm = {
      source = "hashicorp/azurerm"
    }
  }
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "name" {
  type = string
}

resource "azurerm_static_web_app" "main" {
  name                = var.name
  resource_group_name = var.resource_group_name
  location            = var.location
  sku_tier            = "Free"
  sku_size            = "Free"

  configuration_file_changes_enabled = true
  preview_environments_enabled       = true

  tags = {}

  lifecycle {
    prevent_destroy = true
    # Linked to GitHub when it was created in the portal; deployments use the API token, so
    # Terraform leaves the repository link alone.
    ignore_changes = [repository_url, repository_branch]
  }
}

output "url" {
  value = "https://${azurerm_static_web_app.main.default_host_name}"
}
