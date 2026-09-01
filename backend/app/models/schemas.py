from typing import Literal

from pydantic import BaseModel, Field


class ResumeSuggestionsRequest(BaseModel):
    resume_text: str = Field(min_length=20)
    job_description_text: str = Field(min_length=20)
    tone: str | None = Field(default="professional")


class ResumeExtractResponse(BaseModel):
    resume_text: str
    ocr_status: Literal["used", "failed", "not_used"]


class CoverLetterRequest(BaseModel):
    resume_text: str = Field(min_length=20)
    job_description_text: str = Field(min_length=20)
    company_name: str = Field(min_length=2)
    role_title: str = Field(min_length=2)
    tone: str | None = Field(default="professional")
