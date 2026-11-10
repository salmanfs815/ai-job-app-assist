# Set up sign-in (Microsoft Entra External ID)

Until these steps are done the app runs as a guest-only demo: the API accepts no tokens and the
frontend hides sign-in. Nothing here costs money as long as you stay under 50,000 monthly
active users and do not enable paid add-ons (SMS, M2M authentication, Go-Local).

Verified against Microsoft Learn on 2026-11-09. Portal labels change from time to time; the
concepts do not.

## 1. Create the external tenant (portal, once)

1. Sign in to the [Microsoft Entra admin center](https://entra.microsoft.com) with the account
   that owns the Azure subscription.
2. **Entra ID → Overview → Manage tenants → Create**, choose **External**, and pick a
   subdomain, for example `jobassist`. The sign-in host becomes `jobassist.ciamlogin.com`.
3. Link the tenant to the existing subscription (`rg-job-assist`) when asked. External ID bills
   through a subscription even when usage stays inside the free allowance.
4. Note the **tenant ID** (Overview page) and the **subdomain**.

## 2. Create the app registrations (Terraform, from your machine)

```bash
az login --tenant <external-tenant-id> --allow-no-subscriptions
```

```bash
cd infra/entra
terraform init
terraform apply -var tenant_id=<external-tenant-id>
```

State for this root goes to its own HCP Terraform workspace (set `TF_CLOUD_ORGANIZATION` and
`TF_WORKSPACE`, for example `jobassist-entra`). It contains no secrets.

This creates:

| Registration | Purpose |
| --- | --- |
| **Job Application Assistant API** | Exposes the `access_as_user` scope; app roles `Admin` (users) and `Postings.Ingest` (applications); issues v2.0 access tokens; App ID URI `api://<client-id>`. |
| **Job Application Assistant** (SPA) | Authorization code + PKCE, redirect URIs `<origin>/redirect.html` for the Static Web App and local dev. Admin consent to the API scope is granted, so users are not prompted. |
| Job Posting Watcher (optional) | Off by default; see ADR 0006. |

To give yourself the `Admin` role, sign up once (step 4), copy your user's object ID from
**Users**, and re-apply with `-var 'admin_object_ids=["<object-id>"]'`.

Run `terraform output` and keep the values for steps 5 and 6.

## 3. Create the sign-up and sign-in user flow (portal)

1. In the external tenant: **External Identities → User flows → New user flow**.
2. Name it `signupsignin`. Identity providers: **Email with password** and/or **Email
   one-time passcode**. Collect the **Display name** attribute.
3. Open the flow → **Applications → Add application** → select **Job Application Assistant**
   (the SPA). The API does not need to be added.
4. Optional: **Company branding** to add the app name and colours to the sign-in page.

Google sign-in is optional and off. To enable it later, create a Google OAuth client, add
Google under **External Identities → All identity providers**, and tick it in the user flow.

## 4. Check the issuer the API should trust

```bash
curl -s https://<subdomain>.ciamlogin.com/<tenant-id>/v2.0/.well-known/openid-configuration
```

The API expects `issuer` to be `https://<tenant-id>.ciamlogin.com/<tenant-id>/v2.0` and the
keys at `jwks_uri` = `https://<subdomain>.ciamlogin.com/<tenant-id>/discovery/v2.0/keys`.
If either differs, set `ENTRA_ISSUER` / `ENTRA_JWKS_URI` on the API to the values shown.

## 5. Configure the API (Terraform, `infra/azure`)

Set these GitHub **repository variables** (Settings → Secrets and variables → Actions →
Variables) and merge or re-run the Terraform workflow:

| Variable | Value |
| --- | --- |
| `ENTRA_TENANT_ID` | external tenant ID |
| `ENTRA_TENANT_SUBDOMAIN` | e.g. `jobassist` |
| `ENTRA_API_CLIENT_ID` | `api_client_id` output |
| `ENTRA_API_APP_ID_URI` | `api_app_id_uri` output |
| `TF_ENABLE_PHASE1` | `true` (see `docs/setup/terraform.md`) |

## 6. Configure the frontend build

Set these repository variables; the Static Web Apps workflow passes them to the build:

| Variable | Value |
| --- | --- |
| `VITE_AUTH_MODE` | `entra` |
| `VITE_ENTRA_TENANT_SUBDOMAIN` | e.g. `jobassist` |
| `VITE_ENTRA_SPA_CLIENT_ID` | `spa_client_id` output |
| `VITE_ENTRA_API_SCOPE` | `api_scope` output (`api://<api-client-id>/access_as_user`) |

If any of these is missing the frontend stays in guest-only mode instead of showing a broken
sign-in button.

## 7. Try it

1. Open the site, choose **Sign in**, and create an account with your email.
2. Settings should show your email and **20 generations** for today.
3. On the API, an expired or tampered token gets `401 invalid_token`; a token for another API
   gets `401` as well; a token without `access_as_user` gets `403 insufficient_scope`.

## Local development without a tenant

Run the API with `AUTH_MODE=dev` and `ENVIRONMENT=local`, and the frontend with
`VITE_AUTH_MODE=dev`. **Sign in** then signs you in as a fake "Demo User" by sending an
`X-Dev-User` header. The API refuses to start with dev auth in any other environment.
