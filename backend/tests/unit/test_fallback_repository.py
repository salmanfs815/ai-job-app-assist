from datetime import date

from app.domain.usage import UsageKind, UsageRecord, guest_subject
from app.repositories.base import RepositoryUnavailableError
from app.repositories.fallback import FallbackUsageRepository
from app.repositories.memory import InMemoryUsageRepository
from app.services.usage import UsageService

DAY = date(2026, 11, 9)


class FlakyRepository(InMemoryUsageRepository):
    def __init__(self) -> None:
        super().__init__()
        self.available = True
        self.calls = 0

    async def get(self, owner_id: str, day: date) -> UsageRecord | None:
        self.calls += 1
        if not self.available:
            raise RepositoryUnavailableError("down")
        return await super().get(owner_id, day)

    async def create(self, record: UsageRecord) -> UsageRecord:
        if not self.available:
            raise RepositoryUnavailableError("down")
        return await super().create(record)


class ManualTime:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def record(generations: int = 1) -> UsageRecord:
    return UsageRecord(owner_id="u", day=DAY, kind=UsageKind.USER, generations=generations)


async def test_uses_the_primary_store_while_it_is_healthy() -> None:
    primary, fallback = FlakyRepository(), InMemoryUsageRepository()
    repository = FallbackUsageRepository(primary, fallback)

    created = await repository.create(record())
    await repository.replace(created.with_generations(1))

    stored = await primary.get("u", DAY)
    assert stored is not None
    assert stored.generations == 2
    assert await fallback.get("u", DAY) is None
    assert not repository.degraded
    assert await repository.delete_for_owner("u") == 1


async def test_switches_to_memory_when_primary_fails_and_recovers_after_cooldown() -> None:
    primary, fallback, time = FlakyRepository(), InMemoryUsageRepository(), ManualTime()
    repository = FallbackUsageRepository(primary, fallback, retry_after_seconds=60, clock=time)
    primary.available = False

    assert await repository.get("u", DAY) is None
    await repository.create(record())

    assert repository.degraded
    assert (await fallback.get("u", DAY)) is not None
    calls_while_degraded = primary.calls
    await repository.get("u", DAY)
    assert primary.calls == calls_while_degraded  # primary is left alone during the cool-down

    primary.available = True
    time.value = 61.0
    assert await repository.get("u", DAY) is None  # back on the (empty) primary
    assert not repository.degraded


async def test_limits_are_still_enforced_while_degraded() -> None:
    primary = FlakyRepository()
    primary.available = False
    service = UsageService(
        FallbackUsageRepository(primary, InMemoryUsageRepository()),
        user_daily_limit=5,
        guest_daily_limit=2,
        daily_budget_usd=1.0,
    )
    guest = guest_subject("203.0.113.7", "salt")

    await service.reserve_generation(guest)
    await service.reserve_generation(guest)

    assert (await service.quota_status(guest)).remaining == 0
