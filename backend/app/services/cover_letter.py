from app.services.llm_client import call_llm_text
from app.services.prompt_engineering import build_cover_letter_prompt


def generate_cover_letter(
    resume_text: str,
    job_description_text: str,
    company_name: str,
    role_title: str,
    tone: str,
) -> str:
    prompt = build_cover_letter_prompt(
        resume_text=resume_text,
        jd_text=job_description_text,
        company_name=company_name,
        role_title=role_title,
        tone=tone,
    )
    return call_llm_text(prompt)
