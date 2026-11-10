"""Cosmos repositories against an in-process fake of the SDK container.

The fake reproduces the behaviours the repositories depend on: ETag checks, 404/409/412
errors, partition-scoped queries and a missing container. Running the same tests against
the Cosmos emulator is documented in docs/setup/local-development.md.
"""

from datetime import UTC, date, datetime
from itertools import count
from typing import Any

import pytest
from azure.core import MatchConditions
from azure.cosmos.exceptions import (
    CosmosAccessConditionFailedError,
    CosmosHttpResponseError,
    CosmosResourceExistsError,
    CosmosResourceNotFoundError,
)

from app.domain.resumes import Resume
from app.domain.usage import UsageKind, UsageRecord
from app.domain.users import User
from app.repositories.base import ConcurrencyError, RepositoryUnavailableError
from app.repositories.cosmos import CosmosContainers, CosmosResultsRepository, CosmosUsageRepository
from app.repositories.cosmos_accounts import CosmosResumeRepository, CosmosUserRepository

DAY = date(2026, 11, 9)
NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


class FakeContainer:
    def __init__(self, partition_key: str) -> None:
        self.partition_key = partition_key
        self.items: dict[tuple[str, str], dict[str, Any]] = {}
        self.missing = False
        self.fail_with: Exception | None = None
        self._etags = count(1)

    def _check(self) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        if self.missing:
            error = CosmosResourceNotFoundError(message="Owner resource does not exist")
            error.sub_status = 1003
            raise error

    def _store(self, body: dict[str, Any]) -> dict[str, Any]:
        stored = {**body, "_etag": f'"{next(self._etags)}"'}
        self.items[(body[self.partition_key], body["id"])] = stored
        return dict(stored)

    def read_item(self, item: str, partition_key: str) -> dict[str, Any]:
        self._check()
        try:
            return dict(self.items[(partition_key, item)])
        except KeyError:
            raise CosmosResourceNotFoundError(message="Entity with the specified id does not exist") from None

    def create_item(self, body: dict[str, Any]) -> dict[str, Any]:
        self._check()
        if (body[self.partition_key], body["id"]) in self.items:
            raise CosmosResourceExistsError(message="Conflict")
        return self._store(body)

    def upsert_item(self, body: dict[str, Any]) -> dict[str, Any]:
        self._check()
        return self._store(body)

    def replace_item(
        self, item: str, body: dict[str, Any], etag: str | None = None, match_condition: Any = None
    ) -> dict[str, Any]:
        self._check()
        current = self.items.get((body[self.partition_key], item))
        if current is None:
            raise CosmosResourceNotFoundError(message="Entity with the specified id does not exist")
        if match_condition is MatchConditions.IfNotModified and current["_etag"] != etag:
            raise CosmosAccessConditionFailedError(message="Precondition failed")
        return self._store(body)

    def delete_item(self, item: str, partition_key: str) -> None:
        self._check()
        if self.items.pop((partition_key, item), None) is None:
            raise CosmosResourceNotFoundError(message="Entity with the specified id does not exist")

    def query_items(self, query: str, parameters: list[dict[str, Any]], **options: Any) -> list[dict[str, Any]]:
        self._check()
        value = parameters[0]["value"]
        if "partition_key" in options:
            assert options["partition_key"] == value
        else:
            assert options.get("enable_cross_partition_query") is True
        return [dict(item) for item in self.items.values() if item.get("userId") == value]


class FakeContainers:
    def __init__(self, **containers: FakeContainer) -> None:
        self._containers = containers

    def container(self, name: str) -> FakeContainer:
        return self._containers[name]


def usage_record(owner: str = "alice", generations: int = 1) -> UsageRecord:
    return UsageRecord(owner_id=owner, day=DAY, kind=UsageKind.GUEST, generations=generations, input_tokens=5)


def make_resume(resume_id: str, user_id: str = "alice") -> Resume:
    return Resume(
        id=resume_id,
        user_id=user_id,
        name="CV",
        text="Backend engineer with Python experience.",
        is_default=True,
        source_filename="cv.pdf",
        ocr_status="used",
        version=3,
        created_at=NOW,
        updated_at=NOW,
    )


# --- usage -------------------------------------------------------------------------------


@pytest.fixture
def usage() -> tuple[CosmosUsageRepository, FakeContainer]:
    container = FakeContainer("userId")
    return CosmosUsageRepository(FakeContainers(usage=container), "usage"), container  # type: ignore[arg-type]


async def test_usage_round_trip_and_document_shape(usage: tuple[CosmosUsageRepository, FakeContainer]) -> None:
    repository, container = usage

    created = await repository.create(usage_record())

    assert created.etag is not None
    assert await repository.get("alice", DAY) == created
    assert await repository.get("alice", date(2026, 11, 10)) is None
    document = container.items[("alice", "2026-11-09")]
    assert document["kind"] == "guest"
    assert document["ttl"] == 2 * 24 * 60 * 60  # guest documents expire quickly
    assert (document["generations"], document["inputTokens"]) == (1, 5)


