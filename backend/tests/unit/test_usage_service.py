from datetime import UTC, date, datetime

import pytest

from app.domain.pricing import ModelPrice
from app.domain.usage import GLOBAL_OWNER_ID, LLMUsage, UsageRecord, guest_subject, user_subject
from app.repositories.base import ConcurrencyError
from app.repositories.memory import InMemoryUsageRepository
from app.services.usage import BudgetExceededError, QuotaExceededError, UsageService
from tests.conftest import FakeClock

USER = user_subject("user-1")
GUEST = guest_subject("203.0.113.7", "salt")
TODAY = date(2026, 11, 9)
USAGE = LLMUsage(model="gpt-4.1-mini", input_tokens=1_000_000, output_tokens=250_000)  # $0.40 + $0.40


def make_service(
    clock: FakeClock,
    repository: InMemoryUsageRepository | None = None,
    **overrides: object,
) -> tuple[UsageService, InMemoryUsageRepository]:
    repository = repository or InMemoryUsageRepository()
    options: dict[str, object] = {
        "user_daily_limit": 3,
        "guest_daily_limit": 1,
        "daily_budget_usd": 1.0,
        "clock": clock,
    }
    options.update(overrides)
    return UsageService(repository, **options), repository  # type: ignore[arg-type]


class RacingRepository(InMemoryUsageRepository):
    """Simulates another request winning the race a number of times."""

    def __init__(self, conflicts: int) -> None:
        super().__init__()
        self.conflicts = conflicts
        self.attempts = 0

    async def _race(self) -> None:
        self.attempts += 1
        if self.conflicts > 0:
            self.conflicts -= 1
            raise ConcurrencyError("lost the race")

    async def create(self, record: UsageRecord) -> UsageRecord:
        await self._race()
        return await super().create(record)

    async def replace(self, record: UsageRecord) -> UsageRecord:
        await self._race()
        return await super().replace(record)


async def test_user_can_generate_up_to_the_daily_limit(clock: FakeClock) -> None:
    service, _ = make_service(clock)

    used = [(await service.reserve_generation(USER)).status.used for _ in range(3)]
    with pytest.raises(QuotaExceededError) as excinfo:
        await service.reserve_generation(USER)

    assert used == [1, 2, 3]
    assert excinfo.value.status.limit == 3
    assert excinfo.value.status.used == 3
    assert excinfo.value.status.resets_at == datetime(2026, 11, 10, tzinfo=UTC)
    # The rejected attempt is not counted.
    assert (await service.quota_status(USER)).used == 3


async def test_guests_have_their_own_smaller_limit_per_address(clock: FakeClock) -> None:
    service, _ = make_service(clock)
    other_guest = guest_subject("203.0.113.8", "salt")

    await service.reserve_generation(GUEST)
    with pytest.raises(QuotaExceededError):
        await service.reserve_generation(GUEST)

    # Another address and signed-in users are unaffected.
    assert (await service.reserve_generation(other_guest)).status.remaining == 0
    assert (await service.reserve_generation(USER)).status.remaining == 2


async def test_quota_resets_at_utc_midnight(clock: FakeClock) -> None:
    service, _ = make_service(clock)
    await service.reserve_generation(GUEST)

    clock.advance(hours=12)

    status = await service.quota_status(GUEST)
    assert status.used == 0
    assert status.resets_at == datetime(2026, 11, 11, tzinfo=UTC)
    await service.reserve_generation(GUEST)


async def test_zero_limit_disables_generation(clock: FakeClock) -> None:
    service, _ = make_service(clock, guest_daily_limit=0)

    with pytest.raises(QuotaExceededError):
        await service.reserve_generation(GUEST)


async def test_release_hands_the_generation_back(clock: FakeClock) -> None:
    service, _ = make_service(clock)
    reservation = await service.reserve_generation(GUEST)

    await service.release_generation(reservation)

    assert (await service.quota_status(GUEST)).used == 0
    await service.reserve_generation(GUEST)


