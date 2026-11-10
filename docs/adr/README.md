# Architecture decision records

Decisions are recorded in [MADR](https://adr.github.io/madr/) format. A new decision gets the
next number; a changed decision gets a new record that supersedes the old one.

| # | Decision | Status |
| --- | --- | --- |
| [0001](0001-authentication-provider.md) | Microsoft Entra External ID for user sign-in | Accepted |
| [0002](0002-guest-mode.md) | Guest mode for the original tool | Accepted |
| [0003](0003-rate-limiting-and-spend-protection.md) | Rate limiting and LLM spend protection | Accepted |
| [0004](0004-cosmos-partitioning-and-throughput.md) | Cosmos DB partitioning and capacity mode | Accepted (capacity mode pending owner decision) |
| 0005 | Watcher pushes postings to the API instead of sharing a database | Planned (Phase 2) |
| [0006](0006-service-to-service-auth.md) | HMAC request signing between the watcher and the API | Proposed |
| 0007 | Deterministic matching and skill extraction (no LLM cost) | Planned (Phase 2–3) |
| [0008](0008-terraform-with-imported-resources.md) | Terraform with imported resources | Accepted |
| 0009 | OpenTelemetry for operations, Cosmos rollups for product analytics | Planned (Phase 2–3) |
