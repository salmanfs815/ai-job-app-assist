"""Keeps limits enforced when the durable usage store is unavailable.

If Cosmos DB cannot be reached (or the ``usage`` container has not been provisioned
yet) counters fall back to process memory instead of failing open (no limits) or
failing closed (no demo). The primary store is retried after a cool-down.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import date
from typing import TypeVar

from app.core.clock import Monotonic, monotonic
from app.domain.usage import UsageRecord
from app.repositories.base import RepositoryUnavailableError, UsageRepository

logger = logging.getLogger(__name__)

T = TypeVar("T")


class FallbackUsageRepository:
    def __init__(
        self,
        primary: UsageRepository,
        fallback: UsageRepository,
        *,
        retry_after_seconds: float = 60.0,
        clock: Monotonic = monotonic,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._retry_after = retry_after_seconds
        self._clock = clock
        self._degraded_until: float | None = None

    @property
    def degraded(self) -> bool:
        return self._degraded_until is not None and self._clock() < self._degraded_until

    async def _call(
        self,
        primary_call: Callable[[], Awaitable[T]],
        fallback_call: Callable[[], Awaitable[T]],
    ) -> T:
        if self.degraded:
            return await fallback_call()
        try:
            result = await primary_call()
        except RepositoryUnavailableError:
            logger.warning(
                "Usage store unavailable; enforcing limits from process memory for %.0f seconds.",
                self._retry_after,
                exc_info=True,
            )
            self._degraded_until = self._clock() + self._retry_after
            return await fallback_call()
        self._degraded_until = None
        return result

    async def get(self, owner_id: str, day: date) -> UsageRecord | None:
        return await self._call(lambda: self._primary.get(owner_id, day), lambda: self._fallback.get(owner_id, day))

    async def create(self, record: UsageRecord) -> UsageRecord:
        return await self._call(lambda: self._primary.create(record), lambda: self._fallback.create(record))

    async def replace(self, record: UsageRecord) -> UsageRecord:
        return await self._call(lambda: self._primary.replace(record), lambda: self._fallback.replace(record))

    async def delete_for_owner(self, owner_id: str) -> int:
        return await self._call(
            lambda: self._primary.delete_for_owner(owner_id),
            lambda: self._fallback.delete_for_owner(owner_id),
        )
