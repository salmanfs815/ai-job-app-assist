# AI Job Application Assistant

Full-stack app with:
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
- Resume upload parsing for PDF/DOCX files

## Quick Start

1. Copy env file:
   ```bash
   cp .env.example .env
   ```
2. Add OpenAI API key in `.env`.
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
- `POST /analyze-upload` (multipart form-data with `resume_file` or `resume_text`)
- `POST /cover-letter-upload` (multipart form-data with `resume_file` or `resume_text`)

## Notes
- If OpenAI key is not set, backend uses deterministic mock output so the UI remains testable.
- Supported uploaded resume formats: `.pdf`, `.docx`.
- Max upload size is configurable with `MAX_UPLOAD_BYTES` (default `5242880`, i.e. 5 MB).
- OCR fallback for scanned PDFs is enabled by default (`ENABLE_PDF_OCR_FALLBACK=true`) and uses Tesseract.
- Set `TESSERACT_CMD` only if your environment needs a custom Tesseract binary path.
