# AI Job Application Assistant

A full-stack application that helps automate and improve the process of tailoring job applications by aligning resumes with job descriptions using LLMs.

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

- Accepts resume input (PDF/DOCX or text)
- Parses and extracts structured content
- Analyzes job descriptions for key requirements
- Computes and returns skill/keyword alignment

### 2. Resume Bullet Optimization

- Uses LLM pipelines to rewrite resume bullets
- Aligns experience with job-specific requirements
- Improves clarity and relevance for ATS and recruiters

### 3. Cover Letter Generation

- Generates tailored cover letters based on:
  - resume content
  - job description
- Ensures consistency between resume and narrative

### 4. File Parsing Pipeline

- Supports PDF and DOCX resume uploads
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
PostgreSQL (Persistence)
```

## Tech Stack

**Backend**
- Python
- FastAPI
- PostgreSQL

**Frontend**
- React (Vite)

**AI Integration**
- OpenAI API (LLM)

**DevOps / Tooling**
- Docker
- Docker Compose

## How It Works

1. User uploads a resume (PDF/DOCX) and provides a job description
2. Backend:
  - Parses resume content
  - Extracts job requirements
  - Constructs structured prompts
3. LLM processes:
  - Skill alignment
  - Resume improvements
  - Cover letter generation
4. Backend:
  - Validates and parses responses
  - Returns structured output to frontend

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

## Future Improvements

- Better scoring algorithms for skill alignment
- Support for multiple resume versions
- Improved UI/UX for editing generated content
- Deployment (cloud hosting)
- Authentication and user accounts
