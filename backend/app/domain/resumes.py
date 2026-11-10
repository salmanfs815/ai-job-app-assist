"""Saved resumes: extracted text and metadata only. Uploaded files are never stored."""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

OcrStatus = Literal["used", "failed", "not_used"]

MIN_RESUME_TEXT_CHARS = 20
MAX_RESUME_TEXT_CHARS = 60_000
MAX_RESUME_NAME_CHARS = 120


class ResumeValidationError(ValueError):
    """The resume breaks a business rule (as opposed to a malformed request)."""


@dataclass(frozen=True, slots=True)
class Resume:
    id: str
    user_id: str
    name: str
    text: str
    is_default: bool
    created_at: datetime
    updated_at: datetime
    source_filename: str | None = None
    ocr_status: OcrStatus = "not_used"
    # Bumped whenever the text changes; scores cached against a resume are keyed by it.
    version: int = 1

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()

    def renamed(self, name: str, now: datetime) -> "Resume":
        return replace(self, name=clean_name(name), updated_at=now)

    def with_default(self, is_default: bool, now: datetime) -> "Resume":
        if self.is_default == is_default:
            return self
        return replace(self, is_default=is_default, updated_at=now)


def clean_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise ResumeValidationError("A resume needs a name.")
    if len(cleaned) > MAX_RESUME_NAME_CHARS:
        raise ResumeValidationError(f"Resume names can be at most {MAX_RESUME_NAME_CHARS} characters.")
    return cleaned


def clean_text(text: str) -> str:
    cleaned = text.strip()
    if len(cleaned) < MIN_RESUME_TEXT_CHARS:
        raise ResumeValidationError("The resume text is too short to be useful.")
    if len(cleaned) > MAX_RESUME_TEXT_CHARS:
        raise ResumeValidationError(f"Resume text can be at most {MAX_RESUME_TEXT_CHARS:,} characters.")
    return cleaned


def sort_for_display(resumes: Sequence[Resume]) -> list[Resume]:
    """Default resume first, then most recently updated."""
    by_recency = sorted(resumes, key=lambda resume: resume.updated_at, reverse=True)
    return sorted(by_recency, key=lambda resume: not resume.is_default)


def next_default(remaining: Sequence[Resume]) -> Resume | None:
    """Which resume becomes the default after the current default is deleted."""
    if not remaining or any(resume.is_default for resume in remaining):
        return None
    return max(remaining, key=lambda resume: resume.updated_at)
