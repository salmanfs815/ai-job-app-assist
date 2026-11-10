provider "azurerm" {
  subscription_id = var.subscription_id

  # Every provider this configuration needs is already registered on the subscription.
  # azurerm 5.x registers nothing by default, which keeps the CI identity's permissions small.
  resource_provider_registrations = "none"

  features {
    resource_group {
      # Never delete a resource group that still holds resources Terraform does not know about.
      prevent_deletion_if_contains_resources = true
    }
  }
}
