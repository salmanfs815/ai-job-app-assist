# 4. Cosmos DB partitioning and capacity mode

- Status: Accepted
- Date: 2026-11-09 (capacity mode decided by the owner on 2026-11-09)

## Context and problem statement

Phase 1 adds three containers next to the existing `results` container, and Phase 2 adds
roughly six more. The brief asked for all containers to share database-level throughput inside
the Cosmos DB free tier (1000 RU/s, 25 GB). Inspecting the live account (2026-11-09) showed:

| Setting | Live value |
| --- | --- |
| Capacity mode | **Serverless** (`EnableServerless` capability) |
| Free tier | **Off** (it can only be enabled when an account is created) |
| `jobassist` database | No provisioned throughput (serverless has none) |
| `results` container | Partition key `/type`, default indexing |
| Usage, last 30 days | 73 request units in total, 4 active days, 544 KB stored |
| Cosmos cost since August 2026 | a fraction of a cent per month |

The account was deliberately moved to serverless earlier. A previous free-tier setup was billed
continuously: free tier discounts the first 1000 RU/s of *provisioned* throughput, and anything
provisioned above that (for example several containers with their own throughput, each at
least 400 RU/s) is billed every hour whether or not it is used.

## Considered options

1. **Keep the serverless account.**
   - Pay per request unit consumed plus storage; idle costs nothing. At this volume it rounds
     to $0, and a rough estimate for Phase 2 ingestion (an hourly watcher, ~20 changed postings
     an hour, ~30 RU each) stays well under a million RU a month: cents.
   - Bursts (ingestion batches of up to 100 events) are not squeezed by a fixed RU/s budget.
   - No migration.
   - Not literally free, and there is no hard spending ceiling: the account throughput limit
     is documented as unavailable for serverless accounts, so the `4000` value on the account
     has no effect.
2. **New free-tier account with one shared-throughput database at 1000 RU/s**, with the
   account limit set to the free-tier amount.
   - Guaranteed $0 within 1000 RU/s and 25 GB, if configured exactly right.
   - 1000 RU/s shared by every container: ingestion batches would be throttled (429) and rely
     on retries.
   - Migration: a new account, endpoint and key, a data copy and a cut-over. Only one free-tier
     account per subscription, which the watcher could then not have separately.
   - Misconfiguration is billed hourly, which is what happened before.

## Decision: capacity

Option 1, keep serverless. It matches how the app is actually used (rare, small bursts) and
avoids the failure mode already experienced with provisioned throughput.

Because serverless has no hard ceiling, two things bound spend instead:

- The API is the only path to Cosmos, and every request passes the per-IP rate limit; LLM
  calls also pass quotas and the daily budget (ADR 0003).
- A monthly **budget alert** on the resource group (Terraform, `infra/azure/budget.tf`;
  default 2 in the billing currency) notifies the Owners at 50% actual, 100% forecast and
  100% actual spend. Budgets are free; they notify but do not stop spending.

Revisit if Cosmos spend approaches about a dollar a month.

## Decision: partitioning

| Container | Partition key | Why |
| --- | --- | --- |
| `users` | `/id` | Every access is a point read of one user (1 RU). |
| `resumes` | `/userId` | A user's resumes are always listed together; one logical partition per user keeps listing a single-partition query. Resume text is excluded from the index (read by id only). |
| `usage` | `/userId` | One document per owner per UTC day (`id` = date). Global budget documents use `userId = "global"`. Per-item TTL: guests 2 days, users 90 days, global 400 days. |
| `results` | `/type` (existing) | Kept as is. Phase 1 adds a `userId` field to new results so account deletion can find them (a rare cross-partition query). Guest results are no longer written. |

Counters use optimistic concurrency (`If-Match` on `_etag`), so concurrent updates retry
rather than overwrite each other.

The global budget lives in a single logical partition (`userId = "global"`). At this scale that
is fine; a busier app would shard it per hour.

## Consequences

- Good: every hot path is a point read or a single-partition query.
- Good: no migration of live data in Phase 1.
- Bad: until the owner decides on option 2, Cosmos is pay-per-use rather than free.
- Local development and tests use in-memory repositories with the same interfaces; the Cosmos
  repositories are tested against a fake of the SDK container, and the emulator can be used
  for manual checks (see `docs/setup/local-development.md`).
