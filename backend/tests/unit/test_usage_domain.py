from datetime import UTC, date, datetime, timedelta, timezone

from app.domain.usage import (
    GLOBAL_USAGE_TTL_SECONDS,
    GUEST_USAGE_TTL_SECONDS,
    USER_USAGE_TTL_SECONDS,
    BudgetStatus,
    LLMUsage,
    QuotaStatus,
    UsageKind,
    UsageRecord,
    guest_owner_id,
    guest_subject,
    next_utc_midnight,
    seconds_until,
    user_subject,
    utc_day,
)

NOON = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


def test_day_boundaries_are_utc_regardless_of_input_timezone() -> None:
    late_evening_pacific = datetime(2026, 11, 9, 23, 30, tzinfo=timezone(timedelta(hours=-8)))

    assert utc_day(late_evening_pacific) == date(2026, 11, 10)
    assert next_utc_midnight(late_evening_pacific) == datetime(2026, 11, 11, tzinfo=UTC)


def test_seconds_until_rounds_up_and_is_at_least_one() -> None:
    assert seconds_until(NOON, next_utc_midnight(NOON)) == 12 * 3600
    assert seconds_until(NOON, NOON + timedelta(milliseconds=200)) == 1
    assert seconds_until(NOON, NOON - timedelta(hours=1)) == 1


def test_guest_ids_are_stable_salted_and_do_not_contain_the_ip() -> None:
    first = guest_owner_id("203.0.113.7", "salt-a")

    assert first == guest_owner_id("203.0.113.7", "salt-a")
    assert first != guest_owner_id("203.0.113.7", "salt-b")
    assert first != guest_owner_id("203.0.113.8", "salt-a")
    assert first.startswith("guest:")
    assert "203.0.113.7" not in first


def test_subject_helpers() -> None:
    assert guest_subject("203.0.113.7", "s").kind is UsageKind.GUEST
    assert user_subject("user-1").owner_id == "user-1"
    assert user_subject("user-1").kind is UsageKind.USER


def test_record_accumulates_and_never_goes_negative() -> None:
    record = UsageRecord(owner_id="u", day=date(2026, 11, 9), kind=UsageKind.USER)

    record = record.with_generations(1).with_llm_usage(LLMUsage("gpt-4.1-mini", 100, 50), 0.001)
    record = record.with_llm_usage(LLMUsage("gpt-4.1-mini", -10, 25), -1.0)

    assert (record.generations, record.input_tokens, record.output_tokens) == (1, 100, 75)
    assert record.estimated_cost_usd == 0.001
    assert record.with_generations(-5).generations == 0


def test_ttl_depends_on_kind() -> None:
    def ttl(kind: UsageKind) -> int:
        return UsageRecord(owner_id="x", day=date(2026, 11, 9), kind=kind).ttl_seconds

    assert ttl(UsageKind.GUEST) == GUEST_USAGE_TTL_SECONDS
    assert ttl(UsageKind.USER) == USER_USAGE_TTL_SECONDS
    assert ttl(UsageKind.GLOBAL) == GLOBAL_USAGE_TTL_SECONDS
    assert ttl(UsageKind.GUEST) < ttl(UsageKind.USER)


def test_status_helpers() -> None:
    quota = QuotaStatus(kind=UsageKind.GUEST, limit=3, used=5, resets_at=NOON)
    assert quota.remaining == 0
    assert quota.exhausted
    assert not QuotaStatus(kind=UsageKind.GUEST, limit=3, used=2, resets_at=NOON).exhausted

    assert BudgetStatus(limit_usd=1.0, spent_usd=1.0, resets_at=NOON).exhausted
    assert not BudgetStatus(limit_usd=1.0, spent_usd=0.99, resets_at=NOON).exhausted
