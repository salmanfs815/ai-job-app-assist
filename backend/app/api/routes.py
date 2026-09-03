import asyncio
from collections.abc import AsyncIterator, Callable

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.config import settings
from app.db.repository import save_cover_letter, save_resume_suggestions
from app.models.schemas import (
    CoverLetterRequest,
    JobDescriptionExtractResponse,
    ResumeExtractResponse,
    ResumeSuggestionsRequest,
)
from app.services.file_parsing import OcrStatus, extract_text_from_resume_file
from app.services.prompt_engineering import build_cover_letter_messages, build_resume_suggestions_messages
from app.services.streaming import (
    LLMStreamError,
    MOCK_COVER_LETTER,
    MOCK_RESUME_SUGGESTIONS,
    sse_event,
    stream_chat_markdown,
)

router = APIRouter()


def _extract_document_upload(upload: UploadFile, document_name: str) -> tuple[str, OcrStatus]:
    content = upload.file.read()
    if not content:
        raise HTTPException(status_code=400, detail=f"Uploaded {document_name} file is empty.")
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"{document_name.capitalize()} file is too large. Max allowed size is {settings.max_upload_bytes} bytes.",
        )
    try:
        parsed, ocr_status = extract_text_from_resume_file(upload.filename or "", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if len(parsed.strip()) < 20:
        raise HTTPException(status_code=400, detail=f"Could not extract enough text from {document_name} file.")
    return parsed.strip(), ocr_status


def _stream_markdown_response(
    request: Request,
    *,
    messages: list[dict[str, str]],
    mock_text: str,
    status_message: str,
    temperature: float,
    persist: Callable[[str], None],
) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        demo = not bool(settings.openai_api_key)
        yield sse_event("status", {"message": status_message, "demo": demo})
        full_text: list[str] = []
        try:
            async for delta in stream_chat_markdown(
                messages,
                temperature=temperature,
                mock_text=mock_text,
            ):
                if await request.is_disconnected():
                    return
                full_text.append(delta)
                yield sse_event("delta", {"text": delta})
        except asyncio.CancelledError:
            raise
        except LLMStreamError as exc:
            yield sse_event(
                "error",
                {
                    "message": str(exc),
                    "retryable": exc.retryable,
                    "partial": bool(full_text),
                },
            )
            return

        completed = "".join(full_text).strip()
        if not completed:
            yield sse_event(
                "error",
                {"message": "OpenAI returned an empty response.", "retryable": True, "partial": False},
            )
            return

        if await request.is_disconnected():
            return
        yield sse_event("status", {"message": "Finalizing and saving your result…", "demo": demo})
        await asyncio.to_thread(persist, completed)
        yield sse_event("done", {"demo": demo})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/resume/extract", response_model=ResumeExtractResponse)
def extract_resume(resume_file: UploadFile = File(...)) -> ResumeExtractResponse:
    resume_text, ocr_status = _extract_document_upload(resume_file, "resume")
    return ResumeExtractResponse(resume_text=resume_text, ocr_status=ocr_status)


@router.post("/job-description/extract", response_model=JobDescriptionExtractResponse)
def extract_job_description(job_description_file: UploadFile = File(...)) -> JobDescriptionExtractResponse:
    job_description_text, ocr_status = _extract_document_upload(job_description_file, "job description")
    return JobDescriptionExtractResponse(job_description_text=job_description_text, ocr_status=ocr_status)


@router.post("/generate/resume-suggestions")
async def generate_resume_suggestions(payload: ResumeSuggestionsRequest, request: Request) -> StreamingResponse:
    tone = payload.tone or "professional"
    messages = build_resume_suggestions_messages(payload.resume_text, payload.job_description_text, tone)
    return _stream_markdown_response(
        request,
        messages=messages,
        mock_text=MOCK_RESUME_SUGGESTIONS,
        status_message="Comparing your resume with the job description…",
        temperature=0.2,
        persist=lambda markdown: save_resume_suggestions(
            resume_text=payload.resume_text,
            job_description_text=payload.job_description_text,
            tone=tone,
            generated_markdown=markdown,
        ),
    )


@router.post("/generate/cover-letter")
async def generate_cover_letter_stream(payload: CoverLetterRequest, request: Request) -> StreamingResponse:
    tone = payload.tone or "professional"
    messages = build_cover_letter_messages(
        payload.resume_text,
        payload.job_description_text,
        payload.company_name,
        payload.role_title,
        tone,
    )
    return _stream_markdown_response(
        request,
        messages=messages,
        mock_text=MOCK_COVER_LETTER,
        status_message="Drafting your tailored cover letter…",
        temperature=0.4,
        persist=lambda markdown: save_cover_letter(
            company_name=payload.company_name,
            role_title=payload.role_title,
            tone=tone,
            generated_text=markdown,
        ),
    )
