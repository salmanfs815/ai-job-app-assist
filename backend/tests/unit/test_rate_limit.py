import pytest

from app.domain.rate_limit import TokenBucketLimiter


def test_allows_a_burst_up_to_capacity_then_rejects() -> None:
    limiter = TokenBucketLimiter(capacity=3, refill_per_second=1)

    decisions = [limiter.consume("ip", now=0.0) for _ in range(4)]

    assert [d.allowed for d in decisions] == [True, True, True, False]
    assert decisions[2].remaining == 0
    assert decisions[3].retry_after_seconds == 1


def test_refills_over_time_without_exceeding_capacity() -> None:
    limiter = TokenBucketLimiter(capacity=2, refill_per_second=0.5)
    limiter.consume("ip", now=0.0)
    limiter.consume("ip", now=0.0)

    assert not limiter.consume("ip", now=1.0).allowed  # only half a token back
    assert limiter.consume("ip", now=2.0).allowed
    # A long idle period refills to capacity, not beyond it.
    assert limiter.consume("ip", now=1000.0).remaining == 1


def test_keys_are_limited_independently() -> None:
    limiter = TokenBucketLimiter(capacity=1, refill_per_second=1)

    assert limiter.consume("a", now=0.0).allowed
    assert not limiter.consume("a", now=0.0).allowed
    assert limiter.consume("b", now=0.0).allowed


def test_expensive_requests_draw_more_tokens_and_report_wait() -> None:
    limiter = TokenBucketLimiter(capacity=10, refill_per_second=2)

    assert limiter.consume("ip", now=0.0, cost=8).remaining == 2
    rejected = limiter.consume("ip", now=0.0, cost=8)

    assert not rejected.allowed
    assert rejected.retry_after_seconds == 3  # needs 6 more tokens at 2/s


def test_cost_larger_than_capacity_is_clamped_so_it_can_succeed() -> None:
    limiter = TokenBucketLimiter(capacity=5, refill_per_second=1)

    assert limiter.consume("ip", now=0.0, cost=50).allowed
    assert not limiter.consume("ip", now=0.0, cost=50).allowed


def test_clock_going_backwards_does_not_remove_tokens() -> None:
    limiter = TokenBucketLimiter(capacity=2, refill_per_second=1)
    limiter.consume("ip", now=10.0)

    assert limiter.consume("ip", now=5.0).allowed


def test_evicts_refilled_buckets_before_active_ones() -> None:
    limiter = TokenBucketLimiter(capacity=1, refill_per_second=1, max_keys=2)
    limiter.consume("old", now=0.0)
    limiter.consume("busy", now=9.5)

    limiter.consume("new", now=10.0)  # "old" has fully refilled and is dropped

    assert len(limiter) == 2
    assert not limiter.consume("busy", now=10.0).allowed  # state for the active key survived


def test_evicts_least_recently_used_when_every_bucket_is_active() -> None:
    limiter = TokenBucketLimiter(capacity=100, refill_per_second=1, max_keys=2)
    limiter.consume("first", now=0.0)
    limiter.consume("second", now=1.0)

    limiter.consume("third", now=2.0)

    assert len(limiter) == 2
    assert limiter.consume("first", now=2.0).remaining == 99  # recreated with a full bucket


@pytest.mark.parametrize(("capacity", "refill"), [(0, 1.0), (1, 0.0), (1, -1.0)])
def test_rejects_invalid_configuration(capacity: int, refill: float) -> None:
    with pytest.raises(ValueError, match="must be"):
        TokenBucketLimiter(capacity=capacity, refill_per_second=refill)
