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

variable "account_name" {
  type = string
}

variable "database_name" {
  type = string
}

variable "create_app_containers" {
  description = "Create the users, resumes and usage containers."
  type        = bool
}

# The live account is *serverless* (billed per request unit consumed, no provisioned
# throughput), not free tier. Free tier can only be chosen when an account is created, so
# moving to it would mean a new account and a data migration. See ADR 0004.
resource "azurerm_cosmosdb_account" "main" {
  name                = var.account_name
  resource_group_name = var.resource_group_name
  location            = var.location
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"

  free_tier_enabled             = false
  automatic_failover_enabled    = true
  public_network_access_enabled = true
  local_authentication_enabled  = true
  minimal_tls_version           = "Tls12"

  capabilities {
    name = "EnableServerless"
  }

  consistency_policy {
    consistency_level       = "Session"
    max_interval_in_seconds = 5
    max_staleness_prefix    = 100
  }

  geo_location {
    location          = var.location
    failover_priority = 0
    zone_redundant    = false
  }

  backup {
    type                = "Periodic"
    interval_in_minutes = 240
    retention_in_hours  = 8
    storage_redundancy  = "Geo"
  }

  # Account-wide cap on RU/s: a hard ceiling on what a traffic spike can cost.
  capacity {
    total_throughput_limit = 4000
  }

  tags = {
    defaultExperience         = "Core (SQL)"
    "hidden-cosmos-mmspecial" = ""
    "hidden-workload-type"    = "Learning"
  }

  lifecycle {
    prevent_destroy = true
    # The IP firewall is managed in the portal: it lists personal addresses that should not
    # live in a public repository.
    ignore_changes = [ip_range_filter]
  }
}

resource "azurerm_cosmosdb_sql_database" "main" {
  name                = var.database_name
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.main.name

  lifecycle {
    prevent_destroy = true
  }
}

# Existing container. Results are written by `type`; account deletion finds a user's
# results with a cross-partition query (rare, small).
resource "azurerm_cosmosdb_sql_container" "results" {
  name                  = "results"
  resource_group_name   = var.resource_group_name
  account_name          = azurerm_cosmosdb_account.main.name
  database_name         = azurerm_cosmosdb_sql_database.main.name
  partition_key_paths   = ["/type"]
  partition_key_version = 2

  indexing_policy {
    indexing_mode = "consistent"

    included_path {
      path = "/*"
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

locals {
  app_containers = {
    users   = { partition_key = "/id", default_ttl = null }
    resumes = { partition_key = "/userId", default_ttl = null }
    # TTL switched on (-1) without a default: each usage document sets its own `ttl`.
    usage = { partition_key = "/userId", default_ttl = -1 }
  }
}

resource "azurerm_cosmosdb_sql_container" "app" {
  for_each = var.create_app_containers ? local.app_containers : {}

  name                  = each.key
  resource_group_name   = var.resource_group_name
  account_name          = azurerm_cosmosdb_account.main.name
  database_name         = azurerm_cosmosdb_sql_database.main.name
  partition_key_paths   = [each.value.partition_key]
  partition_key_version = 2
  default_ttl           = each.value.default_ttl

  indexing_policy {
    indexing_mode = "consistent"

    included_path {
      path = "/*"
    }

    # Resume text is only ever read by id; indexing it would cost RUs on every write.
    dynamic "excluded_path" {
      for_each = each.key == "resumes" ? ["/text/?"] : []
      content {
        path = excluded_path.value
      }
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

output "endpoint" {
  value = azurerm_cosmosdb_account.main.endpoint
}

output "primary_key" {
  value     = azurerm_cosmosdb_account.main.primary_key
  sensitive = true
}

output "database_name" {
  value = azurerm_cosmosdb_sql_database.main.name
}

output "container_names" {
  value = {
    results = azurerm_cosmosdb_sql_container.results.name
    users   = "users"
    resumes = "resumes"
    usage   = "usage"
  }
}

output "partition_keys" {
  value = merge(
    { results = "/type" },
    { for name, container in local.app_containers : name => container.partition_key },
  )
}
