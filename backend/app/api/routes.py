from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile

from app.config import settings
from app.db.repository import save_analysis, save_cover_letter
from app.models.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    CoverLetterRequest,
    CoverLetterResponse,
)
from app.services.cover_letter import generate_cover_letter
from app.services.file_parsing import OcrStatus, extract_text_from_resume_file
from app.services.matching import build_suggestions, compute_match_score
from app.services.resume_tailor import analyze_resume_against_jd

router = APIRouter()


def _resolve_resume_text(resume_text: str | None, resume_file: UploadFile | None) -> tuple[str, OcrStatus]:
    if resume_file is not None:
        content = resume_file.file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded resume file is empty.")
        if len(content) > settings.max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Resume file is too large. Max allowed size is {settings.max_upload_bytes} bytes.",
            )
        try:
            parsed, ocr_status = extract_text_from_resume_file(resume_file.filename or "", content)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if len(parsed.strip()) < 20:
            if resume_text and len(resume_text.strip()) >= 20:
                return resume_text.strip(), "failed"
            raise HTTPException(status_code=400, detail="Could not extract enough text from resume file.")
        return parsed, ocr_status

    if resume_text and len(resume_text.strip()) >= 20:
        return resume_text.strip(), "not_used"

    raise HTTPException(status_code=400, detail="Provide either resume_text or a PDF/DOCX resume_file.")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(payload: AnalyzeRequest) -> AnalyzeResponse:
    llm_result = analyze_resume_against_jd(payload.resume_text, payload.job_description_text, payload.tone or "professional")
    score = compute_match_score(llm_result.matched_skills, llm_result.missing_skills, llm_result.extracted_keywords)
    suggestions = build_suggestions(llm_result.missing_skills, llm_result.rewritten_bullets)

    response = AnalyzeResponse(
        extracted_keywords=llm_result.extracted_keywords,
        matched_skills=llm_result.matched_skills,
        missing_skills=llm_result.missing_skills,
        match_score=score,
        rewritten_bullets=llm_result.rewritten_bullets,
        suggestions=suggestions,
        summary=llm_result.summary,
    )

    save_analysis(
        resume_text=payload.resume_text,
        job_description_text=payload.job_description_text,
        extracted_keywords=response.extracted_keywords,
        match_score=response.match_score,
        result_payload=response.model_dump(),
    )

    return response


@router.post("/analyze-upload", response_model=AnalyzeResponse)
def analyze_upload(
    job_description_text: str = Form(...),
    tone: str = Form("professional"),
    resume_text: str | None = Form(None),
    resume_file: UploadFile | None = File(None),
    http_response: Response = None,
) -> AnalyzeResponse:
    resolved_resume, ocr_status = _resolve_resume_text(resume_text, resume_file)
    if http_response is not None:
        http_response.headers["X-Resume-OCR-Status"] = ocr_status
    if len(job_description_text.strip()) < 20:
        raise HTTPException(status_code=400, detail="job_description_text must be at least 20 characters.")

    llm_result = analyze_resume_against_jd(resolved_resume, job_description_text, tone or "professional")
    score = compute_match_score(llm_result.matched_skills, llm_result.missing_skills, llm_result.extracted_keywords)
    suggestions = build_suggestions(llm_result.missing_skills, llm_result.rewritten_bullets)

    api_response = AnalyzeResponse(
        extracted_keywords=llm_result.extracted_keywords,
        matched_skills=llm_result.matched_skills,
        missing_skills=llm_result.missing_skills,
        match_score=score,
        rewritten_bullets=llm_result.rewritten_bullets,
        suggestions=suggestions,
        summary=llm_result.summary,
    )

    save_analysis(
        resume_text=resolved_resume,
        job_description_text=job_description_text,
        extracted_keywords=api_response.extracted_keywords,
        match_score=api_response.match_score,
        result_payload=api_response.model_dump(),
    )

    return api_response


@router.post("/cover-letter", response_model=CoverLetterResponse)
def cover_letter(payload: CoverLetterRequest) -> CoverLetterResponse:
    text = generate_cover_letter(
        resume_text=payload.resume_text,
        job_description_text=payload.job_description_text,
        company_name=payload.company_name,
        role_title=payload.role_title,
        tone=payload.tone or "professional",
    )

    save_cover_letter(
        company_name=payload.company_name,
        role_title=payload.role_title,
        tone=payload.tone or "professional",
        generated_text=text,
    )

    return CoverLetterResponse(cover_letter=text)


@router.post("/cover-letter-upload", response_model=CoverLetterResponse)
def cover_letter_upload(
    job_description_text: str = Form(...),
    company_name: str = Form(...),
    role_title: str = Form(...),
    tone: str = Form("professional"),
    resume_text: str | None = Form(None),
    resume_file: UploadFile | None = File(None),
    http_response: Response = None,
) -> CoverLetterResponse:
    resolved_resume, ocr_status = _resolve_resume_text(resume_text, resume_file)
    if http_response is not None:
        http_response.headers["X-Resume-OCR-Status"] = ocr_status
    if len(job_description_text.strip()) < 20:
        raise HTTPException(status_code=400, detail="job_description_text must be at least 20 characters.")
    if len(company_name.strip()) < 2 or len(role_title.strip()) < 2:
        raise HTTPException(status_code=400, detail="company_name and role_title are required.")

    text = generate_cover_letter(
        resume_text=resolved_resume,
        job_description_text=job_description_text,
        company_name=company_name,
        role_title=role_title,
        tone=tone or "professional",
    )

    save_cover_letter(
        company_name=company_name,
        role_title=role_title,
        tone=tone or "professional",
        generated_text=text,
    )

    return CoverLetterResponse(cover_letter=text)