async def test_usage_create_conflict_and_etag_mismatch(usage: tuple[CosmosUsageRepository, FakeContainer]) -> None:
    repository, _ = usage
    created = await repository.create(usage_record())

    with pytest.raises(ConcurrencyError):
        await repository.create(usage_record())

    updated = await repository.replace(created.with_generations(1))
    assert updated.generations == 2
    with pytest.raises(ConcurrencyError):
        await repository.replace(created.with_generations(1))  # stale ETag: another writer won
    with pytest.raises(ConcurrencyError):
        await repository.replace(usage_record("nobody"))


async def test_usage_delete_for_owner(usage: tuple[CosmosUsageRepository, FakeContainer]) -> None:
    repository, _ = usage
    await repository.create(usage_record("alice"))
    await repository.create(usage_record("bob"))

    assert await repository.delete_for_owner("alice") == 1
    assert await repository.get("alice", DAY) is None
    assert await repository.get("bob", DAY) is not None


async def test_missing_container_and_outages_are_reported_as_unavailable(
    usage: tuple[CosmosUsageRepository, FakeContainer],
) -> None:
    repository, container = usage
    container.missing = True
    with pytest.raises(RepositoryUnavailableError, match="does not exist"):
        await repository.get("alice", DAY)
    with pytest.raises(RepositoryUnavailableError, match="does not exist"):
        await repository.create(usage_record())

    container.missing = False
    container.fail_with = CosmosHttpResponseError(status_code=503, message="Service unavailable")
    with pytest.raises(RepositoryUnavailableError, match="503"):
        await repository.get("alice", DAY)
    container.fail_with = ConnectionError("dns")
    with pytest.raises(RepositoryUnavailableError, match="unreachable"):
        await repository.get("alice", DAY)


# --- users and resumes -------------------------------------------------------------------


async def test_user_round_trip() -> None:
    container = FakeContainer("id")
    repository = CosmosUserRepository(FakeContainers(users=container), "users")  # type: ignore[arg-type]
    user = User(id="alice", email="a@example.test", display_name="Alice", created_at=NOW, last_seen_at=NOW)

    assert await repository.get("alice") is None
    assert await repository.upsert(user) == user
    assert await repository.get("alice") == user
    assert await repository.delete("alice") is True
    assert await repository.delete("alice") is False

    container.missing = True
    with pytest.raises(RepositoryUnavailableError):
        await repository.get("alice")
    with pytest.raises(RepositoryUnavailableError):
        await repository.upsert(user)


async def test_resume_round_trip_and_isolation() -> None:
    container = FakeContainer("userId")
    repository = CosmosResumeRepository(FakeContainers(resumes=container), "resumes")  # type: ignore[arg-type]
    mine, theirs = make_resume("r1"), make_resume("r2", "bob")

    assert await repository.upsert(mine) == mine
    await repository.upsert(theirs)

    assert await repository.get("alice", "r1") == mine
    assert await repository.get("bob", "r1") is None  # wrong partition
    assert await repository.list_for_user("alice") == [mine]
    document = container.items[("alice", "r1")]
    assert document["charCount"] == mine.char_count
    assert document["contentHash"] == mine.content_hash
    assert await repository.delete("alice", "r1") is True
    assert await repository.delete("alice", "r1") is False
    assert await repository.delete_for_user("bob") == 1
    assert container.items == {}

    container.missing = True
    for call in (repository.get("alice", "r1"), repository.list_for_user("alice"), repository.upsert(mine)):
        with pytest.raises(RepositoryUnavailableError):
            await call


# --- results -----------------------------------------------------------------------------


async def test_results_are_saved_with_user_id_and_deleted_per_user() -> None:
    container = FakeContainer("type")
    repository = CosmosResultsRepository(FakeContainers(results=container), "results")  # type: ignore[arg-type]

    await repository.save_resume_suggestions(
        user_id="alice", resume_text="r", job_description_text="j", tone="t", generated_markdown="# m"
    )
    await repository.save_cover_letter(
        user_id="bob", company_name="Acme", role_title="Engineer", tone="t", generated_text="Dear"
    )
    await repository.save_cover_letter(
        user_id=None, company_name="Acme", role_title="Engineer", tone="t", generated_text="Dear"
    )

    kinds = sorted((key[0], item.get("userId", "")) for key, item in container.items.items())
    assert kinds == [("cover_letter", ""), ("cover_letter", "bob"), ("resume_suggestions", "alice")]
    assert await repository.delete_for_user("alice") == 1
    assert sorted(item.get("userId", "") for item in container.items.values()) == ["", "bob"]


async def test_result_persistence_failures_never_reach_the_caller() -> None:
    container = FakeContainer("type")
    container.fail_with = CosmosHttpResponseError(status_code=500, message="boom")
    repository = CosmosResultsRepository(FakeContainers(results=container), "results")  # type: ignore[arg-type]

    await repository.save_cover_letter(
        user_id="alice", company_name="Acme", role_title="Engineer", tone="t", generated_text="Dear"
    )


def test_containers_require_configuration() -> None:
    with pytest.raises(RuntimeError, match="not configured"):
        CosmosContainers(endpoint="", key="", database_name="jobassist")
