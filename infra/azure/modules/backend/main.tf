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

variable "environment_name" {
  type = string
}

variable "app_name" {
  type = string
}

variable "image" {
  type = string
}

variable "max_replicas" {
  type = number
}

variable "env" {
  description = <<-EOT
    Environment variables in order. Each sets either `value` or `secret_name`. Order is kept
    as given: the API compares the list positionally, so reordering shows up as a change.
  EOT
  type = list(object({
    name        = string
    value       = optional(string)
    secret_name = optional(string)
  }))
}

variable "secrets" {
  description = "Container Apps secret values, keyed by secret name."
  type        = map(string)
  sensitive   = true
}

# Consumption-only environment. Its free monthly grant (180,000 vCPU-s, 360,000 GiB-s and
# 2M requests per subscription) is shared with the watcher's Container Apps Job.
resource "azurerm_container_app_environment" "main" {
  name                  = var.environment_name
  resource_group_name   = var.resource_group_name
  location              = var.location
  public_network_access = "Enabled"
  mutual_tls_enabled    = false

  identity {
    type = "SystemAssigned"
  }

  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }

  lifecycle {
    # Recreating the environment would change the API's public hostname.
    prevent_destroy = true
  }
}

resource "azurerm_container_app" "main" {
  name                         = var.app_name
  resource_group_name          = var.resource_group_name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  max_inactive_revisions       = 100

  identity {
    type = "SystemAssigned"
  }

  dynamic "secret" {
    for_each = nonsensitive(toset(keys(var.secrets)))
    content {
      name  = secret.value
      value = var.secrets[secret.value]
    }
  }

  ingress {
    external_enabled           = true
    target_port                = 8000
    transport                  = "auto"
    allow_insecure_connections = false
    client_certificate_mode    = "ignore"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    # Scale to zero when idle; one replica keeps the in-memory rate limiter exact (ADR 0003).
    min_replicas                = 0
    max_replicas                = var.max_replicas
    cooldown_period_in_seconds  = 300
    polling_interval_in_seconds = 30

    http_scale_rule {
      name                = "http-scaler"
      concurrent_requests = "10"
    }

    container {
      name   = var.app_name
      image  = var.image
      cpu    = 0.25
      memory = "0.5Gi"

      dynamic "env" {
        for_each = var.env
        content {
          name        = env.value.name
          value       = env.value.value
          secret_name = env.value.secret_name
        }
      }

      liveness_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/health"
        initial_delay           = 5
        interval_seconds        = 10
        timeout                 = 5
        failure_count_threshold = 3
      }

      readiness_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/health"
        initial_delay           = 5
        interval_seconds        = 10
        timeout                 = 5
        failure_count_threshold = 3
        success_count_threshold = 1
      }
    }
  }

  lifecycle {
    # The backend workflow rolls out new images; Terraform owns everything else.
    ignore_changes = [template[0].container[0].image]
  }
}

output "environment_id" {
  value = azurerm_container_app_environment.main.id
}

output "url" {
  value = "https://${azurerm_container_app.main.ingress[0].fqdn}"
}
