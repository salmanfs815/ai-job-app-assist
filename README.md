# AI Job Application Assistant

A full-stack application that helps automate and improve the process of tailoring job applications by aligning resumes with job descriptions using LLMs.

## Quick Start

1. Copy the environment template:
   ```bash
   cp .env.example .env
   ```
2. Add your OpenAI API key to `.env`.
3. For a simple local run without persistence, keep:
   ```env
   PERSISTENCE_ENABLED=false
   ```
4. Start the app (containers):
   ```bash
   docker compose up --build
   ```

Open:
- Frontend: http://localhost:3000
- Backend docs: http://localhost:8000/docs

## Development workflow with live reload

For day-to-day development, run the frontend and backend locally so changes appear instantly in the browser.

### 1. Backend (FastAPI) with auto-reload
```bash
cd backend
py -3 -m venv .venv
\.venv\Scripts\Activate.ps1   # Windows PowerShell
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Set `PERSISTENCE_ENABLED=false` (default) in `.env` to disable persistence, or set it to `true` and provide Cosmos connection values.

### 2. Frontend (React + Vite) with HMR
```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 3000
```

Open `http://localhost:3000` to see the app. Vite provides hot module replacement for frontend changes; `uvicorn --reload` reloads backend on Python file changes.

### Notes about persistence
- Persistence is optional and disabled by default to keep local development simple and inexpensive.
- When `PERSISTENCE_ENABLED=true`, the app uses Azure Cosmos DB (NoSQL) for storing JSON results. Configure the Cosmos variables in `.env`.

## Persistence and Azure Cosmos DB

The app supports optional persistence through Azure Cosmos DB for NoSQL. To enable Cosmos persistence, set:
```env
PERSISTENCE_ENABLED=true
COSMOS_ENDPOINT=https://<your-account>.documents.azure.com:443/
COSMOS_KEY=your_cosmos_key
COSMOS_DATABASE_NAME=jobassist
COSMOS_CONTAINER_NAME=results
```

When persistence is disabled, the app works normally and simply skips saving analysis and cover-letter results.

## Overview

Applying to jobs often requires manually tailoring resumes and writing cover letters for each role. This process is time-consuming, inconsistent, and prone to missing key requirements—especially those used in ATS (Applicant Tracking Systems).

This project addresses that problem by building a system that:
- Analyzes resume and job description alignment
- Identifies matching and missing skills
- Rewrites resume bullets for better alignment
- Generates tailored cover letters

## Motivation

This project was built to explore how backend systems can leverage LLMs to solve real-world productivity problems—specifically, improving the efficiency and quality of job applications.

It also serves as a deeper dive into:
- processing unstructured data
- designing reliable LLM-backed systems
- building production-style backend services

## Key Features

### 1. Resume + Job Description Analysis

- Accepts resume and job-description input (PDF/DOCX or text)
- Parses and extracts structured content
- Streams a Markdown tailoring report as it is generated
- Suggests supported changes to titles, summaries, skills, experience, section order, wording, and ATS alignment

### 2. Resume Bullet Optimization

- Uses LLM pipelines to rewrite resume bullets
- Aligns experience with job-specific requirements
- Improves clarity and relevance for ATS and recruiters

### 3. Cover Letter Generation

- Generates tailored cover letters based on:
  - resume content
  - job description
- Ensures consistency between resume and narrative
- Streams the draft to the browser as it is generated

### 4. File Parsing Pipeline

- Supports PDF and DOCX resume and job-description uploads
- Preserves PDF page markers to inform page-fit recommendations
- Extracts and normalizes text for downstream processing
- Handles unstructured input formats

### 5. Robust LLM Integration

- Structured prompting for consistent outputs
- Response validation and parsing
- Retry logic for API reliability
- Logging for debugging and observability

## System Architecture

```
Frontend (React - Vite)
        ↓
FastAPI Backend
        ↓
Processing Layer
  - Resume parsing
  - Job description analysis
  - Prompt construction
  - Response parsing
        ↓
OpenAI API (LLM)
        ↓
      Optional persistence: Azure Cosmos DB (NoSQL)
```

## Tech Stack

**Backend**
- Python
- FastAPI
- Optional persistence: Azure Cosmos DB (NoSQL)

**Frontend**
- React (Vite)

**AI Integration**
- OpenAI API (LLM)

**DevOps / Tooling**
- Docker
- Docker Compose

## How It Works

1. User uploads or pastes a resume and job description (PDF/DOCX or text)
2. Backend parses the resume and constructs Markdown-generation prompts.
3. The LLM generates resume improvements or a tailored cover letter.
4. Backend streams Markdown fragments to the frontend and persists completed results.

## API Endpoints
- `GET /health`
- `POST /resume/extract` (multipart form-data with `resume_file`)
- `POST /job-description/extract` (multipart form-data with `job_description_file`)
- `POST /generate/resume-suggestions` (JSON request; Server-Sent Events response)
- `POST /generate/cover-letter` (JSON request; Server-Sent Events response)

The generation endpoints return `text/event-stream`. Event types are:

- `status`: immediate progress text and whether local demo output is active
- `delta`: the next Markdown text fragment
- `done`: successful completion
- `error`: a safe error message plus `retryable` and `partial` flags

The frontend proxies all generation through FastAPI; the OpenAI API key is never sent to the browser. Streamed Markdown is rendered without enabling raw HTML.

### File reuse

When a PDF or DOCX is selected, the browser computes a SHA-256 hash and extracts it through the appropriate document endpoint. The extracted text is shown in its textarea so it can be reviewed or edited. Selecting the same file again in the same page session reuses an in-memory cache and skips upload, parsing, and OCR. The cache is cleared on refresh and is never written to browser storage.

This optimization saves file-processing work, but not LLM input tokens: the resolved resume text is still included in every generation request.

## Notes
- If OpenAI key is not set, backend uses deterministic mock output so the UI remains testable.
- If an OpenAI request fails while a key is configured, the stream reports an error instead of silently substituting mock content.
- Supported uploaded resume and job-description formats: `.pdf`, `.docx`.
- Max upload size is configurable with `MAX_UPLOAD_BYTES` (default `5242880`, i.e. 5 MB).
- OCR fallback for scanned PDFs is enabled by default (`ENABLE_PDF_OCR_FALLBACK=true`) and uses Tesseract.
- Set `TESSERACT_CMD` only if your environment needs a custom Tesseract binary path.

## Future Improvements

- Better scoring algorithms for skill alignment
- Support for multiple resume versions
- Improved UI/UX for editing generated content
- Deployment (cloud hosting)
- Authentication and user accounts
