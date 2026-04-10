from sqlalchemy.orm import Session

from app.db.models import Analysis, CoverLetter


def save_analysis(
    db: Session,
    resume_text: str,
    job_description_text: str,
    extracted_keywords: list[str],
    match_score: int,
    result_payload: dict,
) -> Analysis:
    row = Analysis(
        resume_text=resume_text,
        job_description_text=job_description_text,
        extracted_keywords={"items": extracted_keywords},
        match_score=match_score,
        result_payload=result_payload,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def save_cover_letter(
    db: Session,
    company_name: str,
    role_title: str,
    tone: str,
    generated_text: str,
) -> CoverLetter:
    row = CoverLetter(
        company_name=company_name,
        role_title=role_title,
        tone=tone,
        generated_text=generated_text,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
