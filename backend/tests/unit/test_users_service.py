from datetime import UTC, date, datetime

import pytest

from app.auth.principal import Principal, PrincipalKind, guest_principal
from app.domain.resumes import Resume
from app.domain.usage import UsageKind, UsageRecord
from app.domain.users import User
from app.repositories.memory import (
    InMemoryResultsRepository,
    InMemoryResumeRepository,
    InMemoryUsageRepository,
    InMemoryUserRepository,
)
from app.services.users import UserService
from tests.conftest import FakeClock

ALICE = Principal(kind=PrincipalKind.USER, id="alice", email="alice@example.test", display_name="Alice")


class CountingUserRepository(InMemoryUserRepository):
    def __init__(self) -> None:
        super().__init__()
        self.writes = 0

    async def upsert(self, user: User) -> User:
        self.writes += 1
        return await super().upsert(user)


class Stores:
    def __init__(self, clock: FakeClock) -> None:
        self.users = CountingUserRepository()
        self.resumes = InMemoryResumeRepository()
        self.usage = InMemoryUsageRepository()
        self.results = InMemoryResultsRepository()
        self.clock = clock

    def service(self, **options: int) -> UserService:
        return UserService(self.users, self.resumes, self.usage, self.results, clock=self.clock, **options)


async def test_account_is_created_on_first_sign_in(clock: FakeClock) -> None:
    stores = Stores(clock)

    user = await stores.service().ensure_user(ALICE)

    assert user == User(
        id="alice", email="alice@example.test", display_name="Alice", created_at=clock.now, last_seen_at=clock.now
    )
    assert await stores.users.get("alice") == user


async def test_repeat_requests_on_the_same_day_do_not_write(clock: FakeClock) -> None:
    stores = Stores(clock)
    service = stores.service()

    for _ in range(5):
        await service.ensure_user(ALICE)
        clock.advance(minutes=10)

    assert stores.users.writes == 1


async def test_last_seen_and_profile_are_refreshed_once_per_day(clock: FakeClock) -> None:
    stores = Stores(clock)
    service = stores.service()
    created = await service.ensure_user(ALICE)

    clock.advance(days=1)
    renamed = Principal(kind=PrincipalKind.USER, id="alice", email=None, display_name="Alice Example")
    user = await service.ensure_user(renamed)
    await service.ensure_user(renamed)

    assert user.last_seen_at == clock.now
    assert user.created_at == created.created_at
    assert user.display_name == "Alice Example"
    assert user.email == "alice@example.test"  # missing claims never erase stored values
    assert stores.users.writes == 2


async def test_a_fresh_process_does_not_rewrite_users_already_seen_today(clock: FakeClock) -> None:
    stores = Stores(clock)
    await stores.service().ensure_user(ALICE)

    await stores.service().ensure_user(ALICE)  # new service instance = empty in-process cache

    assert stores.users.writes == 1


async def test_seen_cache_is_bounded(clock: FakeClock) -> None:
    stores = Stores(clock)
    service = stores.service(max_cached_users=2)

    for name in ("a", "b", "c"):
        await service.ensure_user(Principal(kind=PrincipalKind.USER, id=name))

    assert len(service._seen_on) == 1


async def test_guests_and_services_have_no_accounts(clock: FakeClock) -> None:
    service = Stores(clock).service()

    with pytest.raises(ValueError, match="Only signed-in users"):
        await service.ensure_user(guest_principal("guest:abc"))


async def test_delete_account_removes_all_user_data_and_nothing_else(clock: FakeClock) -> None:
    stores = Stores(clock)
    service = stores.service()
    now = datetime(2026, 11, 9, tzinfo=UTC)
    for user_id in ("alice", "bob"):
        await service.ensure_user(Principal(kind=PrincipalKind.USER, id=user_id))
        await stores.resumes.upsert(
            Resume(
                id=f"{user_id}-cv",
                user_id=user_id,
                name="CV",
                text="x" * 30,
                is_default=True,
                created_at=now,
                updated_at=now,
            )
        )
        await stores.usage.create(UsageRecord(owner_id=user_id, day=date(2026, 11, 9), kind=UsageKind.USER))
        await stores.results.save_cover_letter(
            user_id=user_id, company_name="Acme", role_title="Engineer", tone="professional", generated_text="Dear"
        )

    summary = await service.delete_account("alice")

    assert (summary.resumes, summary.results, summary.usage_records, summary.account) == (1, 1, 1, True)
    assert await stores.users.get("alice") is None
    assert await stores.resumes.list_for_user("alice") == []
    assert await stores.usage.get("alice", date(2026, 11, 9)) is None
    assert [item["userId"] for item in stores.results.items] == ["bob"]
    # Bob is untouched.
    assert await stores.users.get("bob") is not None
    assert len(await stores.resumes.list_for_user("bob")) == 1
    assert await stores.usage.get("bob", date(2026, 11, 9)) is not None


async def test_delete_account_is_idempotent(clock: FakeClock) -> None:
    service = Stores(clock).service()

    summary = await service.delete_account("nobody")

    assert (summary.resumes, summary.results, summary.usage_records, summary.account) == (0, 0, 0, False)
