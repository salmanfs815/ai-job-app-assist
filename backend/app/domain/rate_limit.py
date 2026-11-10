"""Token-bucket rate limiting (pure logic, no I/O).

State lives in process memory, so the limit is only exact while a single replica
serves traffic (``maxReplicas = 1`` in the Container App). See ADR 0003.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after_seconds: int


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated_at: float


class TokenBucketLimiter:
    """One bucket per key. ``capacity`` is the burst size; ``refill_per_second`` the sustained rate."""

    def __init__(self, *, capacity: int, refill_per_second: float, max_keys: int = 10_000) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        if refill_per_second <= 0:
            raise ValueError("refill_per_second must be positive")
        self._capacity = float(capacity)
        self._refill = refill_per_second
        self._max_keys = max_keys
        self._buckets: dict[str, _Bucket] = {}

    def __len__(self) -> int:
        return len(self._buckets)

    def consume(self, key: str, *, now: float, cost: int = 1) -> RateLimitDecision:
        # A request costing more than the whole bucket could never succeed; clamp it.
        needed = float(min(max(cost, 1), int(self._capacity)))
        bucket = self._buckets.get(key)
        if bucket is None:
            self._evict_if_full(now)
            bucket = _Bucket(tokens=self._capacity, updated_at=now)
            self._buckets[key] = bucket
        else:
            elapsed = max(0.0, now - bucket.updated_at)
            bucket.tokens = min(self._capacity, bucket.tokens + elapsed * self._refill)
            bucket.updated_at = now

        if bucket.tokens >= needed:
            bucket.tokens -= needed
            return RateLimitDecision(allowed=True, remaining=int(bucket.tokens), retry_after_seconds=0)

        wait = (needed - bucket.tokens) / self._refill
        return RateLimitDecision(
            allowed=False,
            remaining=int(bucket.tokens),
            retry_after_seconds=max(1, math.ceil(wait)),
        )

    def _evict_if_full(self, now: float) -> None:
        if len(self._buckets) < self._max_keys:
            return
        # Buckets that have had time to refill completely carry no information.
        full_after = self._capacity / self._refill
        stale = [key for key, bucket in self._buckets.items() if now - bucket.updated_at >= full_after]
        for key in stale:
            del self._buckets[key]
        if len(self._buckets) >= self._max_keys:
            # Still full of active keys: drop the least recently used one.
            oldest = min(self._buckets, key=lambda key: self._buckets[key].updated_at)
            del self._buckets[oldest]
