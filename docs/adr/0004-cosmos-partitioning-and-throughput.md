# 4. Cosmos DB partitioning and capacity mode

- Status: Accepted (capacity mode: pending the owner's decision, see below)
- Date: 2026-11-09

## Context and problem statement

Phase 1 adds three containers next to the existing `results` container. The brief asked for all
containers to share database-level throughput inside the Cosmos DB free tier (1000 RU/s,
25 GB). Inspecting the live account (2026-11-09) showed:

| Setting | Live value |
| --- | --- |
| Capacity mode | **Serverless** (`EnableServerless` capability) |
| Free tier | **Off** (it can only be enabled when an account is created) |
| Account throughput limit | 4000 RU/s |
| `jobassist` database | No provisioned throughput (serverless has none) |
| `results` container | Partition key `/type`, default indexing |

Serverless accounts have no provisioned or shared throughput at all: every operation is billed
per request unit consumed (plus storage). At this app's volume that is cents per month, but it is
not $0, and there is no way to switch an existing account to provisioned throughput or to free
tier.

## Options for capacity

1. **Keep the serverless account** (current). No migration, no downtime. Pay-per-use: a small,
   bounded cost (the account-wide 4000 RU/s cap limits a spike). Free tier stays unused.
2. **New free-tier account with a shared-throughput database (1000 RU/s)** and migrate
   `results` into it. Truly $0 within the limits, but a new account (new endpoint and keys),
   a data copy, and a cut-over. One free-tier account per subscription.

Recreating live resources needs the owner's approval, so Phase 1 implements option 1 and
leaves option 2 as a proposed migration (copy `results` with a one-off script, point the API at
the new account through Terraform, then retire the old account).

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
