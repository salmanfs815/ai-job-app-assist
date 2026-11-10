from typing import Literal

from pydantic import BaseModel, Field

# Upper bound on pasted/extracted text. Roughly 15k tokens per field, which keeps the
# worst-case prompt (and therefore the worst-case cost of one request) bounded.
MAX_TEXT_CHARS = 60_000

OcrStatus = Literal["used", "failed", "not_used"]


class ResumeSuggestionsRequest(BaseModel):
    resume_text: str = Field(min_length=20, max_length=MAX_TEXT_CHARS)
    job_description_text: str = Field(min_length=20, max_length=MAX_TEXT_CHARS)
    tone: str | None = Field(default="professional", max_length=40)


class ResumeExtractResponse(BaseModel):
    resume_text: str
    ocr_status: OcrStatus


class JobDescriptionExtractResponse(BaseModel):
    job_description_text: str
    ocr_status: OcrStatus


class CoverLetterRequest(BaseModel):
    resume_text: str = Field(min_length=20, max_length=MAX_TEXT_CHARS)
    job_description_text: str = Field(min_length=20, max_length=MAX_TEXT_CHARS)
    company_name: str = Field(min_length=2, max_length=200)
    role_title: str = Field(min_length=2, max_length=200)
    tone: str | None = Field(default="professional", max_length=40)
