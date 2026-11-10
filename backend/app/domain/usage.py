"""Usage accounting models and rules for LLM quotas and the global daily budget."""

import hashlib
import math
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum

GLOBAL_OWNER_ID = "global"
GUEST_OWNER_PREFIX = "guest:"

# Cosmos per-item TTLs (seconds). Guest documents are keyed by a salted IP hash, so
# they are kept only as long as the daily counter needs them.
GUEST_USAGE_TTL_SECONDS = 2 * 24 * 60 * 60
USER_USAGE_TTL_SECONDS = 90 * 24 * 60 * 60
GLOBAL_USAGE_TTL_SECONDS = 400 * 24 * 60 * 60


class UsageKind(StrEnum):
    USER = "user"
    GUEST = "guest"
    GLOBAL = "global"


@dataclass(frozen=True, slots=True)
class QuotaSubject:
    """Who a generation is counted against."""

    owner_id: str
    kind: UsageKind


@dataclass(frozen=True, slots=True)
class LLMUsage:
    model: str
    input_tokens: int
    output_tokens: int
    # False when the provider did not report usage and the numbers are estimates.
    reported: bool = True


@dataclass(frozen=True, slots=True)
class UsageRecord:
    """One document per owner per UTC day."""

    owner_id: str
    day: date
    kind: UsageKind
    generations: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    etag: str | None = None

    def with_generations(self, delta: int) -> "UsageRecord":
        return replace(self, generations=max(0, self.generations + delta))

    def with_llm_usage(self, usage: LLMUsage, cost_usd: float) -> "UsageRecord":
        return replace(
            self,
            input_tokens=self.input_tokens + max(usage.input_tokens, 0),
            output_tokens=self.output_tokens + max(usage.output_tokens, 0),
            estimated_cost_usd=round(self.estimated_cost_usd + max(cost_usd, 0.0), 8),
        )

    @property
    def ttl_seconds(self) -> int:
        if self.kind is UsageKind.GUEST:
            return GUEST_USAGE_TTL_SECONDS
        if self.kind is UsageKind.GLOBAL:
            return GLOBAL_USAGE_TTL_SECONDS
        return USER_USAGE_TTL_SECONDS


@dataclass(frozen=True, slots=True)
class QuotaStatus:
    kind: UsageKind
    limit: int
    used: int
    resets_at: datetime

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    @property
    def exhausted(self) -> bool:
        return self.used >= self.limit


@dataclass(frozen=True, slots=True)
class BudgetStatus:
    limit_usd: float
    spent_usd: float
    resets_at: datetime

    @property
    def exhausted(self) -> bool:
        return self.spent_usd >= self.limit_usd


def utc_day(now: datetime) -> date:
    return now.astimezone(UTC).date()


def next_utc_midnight(now: datetime) -> datetime:
    return datetime.combine(utc_day(now) + timedelta(days=1), time.min, tzinfo=UTC)


def seconds_until(now: datetime, target: datetime) -> int:
    """Whole seconds until ``target``, never less than one (for ``Retry-After``)."""
    return max(1, math.ceil((target - now).total_seconds()))


def guest_owner_id(ip_address: str, salt: str) -> str:
    """Stable, non-reversible identifier for a guest. Raw IP addresses are never stored."""
    digest = hashlib.sha256(f"{salt}:{ip_address}".encode()).hexdigest()
    return f"{GUEST_OWNER_PREFIX}{digest[:32]}"


def guest_subject(ip_address: str, salt: str) -> QuotaSubject:
    return QuotaSubject(owner_id=guest_owner_id(ip_address, salt), kind=UsageKind.GUEST)


def user_subject(user_id: str) -> QuotaSubject:
    return QuotaSubject(owner_id=user_id, kind=UsageKind.USER)
