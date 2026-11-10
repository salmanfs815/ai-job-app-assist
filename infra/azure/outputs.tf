# Values the watcher repository and the app workflows need. See docs/setup/terraform.md.

output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "container_app_environment_id" {
  description = "The watcher's Container Apps Job runs in this environment (shares the free grant)."
  value       = module.backend.environment_id
}

output "api_base_url" {
  description = "Public base URL of the backend API."
  value       = module.backend.url
}

output "api_app_id_uri" {
  description = "App ID URI of the API app registration (from infra/entra)."
  value       = var.entra_api_app_id_uri
}

output "frontend_url" {
  value = module.frontend.url
}

output "cosmos_endpoint" {
  value = module.cosmos.endpoint
}

output "cosmos_containers" {
  description = "Containers that exist (or will exist) in the database, with their partition keys."
  value       = module.cosmos.partition_keys
}
