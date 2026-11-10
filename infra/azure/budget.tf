# Monthly cost alert for everything in the resource group. Budgets are free in Azure Cost
# Management. A budget only notifies; it does not stop spending. The spend controls are the
# API's rate limits, quotas and LLM budget (ADR 0003), and Cosmos DB is only reachable
# through the API (ADR 0004).

variable "monthly_budget_amount" {
  description = "Monthly budget for the resource group, in the subscription's billing currency."
  type        = number
  default     = 2
}

variable "budget_alert_emails" {
  description = <<-EOT
    Extra addresses for budget alerts. The resource group's Owners are always notified, so this
    can stay empty. Supply it through a CI secret (TF_VAR_budget_alert_emails) rather than
    committing addresses to this public repository.
  EOT
  type        = list(string)
  default     = []
}

resource "azurerm_consumption_budget_resource_group" "monthly" {
  count = var.enable_phase1 ? 1 : 0

  name              = "monthly-cost-guard"
  resource_group_id = azurerm_resource_group.main.id
  amount            = var.monthly_budget_amount
  time_grain        = "Monthly"

  time_period {
    # A budget must start on the first of a month no earlier than the current one, so it
    # starts in the month of the first apply. It is fixed after creation (see ignore_changes).
    start_date = formatdate("YYYY-MM-01'T'00:00:00Z", plantimestamp())
  }

  # Early warning: half the budget actually spent.
  notification {
    enabled        = true
    operator       = "GreaterThanOrEqualTo"
    threshold      = 50
    threshold_type = "Actual"
    contact_roles  = ["Owner"]
    contact_emails = var.budget_alert_emails
  }

  # Forecast to exceed the budget this month.
  notification {
    enabled        = true
    operator       = "GreaterThanOrEqualTo"
    threshold      = 100
    threshold_type = "Forecasted"
    contact_roles  = ["Owner"]
    contact_emails = var.budget_alert_emails
  }

  # Budget exceeded.
  notification {
    enabled        = true
    operator       = "GreaterThanOrEqualTo"
    threshold      = 100
    threshold_type = "Actual"
    contact_roles  = ["Owner"]
    contact_emails = var.budget_alert_emails
  }

  lifecycle {
    ignore_changes = [time_period]
  }
}
