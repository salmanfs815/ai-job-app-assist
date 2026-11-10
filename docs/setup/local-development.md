# Local development

Mock mode needs nothing but Docker: no OpenAI key, no Azure, no identity provider.

## Quick start (3 commands)

```bash
git clone https://github.com/salmanfs815/ai-job-app-assist.git
```

```bash
cd ai-job-app-assist
```

```bash
docker compose up --build
```

Open <http://localhost:3000>. The API docs are at <http://localhost:8000/docs>.

What you get: deterministic sample output instead of OpenAI (the UI shows a "Demo output"
badge), in-memory storage, and **dev sign-in** (`AUTH_MODE=dev`): the **Sign in** button signs
you in as "Demo User" so you can try saved resumes and settings.

## Without Docker (live reload)

Backend (Python 3.12):

```bash
cd backend && python -m venv .venv && .venv/Scripts/activate && pip install -r requirements-dev.txt
```

```bash
ENVIRONMENT=local AUTH_MODE=dev TRUSTED_PROXY_HOPS=0 FRONTEND_ORIGIN=http://localhost:5173 uvicorn app.main:app --reload --port 8000
```

On PowerShell set the variables first, e.g. `$env:ENVIRONMENT="local"`. On macOS/Linux the
activate script is `.venv/bin/activate`.

Frontend (Node 22+):

```bash
cd frontend && npm ci && npm run dev
```

The frontend reads `VITE_*` variables from `frontend/.env.local`; for dev sign-in use:

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_AUTH_MODE=dev
```

## Checks (what CI runs)

```bash
cd backend && ruff check . && ruff format --check . && mypy && pytest --cov=app
```

```bash
cd frontend && npm run typecheck && npm run lint && npm run format:check && npm test && npm run build
```

`pre-commit install` runs ruff and mypy on every commit.

## Configuration

Every variable is listed with a comment in [`.env.example`](../../.env.example). The ones you are
most likely to change locally:

| Variable | Default | Meaning |
| --- | --- | --- |
| `OPENAI_API_KEY` | empty | Empty = mock mode. |
| `ENVIRONMENT` | `production` | Set `local` for development (required for dev sign-in). |
| `AUTH_MODE` | `entra` | `dev` fakes users via `X-Dev-User`. |
| `GUEST_DAILY_GENERATION_LIMIT` / `USER_DAILY_GENERATION_LIMIT` | 3 / 20 | Daily generations. |
| `GLOBAL_DAILY_LLM_BUDGET_USD` | 1.00 | Estimated spend per UTC day before generation pauses. |
| `RATE_LIMIT_ENABLED` | `true` | Per-IP token bucket. |
| `TRUSTED_PROXY_HOPS` | 1 | Set 0 when nothing sits in front of the API. |
| `PERSISTENCE_ENABLED` | `false` | `true` uses Cosmos DB instead of memory. |

## Optional: Cosmos DB emulator

To try the Cosmos repositories locally, run the Linux (vNext) emulator (instructions verified
2026-11-09 against Microsoft Learn; it serves HTTP on 8081 by default, which the Python SDK
supports):

```bash
docker run --detach --name cosmos --publish 8081:8081 --publish 8080:8080 --publish 1234:1234 mcr.microsoft.com/cosmosdb/linux/azure-cosmos-emulator:vnext-latest
```

Create the database `jobassist` with containers `results` (`/type`), `users` (`/id`),
`resumes` (`/userId`) and `usage` (`/userId`, TTL on) in the Data Explorer at
<http://localhost:1234>, then start the API with `PERSISTENCE_ENABLED=true`,
`COSMOS_ENDPOINT=http://localhost:8081/` and the emulator's well-known account key. The
emulator does not enforce authentication and does not implement request-unit accounting, so it
is only for functional checks.

The automated tests do not need the emulator: repositories are tested against in-memory
implementations and a fake of the Cosmos SDK container.
