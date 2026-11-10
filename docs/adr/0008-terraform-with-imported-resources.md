# 8. Terraform with imported resources

- Status: Accepted
- Date: 2026-11-09

## Context and problem statement

All Azure resources were created by hand in the portal. They need to be described as code
without recreating anything that serves the live demo.

## Decision

- **Two Terraform roots.**
  - `infra/azure`: resource group, Cosmos account/database/containers, Container Apps
    environment and backend app, Static Web App. Planned on every PR (plan posted as a PR
    comment) and applied from `master` after approval on the `production` GitHub Environment.
  - `infra/entra`: app registrations in the External ID tenant. Applied by the owner from a
    workstation (see ADR 0006 for why not from CI).
- **Adopt, never recreate.** Live resources are brought in with `import` blocks. Stateful
  resources carry `prevent_destroy`, and the CI plan job fails if a plan destroys or replaces
  anything. A read-only plan against production on 2026-11-09 showed
  **7 to import, 0 to add, 0 to change, 0 to destroy**.
- **Two-step rollout.** `enable_phase1 = false` (default) is the import-only first apply.
  Setting it to `true` (repository variable `TF_ENABLE_PHASE1`) produces a second, separately
  reviewed plan: 3 new containers and a salt (4 to add) and 1 in-place update of the Container
  App (new settings, `maxReplicas` 2 → 1). Nothing is destroyed.
- **Boundary with the app workflows.** Terraform owns configuration (settings, secrets, scale,
  probes, ingress). The backend workflow only rolls out new images; Terraform ignores
  `template.container.image`. The frontend workflow only uploads build output.
- **Left out on purpose.**
  - The GitHub OIDC managed identity Terraform itself signs in with (bootstrap, documented).
  - The Cosmos IP firewall (`ip_range_filter`): it contains personal addresses that should not
    be in a public repository; it stays managed in the portal and Terraform ignores it.
  - The Static Web App's GitHub link (deployments use the API token).
  - Log Analytics: none exists; the environment streams logs only. Adding a workspace is a
    cost decision for later.
- **State.** HCP Terraform Free (up to 500 managed resources; this uses about 15) in "Local"
  execution mode: runs happen on GitHub Actions with Azure OIDC, HCP only stores state. State
  contains secret values (the Cosmos key, the OpenAI key), so the workspace is private.
- **Versions** (verified 2026-11-09): Terraform 1.17.1, `hashicorp/azurerm` 5.13,
  `hashicorp/azuread` 3.10, `hashicorp/random` 3.9. azurerm 5 no longer registers resource
  providers by default; the configuration sets `resource_provider_registrations = "none"`
  explicitly since all needed providers are registered.

## Consequences

- Good: the first apply is provably a no-op for live resources; changes after that are
  reviewed as plans in PRs.
- Bad: renaming a resource in Terraform would plan a replacement, which `prevent_destroy` and
  the CI guard block; real renames need a manual `moved`/import procedure.
- Bad: secrets flow through Terraform state (encrypted at rest in HCP).
