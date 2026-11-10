# 1. Microsoft Entra External ID for user sign-in

- Status: Accepted
- Date: 2026-11-09

## Context and problem statement

The app needs accounts so that resumes and history can be kept per person and so that LLM
quotas can be tied to a person rather than an IP address. Hosting must stay at $0, the rest of
the stack is on Azure, and handling passwords ourselves is out of the question.

## Considered options

1. **Microsoft Entra External ID** (external tenant)
2. Azure AD B2C
3. A third-party identity service (Auth0, Clerk, Supabase Auth)
4. Our own accounts (password hashes in Cosmos)

## Decision

Option 1. Verified on 2026-11-09 against Microsoft Learn:

- External ID's core offering is free for the first 50,000 monthly active users. Paid add-ons
  (SMS, Go-Local, **M2M authentication**) are not enabled.
- Email + password and email one-time passcode are supported for sign-up and sign-in; Google
  federation is optional and stays off unless the owner enables it.
- Authorization code with PKCE is supported for SPAs. The authority is
  `https://<subdomain>.ciamlogin.com/`.
- External tenants only support single-tenant app registrations; the `azuread` Terraform
  provider can manage them when authenticated to the external tenant.
- Azure AD B2C (option 2) is the previous generation of Microsoft's customer identity service;
  External ID is the current one, so a new project should not start on B2C.

### How it is wired

- **SPA** (public client, PKCE) signs users in with MSAL React v5 and requests the
  `access_as_user` scope. MSAL Browser v5 returns sign-in responses to a dedicated redirect
  bridge page (`/redirect.html`), which is the registered redirect URI.
- **API** validates v2.0 access tokens: RS256 only, signing key from a cached JWKS (refreshed
  daily or on an unknown `kid`, at most every five minutes), issuer, audience (client ID or
  `api://<client-id>`), expiry and not-before (60 s leeway), and the `access_as_user` scope.
  Application tokens (no `scp`) must carry an app role. The `Admin` app role is read from the
  `roles` claim.
- A user record is created on the first authenticated request (`oid` is the user ID).
- `AUTH_MODE=dev` replaces token validation with an `X-Dev-User` header for local work. The
  settings model refuses to start with it unless `ENVIRONMENT=local`, and `ENVIRONMENT`
  defaults to `production`.
- A request that presents a credential must present a valid one: an expired or wrong token is
  a 401, never a silent downgrade to guest.

## Consequences

- Good: no passwords stored or seen by the app; free at this scale; one cloud.
- Good: the frontend only downloads MSAL when sign-in is configured (lazy-loaded chunk).
- Bad: the external tenant, user flow, and branding are portal steps (documented in
  `docs/setup/entra-external-id.md`); only app registrations are in Terraform.
- Bad: the API depends on the identity provider's JWKS endpoint. Cached keys keep validating
  through an outage; with no cached keys the API returns 503 rather than 401.
