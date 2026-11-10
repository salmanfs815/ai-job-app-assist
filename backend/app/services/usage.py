"""LLM quotas and the global daily spend guard.

* Each signed-in user and each guest (by salted IP hash) gets a number of generations
  per UTC day.
* All LLM calls together may not exceed an estimated USD budget per UTC day.

Counters are updated with optimistic concurrency (ETags) so concurrent requests
cannot lose updates.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from app.core.clock import Clock, utc_now
from app.domain.pricing import ModelPrice, estimate_cost_usd, price_for_model
from app.domain.usage import (
    GLOBAL_OWNER_ID,
    BudgetStatus,
    LLMUsage,
    QuotaStatus,
    QuotaSubject,
    UsageKind,
    UsageRecord,
    next_utc_midnight,
    utc_day,
)
from app.repositories.base import ConcurrencyError, UsageRepository

logger = logging.getLogger(__name__)


class QuotaExceededError(Exception):
    def __init__(self, status: QuotaStatus) -> None:
        super().__init__(f"Daily generation limit of {status.limit} reached")
        self.status = status


class BudgetExceededError(Exception):
    def __init__(self, status: BudgetStatus) -> None:
        super().__init__("Daily LLM budget reached")
        self.status = status


@dataclass(frozen=True, slots=True)
class Reservation:
    """A generation that has been counted and may be handed back if nothing was produced."""

    subject: QuotaSubject
    day: date
    status: QuotaStatus


class UsageService:
    def __init__(
        self,
        repository: UsageRepository,
        *,
        user_daily_limit: int,
        guest_daily_limit: int,
        daily_budget_usd: float,
        price_override: ModelPrice | None = None,
        clock: Clock = utc_now,
        max_attempts: int = 8,
    ) -> None:
        self._repository = repository
        self._user_daily_limit = user_daily_limit
        self._guest_daily_limit = guest_daily_limit
        self._daily_budget_usd = daily_budget_usd
        self._price_override = price_override
        self._clock = clock
        self._max_attempts = max_attempts

    # --- Quotas ----------------------------------------------------------------------

    def limit_for(self, kind: UsageKind) -> int:
        return self._user_daily_limit if kind is UsageKind.USER else self._guest_daily_limit

    async def quota_status(self, subject: QuotaSubject) -> QuotaStatus:
        now = self._clock()
        record = await self._repository.get(subject.owner_id, utc_day(now))
        return QuotaStatus(
            kind=subject.kind,
            limit=self.limit_for(subject.kind),
            used=record.generations if record else 0,
            resets_at=next_utc_midnight(now),
        )

    async def reserve_generation(self, subject: QuotaSubject) -> Reservation:
        """Count one generation against ``subject`` or raise ``QuotaExceededError``."""
        now = self._clock()
        day = utc_day(now)
        limit = self.limit_for(subject.kind)
        resets_at = next_utc_midnight(now)

        def reserve(record: UsageRecord) -> UsageRecord:
            if record.generations >= limit:
                raise QuotaExceededError(
                    QuotaStatus(kind=subject.kind, limit=limit, used=record.generations, resets_at=resets_at)
                )
            return record.with_generations(1)

        updated = await self._mutate(subject.owner_id, subject.kind, day, reserve)
        return Reservation(
            subject=subject,
            day=day,
            status=QuotaStatus(kind=subject.kind, limit=limit, used=updated.generations, resets_at=resets_at),
        )

    async def release_generation(self, reservation: Reservation) -> None:
        """Hand a reservation back, e.g. when the provider failed before producing output."""
        try:
            await self._mutate(
                reservation.subject.owner_id,
                reservation.subject.kind,
                reservation.day,
                lambda record: record.with_generations(-1),
            )
        except Exception:
            # Failing to refund must never mask the original error.
            logger.warning("Could not release a generation reservation.", exc_info=True)

    # --- Budget ----------------------------------------------------------------------

    async def budget_status(self) -> BudgetStatus:
        now = self._clock()
        record = await self._repository.get(GLOBAL_OWNER_ID, utc_day(now))
        return BudgetStatus(
            limit_usd=self._daily_budget_usd,
            spent_usd=record.estimated_cost_usd if record else 0.0,
            resets_at=next_utc_midnight(now),
        )

    async def ensure_budget_available(self) -> BudgetStatus:
        status = await self.budget_status()
        if status.exhausted:
            raise BudgetExceededError(status)
        return status

    def estimate_cost(self, usage: LLMUsage) -> float:
        price = price_for_model(usage.model, self._price_override)
        return estimate_cost_usd(usage.input_tokens, usage.output_tokens, price)

    async def record_llm_usage(self, reservation: Reservation, usage: LLMUsage, *, billable: bool) -> float:
        """Add token usage to the owner's record and its cost to the global budget.

        ``billable`` is false in mock mode: tokens are still recorded, cost is zero.
        Returns the estimated cost in USD.
        """
        cost = self.estimate_cost(usage) if billable else 0.0
        subject = reservation.subject
        await self._mutate(
            subject.owner_id, subject.kind, reservation.day, lambda record: record.with_llm_usage(usage, cost)
        )
        await self._mutate(
            GLOBAL_OWNER_ID,
            UsageKind.GLOBAL,
            reservation.day,
            lambda record: record.with_llm_usage(usage, cost).with_generations(1),
        )
        return cost

    # --- Account deletion ------------------------------------------------------------

    async def delete_for_owner(self, owner_id: str) -> int:
        return await self._repository.delete_for_owner(owner_id)

    # --- Internals -------------------------------------------------------------------

    async def _mutate(
        self,
        owner_id: str,
        kind: UsageKind,
        day: date,
        change: Callable[[UsageRecord], UsageRecord],
    ) -> UsageRecord:
        for _ in range(self._max_attempts):
            current = await self._repository.get(owner_id, day)
            try:
                if current is None:
                    return await self._repository.create(change(UsageRecord(owner_id=owner_id, day=day, kind=kind)))
                return await self._repository.replace(change(current))
            except ConcurrencyError:
                continue
        raise ConcurrencyError(f"could not update usage after {self._max_attempts} attempts")