async def test_release_never_raises(clock: FakeClock) -> None:
    repository = RacingRepository(conflicts=0)
    service, _ = make_service(clock, repository)
    reservation = await service.reserve_generation(GUEST)
    repository.conflicts = 100

    await service.release_generation(reservation)  # swallowed and logged


async def test_recording_usage_updates_owner_and_global_budget(clock: FakeClock) -> None:
    service, repository = make_service(clock)
    reservation = await service.reserve_generation(USER)

    cost = await service.record_llm_usage(reservation, USAGE, billable=True)

    assert cost == pytest.approx(0.80)
    owner = await repository.get(USER.owner_id, TODAY)
    total = await repository.get(GLOBAL_OWNER_ID, TODAY)
    assert owner is not None
    assert total is not None
    assert (owner.generations, owner.input_tokens, owner.output_tokens) == (1, 1_000_000, 250_000)
    assert owner.estimated_cost_usd == pytest.approx(0.80)
    assert (total.generations, total.estimated_cost_usd) == (1, pytest.approx(0.80))
    assert (await service.budget_status()).spent_usd == pytest.approx(0.80)


async def test_budget_blocks_once_spent_and_resets_next_utc_day(clock: FakeClock) -> None:
    service, _ = make_service(clock)
    await service.ensure_budget_available()
    for _ in range(2):  # 2 x $0.80 > $1.00
        await service.record_llm_usage(await service.reserve_generation(USER), USAGE, billable=True)

    with pytest.raises(BudgetExceededError) as excinfo:
        await service.ensure_budget_available()
    assert excinfo.value.status.spent_usd == pytest.approx(1.60)
    assert excinfo.value.status.resets_at == datetime(2026, 11, 10, tzinfo=UTC)

    clock.advance(hours=12)
    assert not (await service.ensure_budget_available()).exhausted


async def test_mock_usage_records_tokens_but_costs_nothing(clock: FakeClock) -> None:
    service, repository = make_service(clock)
    reservation = await service.reserve_generation(GUEST)

    cost = await service.record_llm_usage(reservation, USAGE, billable=False)

    assert cost == 0
    owner = await repository.get(GUEST.owner_id, TODAY)
    assert owner is not None
    assert owner.input_tokens == 1_000_000
    assert (await service.budget_status()).spent_usd == 0


async def test_usage_is_recorded_on_the_day_it_was_reserved(clock: FakeClock) -> None:
    clock.now = datetime(2026, 11, 9, 23, 59, 50, tzinfo=UTC)
    service, repository = make_service(clock)
    reservation = await service.reserve_generation(USER)

    clock.advance(seconds=30)  # the stream finishes after midnight
    await service.record_llm_usage(reservation, USAGE, billable=True)

    assert await repository.get(USER.owner_id, date(2026, 11, 10)) is None
    yesterday = await repository.get(USER.owner_id, TODAY)
    assert yesterday is not None
    assert yesterday.input_tokens == 1_000_000


async def test_price_override_is_used_for_cost(clock: FakeClock) -> None:
    service, _ = make_service(clock, price_override=ModelPrice(10.0, 0.0))

    assert service.estimate_cost(USAGE) == pytest.approx(10.0)


async def test_concurrent_updates_are_retried_and_not_lost(clock: FakeClock) -> None:
    repository = RacingRepository(conflicts=3)
    service, _ = make_service(clock, repository)

    reservation = await service.reserve_generation(USER)

    assert reservation.status.used == 1
    assert repository.attempts == 4


async def test_gives_up_after_too_many_conflicts(clock: FakeClock) -> None:
    repository = RacingRepository(conflicts=100)
    service, _ = make_service(clock, repository, max_attempts=3)

    with pytest.raises(ConcurrencyError, match="3 attempts"):
        await service.reserve_generation(USER)
    assert repository.attempts == 3


async def test_delete_for_owner_removes_only_that_owner(clock: FakeClock) -> None:
    service, repository = make_service(clock)
    await service.reserve_generation(USER)
    await service.reserve_generation(GUEST)

    assert await service.delete_for_owner(USER.owner_id) == 1
    assert await repository.get(USER.owner_id, TODAY) is None
    assert await repository.get(GUEST.owner_id, TODAY) is not None
