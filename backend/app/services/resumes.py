"""Saved resumes: create, list, rename, choose a default, delete."""

import uuid
from collections.abc import Callable

from app.core.clock import Clock, utc_now
from app.domain.resumes import (
    OcrStatus,
    Resume,
    ResumeValidationError,
    clean_name,
    clean_text,
    next_default,
    sort_for_display,
)
from app.repositories.base import ResumeRepository


class ResumeNotFoundError(Exception):
    pass


class ResumeLimitError(Exception):
    def __init__(self, limit: int) -> None:
        super().__init__(f"You can save up to {limit} resumes. Delete one to add another.")
        self.limit = limit


class ResumeService:
    def __init__(
        self,
        repository: ResumeRepository,
        *,
        max_per_user: int,
        clock: Clock = utc_now,
        new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
    ) -> None:
        self._repository = repository
        self._max_per_user = max_per_user
        self._clock = clock
        self._new_id = new_id

    async def list_for_user(self, user_id: str) -> list[Resume]:
        return sort_for_display(await self._repository.list_for_user(user_id))

    async def get(self, user_id: str, resume_id: str) -> Resume:
        resume = await self._repository.get(user_id, resume_id)
        if resume is None:
            raise ResumeNotFoundError(resume_id)
        return resume

    async def create(
        self,
        user_id: str,
        *,
        name: str,
        text: str,
        source_filename: str | None = None,
        ocr_status: OcrStatus = "not_used",
        make_default: bool = False,
    ) -> Resume:
        existing = await self._repository.list_for_user(user_id)
        if len(existing) >= self._max_per_user:
            raise ResumeLimitError(self._max_per_user)

        now = self._clock()
        # The first resume a user saves is their default.
        is_default = make_default or not existing
        resume = Resume(
            id=self._new_id(),
            user_id=user_id,
            name=clean_name(name),
            text=clean_text(text),
            source_filename=(source_filename or "").strip()[:255] or None,
            ocr_status=ocr_status,
            is_default=is_default,
            created_at=now,
            updated_at=now,
        )
        saved = await self._repository.upsert(resume)
        if is_default:
            await self._clear_other_defaults(existing, keep_id=saved.id)
        return saved

    async def update(
        self,
        user_id: str,
        resume_id: str,
        *,
        name: str | None = None,
        is_default: bool | None = None,
    ) -> Resume:
        resume = await self.get(user_id, resume_id)
        now = self._clock()

        if is_default is False and resume.is_default:
            raise ResumeValidationError("Choose another resume as the default instead of unsetting this one.")
        if name is not None:
            resume = resume.renamed(name, now)
        if is_default:
            resume = resume.with_default(True, now)

        saved = await self._repository.upsert(resume)
        if is_default:
            others = [r for r in await self._repository.list_for_user(user_id) if r.id != saved.id]
            await self._clear_other_defaults(others, keep_id=saved.id)
        return saved

    async def delete(self, user_id: str, resume_id: str) -> None:
        if not await self._repository.delete(user_id, resume_id):
            raise ResumeNotFoundError(resume_id)
        promoted = next_default(await self._repository.list_for_user(user_id))
        if promoted is not None:
            await self._repository.upsert(promoted.with_default(True, self._clock()))

    async def _clear_other_defaults(self, resumes: list[Resume], *, keep_id: str) -> None:
        now = self._clock()
        for resume in resumes:
            if resume.is_default and resume.id != keep_id:
                await self._repository.upsert(resume.with_default(False, now))
