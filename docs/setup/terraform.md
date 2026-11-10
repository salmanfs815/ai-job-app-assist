# Infrastructure as code (Terraform + HCP Terraform)

`infra/azure` describes every Azure resource the app runs on. The live resources were created
by hand and are **adopted with `import` blocks**; nothing is recreated. See ADR 0008.

```
infra/
  azure/                 # applied from GitHub Actions
    imports.tf           # adopts the existing resources
    main.tf              # wiring; Phase 1 additions behind enable_phase1
    modules/cosmos       # account, database, containers
    modules/backend      # Container Apps environment + API app
    modules/frontend     # Static Web App
  entra/                 # applied by the owner (docs/setup/entra-external-id.md)
```

## One-time bootstrap

### 1. HCP Terraform (free)

1. Create an organization at <https://app.terraform.io> (the Free plan covers 500 managed
   resources; this uses about 15).
2. Create a workspace, e.g. `jobassist-azure`, as a **CLI-driven** workspace and set its
   **Execution mode** to **Local**. Runs happen on the GitHub runner; HCP stores state only.
3. Create a team or user API token for CI.

### 2. GitHub settings

Secrets (Settings → Secrets and variables → Actions → Secrets):

| Secret | Value |
| --- | --- |
| `TF_API_TOKEN` | HCP Terraform API token |
| `OPENAI_API_KEY` | the same key the API uses today (stored as a Container Apps secret) |
| `AIJOBASSISTBACKEND_AZURE_*` | already present (client ID, tenant ID, subscription ID) |

Variables (same page, **Variables** tab): `TF_CLOUD_ORGANIZATION`, `TF_WORKSPACE`.

Environment: create a `production` environment with **Required reviewers** (you). Every
`terraform apply` waits for that approval.

### 3. Let the CI identity plan pull requests and apply from the environment

The existing managed identity `cae-ai-job-assistrg-job-assistOidc` trusts only pushes to
`master`. Terraform also runs on pull requests and inside the `production` environment, and
each is a different OIDC subject. Add two federated credentials (one-off, outside Terraform so
Terraform never manages the identity it signs in with):

```bash
az identity federated-credential create -g rg-job-assist --identity-name cae-ai-job-assistrg-job-assistOidc --name github-pull-request --issuer https://token.actions.githubusercontent.com --subject repo:salmanfs815/ai-job-app-assist:pull_request --audiences api://AzureADTokenExchange
```

```bash
az identity federated-credential create -g rg-job-assist --identity-name cae-ai-job-assistrg-job-assistOidc --name github-env-production --issuer https://token.actions.githubusercontent.com --subject repo:salmanfs815/ai-job-app-assist:environment:production --audiences api://AzureADTokenExchange
```

The identity already has **Contributor** on `rg-job-assist`, which covers reading Cosmos keys
and Container Apps secrets during plan. It needs nothing at subscription scope.

## Rollout

1. **Import-only apply.** Merge the infrastructure PR. The PR plan must read
   `7 to import, 0 to add, 0 to change, 0 to destroy`; approve the apply. Verified locally
   against production on 2026-11-09 with exactly that result.
2. **Phase 1 changes.** Set the repository variable `TF_ENABLE_PHASE1=true` and run the
   workflow (or push any `infra/azure` change). Expected plan: `5 to add, 1 to change,
   0 to destroy` (verified with a read-only plan on 2026-11-09):
   - Cosmos containers `users` (`/id`), `resumes` (`/userId`), `usage` (`/userId`, TTL on);
   - a random IP-hash salt;
   - a monthly budget alert on the resource group (default 2 in the billing currency) that
     emails the resource group's Owners at 50% actual, 100% forecast and 100% actual spend.
     To add other addresses, set the secret `BUDGET_ALERT_EMAILS` to a JSON list such as
     `["you@example.com"]`;
   - Container App: auth, guest-mode and limit settings, the salt as a secret, and
     `maxReplicas` 2 → 1.

   Creating containers on the serverless account costs nothing until they are used, and
   budgets are free (see ADR 0004).
3. **Sign-in.** After `docs/setup/entra-external-id.md`, set the `ENTRA_*` variables; the next
   plan adds the three `ENTRA_*` settings to the API.

## Guard rails

- `prevent_destroy` on every stateful resource.
- The workflow fails a plan that would destroy or replace anything, before it is applied.
- Terraform ignores the running image (the backend workflow owns it), the Static Web App's
  GitHub link, and the Cosmos IP firewall (managed in the portal; it contains personal IPs).

## Running a plan locally

```bash
az login
```

```bash
cd infra/azure && terraform init && terraform plan -var subscription_id=$(az account show --query id -o tsv)
```

`terraform plan` prompts for `openai_api_key`; any value works for a read-only plan but shows a
change to that secret unless it matches. Never run `apply` locally against production; let CI
do it after review.

## Outputs for the watcher repository

| Output | Use |
| --- | --- |
| `container_app_environment_id` | Create the watcher's Container Apps Job in the same environment (shares the free grant). |
| `api_base_url` | Base URL for `/internal/*` calls. |
| `api_app_id_uri` | Only needed if service-to-service auth uses tokens (see ADR 0006). |

The apply job prints all outputs in its run summary; `terraform output` shows them locally.
