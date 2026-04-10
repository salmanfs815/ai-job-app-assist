from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    resume_text: str = Field(min_length=20)
    job_description_text: str = Field(min_length=20)
    tone: str | None = Field(default="professional")


class RewriteBullet(BaseModel):
    original: str
    tailored: str
    rationale: str


class AnalyzeLLMResult(BaseModel):
    extracted_keywords: list[str]
    matched_skills: list[str]
    missing_skills: list[str]
    rewritten_bullets: list[RewriteBullet]
    summary: str


class AnalyzeResponse(BaseModel):
    extracted_keywords: list[str]
    matched_skills: list[str]
    missing_skills: list[str]
    match_score: int
    rewritten_bullets: list[RewriteBullet]
    suggestions: list[str]
    summary: str


class CoverLetterRequest(BaseModel):
    resume_text: str = Field(min_length=20)
    job_description_text: str = Field(min_length=20)
    company_name: str = Field(min_length=2)
    role_title: str = Field(min_length=2)
    tone: str | None = Field(default="professional")


class CoverLetterResponse(BaseModel):
    cover_letter: str
