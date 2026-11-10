# 2. Guest mode for the original tool

- Status: Accepted
- Date: 2026-11-09

## Context and problem statement

This is a portfolio project. Reviewers should be able to try the core feature in seconds,
without creating an account. At the same time, unauthenticated LLM endpoints are the cost risk
that started this work.

## Decision

`GUEST_MODE_ENABLED` (default on) lets anyone use the original analyze / cover-letter tool
(`/resume/extract`, `/job-description/extract`, `/generate/*`, `/quota`) without signing in:

- Guests are identified by `sha256(IP_HASH_SALT + client IP)`; raw addresses are never stored
  and guest usage documents expire after two days.
- Guests get a small daily allowance (default 3 generations) and the same per-IP rate limit
  and global budget as everyone else (ADR 0003).
- Guest results are streamed to the browser and **not persisted**.
- Everything else (`/me`, `/resumes`, and later the watchlist and feed) requires sign-in.
- Signing in gives a separate, larger allowance (default 20), so a reviewer who hits the guest
  limit has a reason to create an account.

The frontend also degrades gracefully: when sign-in is not configured for a deployment
(`VITE_AUTH_MODE` unset), it runs as the guest-only tool and hides account features.

## Consequences

- Good: no login wall for the demo; spend stays bounded.
- Bad: people sharing a NAT share the guest allowance. Signing in solves it for them.
- Bad: switching guest mode off makes the landing page's main call to action require sign-in.
