# Adopt the resources that were created by hand. Import blocks are idempotent: once a
# resource is in state they are no-ops, so they stay in the configuration as documentation.
# Nothing here is ever recreated: the stateful resources also carry `prevent_destroy`.

locals {
  rg_id = "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}"
}

import {
  to = azurerm_resource_group.main
  id = local.rg_id
}

import {
  to = module.cosmos.azurerm_cosmosdb_account.main
  id = "${local.rg_id}/providers/Microsoft.DocumentDB/databaseAccounts/${var.cosmos_account_name}"
}

import {
  to = module.cosmos.azurerm_cosmosdb_sql_database.main
  id = "${local.rg_id}/providers/Microsoft.DocumentDB/databaseAccounts/${var.cosmos_account_name}/sqlDatabases/${var.cosmos_database_name}"
}

import {
  to = module.cosmos.azurerm_cosmosdb_sql_container.results
  id = "${local.rg_id}/providers/Microsoft.DocumentDB/databaseAccounts/${var.cosmos_account_name}/sqlDatabases/${var.cosmos_database_name}/containers/results"
}

import {
  to = module.backend.azurerm_container_app_environment.main
  id = "${local.rg_id}/providers/Microsoft.App/managedEnvironments/${var.container_app_environment_name}"
}

import {
  to = module.backend.azurerm_container_app.main
  id = "${local.rg_id}/providers/Microsoft.App/containerApps/${var.backend_app_name}"
}

import {
  to = module.frontend.azurerm_static_web_app.main
  id = "${local.rg_id}/providers/Microsoft.Web/staticSites/${var.static_web_app_name}"
}
