from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.repository import save_analysis, save_cover_letter
from app.models.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    CoverLetterRequest,
    CoverLetterResponse,
)
from app.services.cover_letter import generate_cover_letter
from app.services.matching import build_suggestions, compute_match_score
from app.services.resume_tailor import analyze_resume_against_jd

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(payload: AnalyzeRequest, db: Session = Depends(get_db)) -> AnalyzeResponse:
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
        db=db,
        resume_text=payload.resume_text,
        job_description_text=payload.job_description_text,
        extracted_keywords=response.extracted_keywords,
        match_score=response.match_score,
        result_payload=response.model_dump(),
    )

    return response


@router.post("/cover-letter", response_model=CoverLetterResponse)
def cover_letter(payload: CoverLetterRequest, db: Session = Depends(get_db)) -> CoverLetterResponse:
    text = generate_cover_letter(
        resume_text=payload.resume_text,
        job_description_text=payload.job_description_text,
        company_name=payload.company_name,
        role_title=payload.role_title,
        tone=payload.tone or "professional",
    )

    save_cover_letter(
        db=db,
        company_name=payload.company_name,
        role_title=payload.role_title,
        tone=payload.tone or "professional",
        generated_text=text,
    )

    return CoverLetterResponse(cover_letter=text)
