# AI Job Application Assistant (Starter)

Full-stack starter app with:
- FastAPI backend
- Simple React frontend (Vite)
- Postgres DB
- Dockerized local dev via Docker Compose
- OpenAI integration

## Features (v1)
- Analyze resume + job description
- Extract and score keyword/skill alignment
- Rewrite resume bullets for alignment
- Generate tailored cover letters

## Quick Start

1. Copy env file:
   ```bash
   cp .env.example .env
   ```
2. Add your OpenAI key in `.env`.
3. Run:
   ```bash
   docker compose up --build
   ```
4. Open:
   - Frontend: http://localhost:3000
   - Backend docs: http://localhost:8000/docs

## API Endpoints
- `GET /health`
- `POST /analyze`
- `POST /cover-letter`

## Notes
- If OpenAI key is not set, backend uses deterministic mock output so the UI remains testable.
