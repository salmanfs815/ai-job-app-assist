"""In-memory repositories used by tests, local development and as a degraded fallback."""

from dataclasses import replace
from datetime import date
from itertools import count
from typing import Any

from app.domain.usage import UsageRecord
from app.repositories.base import ConcurrencyError


class InMemoryUsageRepository:
    """Mimics Cosmos optimistic concurrency with a monotonically increasing ETag."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, date], UsageRecord] = {}
        self._etags = count(1)

    def _next_etag(self) -> str:
        return f"etag-{next(self._etags)}"

    async def get(self, owner_id: str, day: date) -> UsageRecord | None:
        return self._records.get((owner_id, day))

    async def create(self, record: UsageRecord) -> UsageRecord:
        key = (record.owner_id, record.day)
        if key in self._records:
            raise ConcurrencyError("usage record already exists")
        stored = replace(record, etag=self._next_etag())
        self._records[key] = stored
        return stored

    async def replace(self, record: UsageRecord) -> UsageRecord:
        key = (record.owner_id, record.day)
        current = self._records.get(key)
        if current is None or current.etag != record.etag:
            raise ConcurrencyError("usage record was modified concurrently")
        stored = replace(record, etag=self._next_etag())
        self._records[key] = stored
        return stored

    async def delete_for_owner(self, owner_id: str) -> int:
        keys = [key for key in self._records if key[0] == owner_id]
        for key in keys:
            del self._records[key]
        return len(keys)


class InMemoryResultsRepository:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    async def save_resume_suggestions(
        self,
        *,
        user_id: str | None,
        resume_text: str,
        job_description_text: str,
        tone: str,
        generated_markdown: str,
    ) -> None:
        self.items.append(
            {
                "type": "resume_suggestions",
                "userId": user_id,
                "resume_text": resume_text,
                "job_description_text": job_description_text,
                "tone": tone,
                "generated_markdown": generated_markdown,
            }
        )

    async def save_cover_letter(
        self,
        *,
        user_id: str | None,
        company_name: str,
        role_title: str,
        tone: str,
        generated_text: str,
    ) -> None:
        self.items.append(
            {
                "type": "cover_letter",
                "userId": user_id,
                "company_name": company_name,
                "role_title": role_title,
                "tone": tone,
                "generated_text": generated_text,
            }
        )

    async def delete_for_user(self, user_id: str) -> int:
        before = len(self.items)
        self.items = [item for item in self.items if item.get("userId") != user_id]
        return before - len(self.items)


class NoopResultsRepository:
    """Used when persistence is disabled: results are streamed to the client and forgotten."""

    async def save_resume_suggestions(self, **_: Any) -> None:
        return None

    async def save_cover_letter(self, **_: Any) -> None:
        return None

    async def delete_for_user(self, user_id: str) -> int:
        return 0
