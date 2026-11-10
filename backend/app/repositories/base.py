"""Repository interfaces.

Services depend on these protocols only. Each has an in-memory implementation
(tests, local mode) and a Cosmos DB implementation.
"""

from datetime import date
from typing import Protocol

from app.domain.resumes import Resume
from app.domain.usage import UsageRecord
from app.domain.users import User


class RepositoryError(Exception):
    """Base class for persistence failures."""


class ConcurrencyError(RepositoryError):
    """The document changed (or appeared) since it was read; re-read and retry."""


class RepositoryUnavailableError(RepositoryError):
    """The backing store could not be reached or is not provisioned."""


class UsageRepository(Protocol):
    async def get(self, owner_id: str, day: date) -> UsageRecord | None: ...

    async def create(self, record: UsageRecord) -> UsageRecord:
        """Insert a new record. Raises ``ConcurrencyError`` if one already exists."""
        ...

    async def replace(self, record: UsageRecord) -> UsageRecord:
        """Replace using ``record.etag``. Raises ``ConcurrencyError`` on a mismatch."""
        ...

    async def delete_for_owner(self, owner_id: str) -> int: ...


class ResultsRepository(Protocol):
    async def save_resume_suggestions(
        self,
        *,
        user_id: str | None,
        resume_text: str,
        job_description_text: str,
        tone: str,
        generated_markdown: str,
    ) -> None: ...

    async def save_cover_letter(
        self,
        *,
        user_id: str | None,
        company_name: str,
        role_title: str,
        tone: str,
        generated_text: str,
    ) -> None: ...

    async def delete_for_user(self, user_id: str) -> int: ...


class UserRepository(Protocol):
    async def get(self, user_id: str) -> User | None: ...

    async def upsert(self, user: User) -> User: ...

    async def delete(self, user_id: str) -> bool: ...


class ResumeRepository(Protocol):
    async def list_for_user(self, user_id: str) -> list[Resume]: ...

    async def get(self, user_id: str, resume_id: str) -> Resume | None: ...

    async def upsert(self, resume: Resume) -> Resume: ...

    async def delete(self, user_id: str, resume_id: str) -> bool: ...

    async def delete_for_user(self, user_id: str) -> int: ...
