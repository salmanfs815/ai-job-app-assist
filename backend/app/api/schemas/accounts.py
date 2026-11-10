from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.api.schemas.usage import QuotaResponse
from app.domain.resumes import MAX_RESUME_NAME_CHARS, MAX_RESUME_TEXT_CHARS, MIN_RESUME_TEXT_CHARS, Resume
from app.domain.users import User

OcrStatus = Literal["used", "failed", "not_used"]


class MeResponse(BaseModel):
    id: str
    email: str | None
    displayName: str | None
    roles: list[str]
    createdAt: datetime
    quota: QuotaResponse

    @classmethod
    def from_domain(cls, user: User, roles: frozenset[str], quota: QuotaResponse) -> "MeResponse":
        return cls(
            id=user.id,
            email=user.email,
            displayName=user.display_name,
            roles=sorted(roles),
            createdAt=user.created_at,
            quota=quota,
        )


class AccountDeletedResponse(BaseModel):
    deleted: Literal[True] = True
    resumes: int
    results: int
    usageRecords: int


class ResumeSummary(BaseModel):
    id: str
    name: str
    isDefault: bool
    charCount: int
    sourceFilename: str | None
    ocrStatus: OcrStatus
    version: int
    createdAt: datetime
    updatedAt: datetime

    @classmethod
    def from_domain(cls, resume: Resume) -> "ResumeSummary":
        return cls(**_summary_fields(resume))


class ResumeDetail(ResumeSummary):
    text: str

    @classmethod
    def from_domain(cls, resume: Resume) -> "ResumeDetail":
        return cls(**_summary_fields(resume), text=resume.text)


class ResumeListResponse(BaseModel):
    items: list[ResumeSummary]
    # Always null today (a user has at most a handful of resumes); present so the list
    # contract matches the other paginated endpoints.
    nextCursor: str | None = None


class CreateResumeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_RESUME_NAME_CHARS)
    text: str = Field(min_length=MIN_RESUME_TEXT_CHARS, max_length=MAX_RESUME_TEXT_CHARS)
    sourceFilename: str | None = Field(default=None, max_length=255)
    ocrStatus: OcrStatus = "not_used"
    makeDefault: bool = False


class UpdateResumeRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=MAX_RESUME_NAME_CHARS)
    isDefault: bool | None = None


def _summary_fields(resume: Resume) -> dict[str, object]:
    return {
        "id": resume.id,
        "name": resume.name,
        "isDefault": resume.is_default,
        "charCount": resume.char_count,
        "sourceFilename": resume.source_filename,
        "ocrStatus": resume.ocr_status,
        "version": resume.version,
        "createdAt": resume.created_at,
        "updatedAt": resume.updated_at,
    }
