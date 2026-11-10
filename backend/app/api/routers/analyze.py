"""The original tool: extract text from uploads, then stream tailored suggestions or a cover letter."""

import asyncio

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.api.deps import Container, ToolCaller
from app.api.generation import admit_generation, stream_markdown_response
from app.api.schemas.analyze import (
    CoverLetterRequest,
    JobDescriptionExtractResponse,
    ResumeExtractResponse,
    ResumeSuggestionsRequest,
)
from app.api.schemas.problem import problem_responses
from app.core.settings import Settings
from app.domain.prompts import build_cover_letter_messages, build_resume_suggestions_messages
from app.integrations.llm import MOCK_COVER_LETTER, MOCK_RESUME_SUGGESTIONS
from app.parsing.file_parsing import OcrStatus, extract_text_from_resume_file

router = APIRouter(tags=["analyze"])


def _extract_document_upload(upload: UploadFile, document_name: str, settings: Settings) -> tuple[str, OcrStatus]:
    content = upload.file.read()
    if not content:
        raise HTTPException(status_code=400, detail=f"Uploaded {document_name} file is empty.")
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"{document_name.capitalize()} file is too large. "
                f"Max allowed size is {settings.max_upload_bytes} bytes."
            ),
        )
    try:
        parsed, ocr_status = extract_text_from_resume_file(
            upload.filename or "",
            content,
            enable_ocr=settings.enable_pdf_ocr_fallback,
            tesseract_cmd=settings.tesseract_cmd,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if len(parsed.strip()) < 20:
        raise HTTPException(status_code=400, detail=f"Could not extract enough text from {document_name} file.")
    return parsed.strip(), ocr_status


@router.post(
    "/resume/extract",
    response_model=ResumeExtractResponse,
    responses=problem_responses(400, 401, 413, 429),
)
async def extract_resume(
    container: Container, _caller: ToolCaller, resume_file: UploadFile = File(...)
) -> ResumeExtractResponse:
    # Parsing and OCR are CPU-bound; keep them off the event loop.
    resume_text, ocr_status = await asyncio.to_thread(
        _extract_document_upload, resume_file, "resume", container.settings
    )
    return ResumeExtractResponse(resume_text=resume_text, ocr_status=ocr_status)


@router.post(
    "/job-description/extract",
    response_model=JobDescriptionExtractResponse,
    responses=problem_responses(400, 401, 413, 429),
)
async def extract_job_description(
    container: Container, _caller: ToolCaller, job_description_file: UploadFile = File(...)
) -> JobDescriptionExtractResponse:
    job_description_text, ocr_status = await asyncio.to_thread(
        _extract_document_upload, job_description_file, "job description", container.settings
    )
    return JobDescriptionExtractResponse(job_description_text=job_description_text, ocr_status=ocr_status)


@router.post(
    "/generate/resume-suggestions",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}, **problem_responses(401, 422, 429, 503)},
)
async def generate_resume_suggestions(
    payload: ResumeSuggestionsRequest,
    request: Request,
    container: Container,
    caller: ToolCaller,
) -> StreamingResponse:
    tone = payload.tone or "professional"
    reservation = await admit_generation(container, caller.quota_subject)
    messages = build_resume_suggestions_messages(payload.resume_text, payload.job_description_text, tone)

    async def persist(markdown: str) -> None:
        await container.results.save_resume_suggestions(
            user_id=caller.id,
            resume_text=payload.resume_text,
            job_description_text=payload.job_description_text,
            tone=tone,
            generated_markdown=markdown,
        )

    return stream_markdown_response(
        request,
        container=container,
        reservation=reservation,
        messages=messages,
        mock_text=MOCK_RESUME_SUGGESTIONS,
        status_message="Comparing your resume with the job description…",
        temperature=0.2,
        # Guest results are streamed and forgotten; only signed-in users get history.
        persist=persist if caller.is_user else None,
    )


@router.post(
    "/generate/cover-letter",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}, **problem_responses(401, 422, 429, 503)},
)
async def generate_cover_letter_stream(
    payload: CoverLetterRequest,
    request: Request,
    container: Container,
    caller: ToolCaller,
) -> StreamingResponse:
    tone = payload.tone or "professional"
    reservation = await admit_generation(container, caller.quota_subject)
    messages = build_cover_letter_messages(
        payload.resume_text,
        payload.job_description_text,
        payload.company_name,
        payload.role_title,
        tone,
    )

    async def persist(markdown: str) -> None:
        await container.results.save_cover_letter(
            user_id=caller.id,
            company_name=payload.company_name,
            role_title=payload.role_title,
            tone=tone,
            generated_text=markdown,
        )

    return stream_markdown_response(
        request,
        container=container,
        reservation=reservation,
        messages=messages,
        mock_text=MOCK_COVER_LETTER,
        status_message="Drafting your tailored cover letter…",
        temperature=0.4,
        # Guest results are streamed and forgotten; only signed-in users get history.
        persist=persist if caller.is_user else None,
    )
