# 3. Rate limiting and LLM spend protection

- Status: Accepted
- Date: 2026-11-09

## Context and problem statement

The public demo exposes endpoints that call OpenAI and endpoints that run OCR. Before this
change anyone could call them in a loop and run up the OpenAI bill or burn the Container Apps
free grant. Hosting must stay at $0, so the protection itself cannot need paid infrastructure
(no Redis, no API gateway, no WAF).

## Decision drivers

- Bound the worst-case daily OpenAI spend with a hard, configurable number.
- Keep the demo usable for a first-time visitor without an account.
- No new paid components; survive scale-to-zero.
- Limits must be testable deterministically.

## Considered options

1. **Edge limiting** (API Management, Front Door, Cloudflare): not free on Azure, or adds a third
   party in front of the API.
2. **Redis-backed limiter**: correct across replicas, but there is no free Redis on Azure.
3. **In-process limiter plus durable counters in Cosmos DB** (chosen).

## Decision

Three independent layers, cheapest check first:

| Layer | Scope | Storage | Response |
| --- | --- | --- | --- |
| Per-IP token bucket | every endpoint except `/health` and CORS preflights | process memory | `429` + `Retry-After` |
| Daily generation quota | per signed-in user (20) / per guest IP (3) | Cosmos `usage`, one document per owner per UTC day | `429` + `Retry-After` |
| Global daily LLM budget | all LLM calls together ($1.00) | Cosmos `usage`, `userId = "global"` | `503` + `Retry-After` |

Details that matter:

- **Token bucket in memory.** Burst 60, refill 1/s; uploads and generations cost 10 tokens. The
  limit is exact only while one replica serves traffic, so the Container App is pinned to
  `maxReplicas = 1`. With more replicas the effective limit is multiplied by the replica count;
  the quota and budget layers are unaffected because they live in Cosmos.
- **Client address.** Azure Container Apps ingress sets `X-Forwarded-For`. Only the right-most
  `TRUSTED_PROXY_HOPS` entries are trusted (default 1), so a client cannot dodge limits by
  sending its own header. Verified against the ingress documentation on 2026-11-09; the docs
  disagree on whether a client-supplied value is appended to or replaced, and taking the
  right-most entry is correct in both cases.
- **Guest identity.** Guests are counted by `sha256(salt + ip)`. Raw IP addresses are never
  stored, and guest usage documents expire after two days (Cosmos TTL).
- **Optimistic concurrency.** Counters are read, changed and written back with `If-Match` on the
  ETag, retrying on conflict, so concurrent requests cannot lose increments.
- **Reserve, then settle.** A generation is counted before the LLM call starts and refunded only
  if the provider failed before producing any output. Token usage is recorded when the stream
  ends, including when the browser disconnects mid-stream (shielded from cancellation).
- **Token usage on streams.** `stream_options={"include_usage": true}` makes OpenAI append a final
  chunk with usage (verified 2026-11-09). If that chunk never arrives, usage is estimated at four
  characters per token.
- **Cost estimate.** Tokens are priced from a table in `app/domain/pricing.py` (overridable by
  environment variables). Unknown models use a deliberately high fallback price so the guard
  can only trip early.
- **Bounded request cost.** Pasted text is capped at 60,000 characters per field and output at
  `LLM_MAX_OUTPUT_TOKENS`, so a single request cannot blow through the budget on its own.
- **Budget overshoot.** The budget is checked before a call and charged after it, so concurrent
  calls can overshoot by at most their own cost (about a cent each at the default model).
- **Store outage.** If Cosmos is unreachable, or the `usage` container does not exist yet, counters
  fall back to process memory for 60 seconds at a time. Limits stay enforced (per process) rather
  than failing open (unlimited spend) or failing closed (dead demo).
- **Mock mode.** Without an OpenAI key, quotas still apply so the UI can be exercised, but no
  cost is charged to the budget.

## Consequences

- Good: worst-case OpenAI spend is roughly the configured budget per day; no paid components.
- Good: all three layers are pure or repository-backed and covered by tests with a fake clock.
- Bad: per-IP limiting is per replica and resets when the app scales to zero. Acceptable because
  the durable layers bound spend.
- Bad: users behind one NAT share a guest quota. Signing in gives each of them their own.
- Bad: cost is an estimate, not the invoice. The OpenAI dashboard remains the source of truth, and
  a hard monthly limit should also be set there.
