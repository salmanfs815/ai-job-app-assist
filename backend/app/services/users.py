"""User records and account deletion."""

import logging
from dataclasses import dataclass
from datetime import date

from app.auth.principal import Principal
from app.core.clock import Clock, utc_now
from app.domain.usage import utc_day
from app.domain.users import User
from app.repositories.base import ResultsRepository, ResumeRepository, UsageRepository, UserRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DeletionSummary:
    resumes: int
    results: int
    usage_records: int
    account: bool


class UserService:
    def __init__(
        self,
        users: UserRepository,
        resumes: ResumeRepository,
        usage: UsageRepository,
        results: ResultsRepository,
        *,
        clock: Clock = utc_now,
        max_cached_users: int = 5_000,
    ) -> None:
        self._users = users
        self._resumes = resumes
        self._usage = usage
        self._results = results
        self._clock = clock
        # Users already recorded as seen today, so most requests skip the write.
        self._seen_on: dict[str, date] = {}
        self._max_cached_users = max_cached_users

    async def ensure_user(self, principal: Principal) -> User:
        """Return the user's record, creating it on first sign-in.

        ``lastSeenAt`` is refreshed at most once per UTC day per process.
        """
        if not principal.is_user:
            raise ValueError("Only signed-in users have accounts.")
        now = self._clock()
        today = utc_day(now)
        existing = await self._users.get(principal.id)

        if existing is None:
            user = await self._users.upsert(
                User(
                    id=principal.id,
                    email=principal.email,
                    display_name=principal.display_name,
                    created_at=now,
                    last_seen_at=now,
                )
            )
            logger.info("Created user account on first sign-in.", extra={"userId": user.id})
        elif self._seen_on.get(principal.id) != today and utc_day(existing.last_seen_at) != today:
            user = await self._users.upsert(
                existing.seen(now, email=principal.email, display_name=principal.display_name)
            )
        else:
            user = existing

        self._remember(principal.id, today)
        return user

    def _remember(self, user_id: str, today: date) -> None:
        if len(self._seen_on) >= self._max_cached_users and user_id not in self._seen_on:
            self._seen_on.clear()
        self._seen_on[user_id] = today

    async def delete_account(self, user_id: str) -> DeletionSummary:
        """Delete everything stored for a user. The account record goes last so that a
        failure part-way through can simply be retried."""
        resumes = await self._resumes.delete_for_user(user_id)
        results = await self._results.delete_for_user(user_id)
        usage_records = await self._usage.delete_for_owner(user_id)
        account = await self._users.delete(user_id)
        self._seen_on.pop(user_id, None)
        logger.info(
            "Deleted user account and data.",
            extra={"userId": user_id, "resumes": resumes, "results": results, "usageRecords": usage_records},
        )
        return DeletionSummary(resumes=resumes, results=results, usage_records=usage_records, account=account)
