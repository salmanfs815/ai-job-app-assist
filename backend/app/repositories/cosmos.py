"""Azure Cosmos DB (NoSQL) repositories.

The synchronous SDK is used and every call is pushed to a worker thread so the event
loop is never blocked. Documents store ``userId`` as the partition key (see ADR 0004).
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

from azure.core import MatchConditions
from azure.cosmos import ContainerProxy, CosmosClient
from azure.cosmos.exceptions import (
    CosmosAccessConditionFailedError,
    CosmosHttpResponseError,
    CosmosResourceExistsError,
    CosmosResourceNotFoundError,
)

from app.domain.usage import UsageKind, UsageRecord
from app.repositories.base import ConcurrencyError, RepositoryUnavailableError

logger = logging.getLogger(__name__)


class CosmosContainers:
    """Lazily creates the client and hands out container proxies by name."""

    def __init__(self, *, endpoint: str, key: str, database_name: str) -> None:
        if not endpoint or not key:
            raise RuntimeError("Cosmos DB endpoint/key is not configured.")
        self._endpoint = endpoint
        self._key = key
        self._database_name = database_name
        self._client: CosmosClient | None = None
        self._containers: dict[str, ContainerProxy] = {}

    def container(self, name: str) -> ContainerProxy:
        if name not in self._containers:
            if self._client is None:
                self._client = CosmosClient(url=self._endpoint, credential=self._key)
            database = self._client.get_database_client(self._database_name)
            self._containers[name] = database.get_container_client(name)
        return self._containers[name]


async def _run[T](operation: Callable[[], T]) -> T:
    """Run a blocking SDK call in a thread and translate infrastructure failures."""
    try:
        return await asyncio.to_thread(operation)
    except (CosmosResourceExistsError, CosmosAccessConditionFailedError, CosmosResourceNotFoundError):
        raise
    except CosmosHttpResponseError as exc:
        raise RepositoryUnavailableError(f"Cosmos DB request failed with status {exc.status_code}") from exc
    except Exception as exc:  # connection errors, DNS failures, misconfiguration
        raise RepositoryUnavailableError("Cosmos DB is unreachable") from exc


class CosmosUsageRepository:
    """``usage`` container, partition key ``/userId``, document id = UTC date."""

    def __init__(self, containers: CosmosContainers, container_name: str) -> None:
        self._containers = containers
        self._name = container_name

    @property
    def _container(self) -> ContainerProxy:
        return self._containers.container(self._name)

    @staticmethod
    def _to_document(record: UsageRecord) -> dict[str, Any]:
        return {
            "id": record.day.isoformat(),
            "userId": record.owner_id,
            "kind": record.kind.value,
            "generations": record.generations,
            "inputTokens": record.input_tokens,
            "outputTokens": record.output_tokens,
            "estimatedCostUsd": record.estimated_cost_usd,
            "ttl": record.ttl_seconds,
        }

    @staticmethod
    def _from_document(document: dict[str, Any]) -> UsageRecord:
        return UsageRecord(
            owner_id=document["userId"],
            day=date.fromisoformat(document["id"]),
            kind=UsageKind(document.get("kind", UsageKind.USER.value)),
            generations=int(document.get("generations", 0)),
            input_tokens=int(document.get("inputTokens", 0)),
            output_tokens=int(document.get("outputTokens", 0)),
            estimated_cost_usd=float(document.get("estimatedCostUsd", 0.0)),
            etag=document.get("_etag"),
        )

    async def get(self, owner_id: str, day: date) -> UsageRecord | None:
        try:
            document = await _run(lambda: self._container.read_item(item=day.isoformat(), partition_key=owner_id))
        except CosmosResourceNotFoundError as exc:
            if _is_missing_container(exc):
                raise RepositoryUnavailableError(f"Cosmos container '{self._name}' does not exist") from exc
            return None
        return self._from_document(document)

    async def create(self, record: UsageRecord) -> UsageRecord:
        try:
            document = await _run(lambda: self._container.create_item(body=self._to_document(record)))
        except CosmosResourceExistsError as exc:
            raise ConcurrencyError("usage record already exists") from exc
        except CosmosResourceNotFoundError as exc:
            raise RepositoryUnavailableError(f"Cosmos container '{self._name}' does not exist") from exc
        return self._from_document(document)

    async def replace(self, record: UsageRecord) -> UsageRecord:
        try:
            document = await _run(
                lambda: self._container.replace_item(
                    item=record.day.isoformat(),
                    body=self._to_document(record),
                    etag=record.etag,
                    match_condition=MatchConditions.IfNotModified,
                )
            )
        except (CosmosAccessConditionFailedError, CosmosResourceNotFoundError) as exc:
            raise ConcurrencyError("usage record was modified concurrently") from exc
        return self._from_document(document)

    async def delete_for_owner(self, owner_id: str) -> int:
        def _delete() -> int:
            container = self._container
            ids = [
                item["id"]
                for item in container.query_items(
                    query="SELECT c.id FROM c WHERE c.userId = @owner",
                    parameters=[{"name": "@owner", "value": owner_id}],
                    partition_key=owner_id,
                )
            ]
            for item_id in ids:
                container.delete_item(item=item_id, partition_key=owner_id)
            return len(ids)

        return await _run(_delete)


class CosmosResultsRepository:
    """Existing ``results`` container (partition key ``/type``). Failures never break a response."""

    def __init__(self, containers: CosmosContainers, container_name: str) -> None:
        self._containers = containers
        self._name = container_name

    @property
    def _container(self) -> ContainerProxy:
        return self._containers.container(self._name)

    async def _save(self, document: dict[str, Any]) -> None:
        try:
            await _run(lambda: self._container.upsert_item(body=document))
        except Exception:
            # Content is deliberately not logged.
            logger.exception("Failed to persist %s result to Cosmos DB.", document.get("type"))

    @staticmethod
    def _base(kind: str, id_prefix: str, user_id: str | None) -> dict[str, Any]:
        now = datetime.now(UTC)
        document: dict[str, Any] = {
            "id": f"{id_prefix}-{now.timestamp()}",
            "type": kind,
            "created_at": now.isoformat(),
        }
        if user_id is not None:
            document["userId"] = user_id
        return document

    async def save_resume_suggestions(
        self,
        *,
        user_id: str | None,
        resume_text: str,
        job_description_text: str,
        tone: str,
        generated_markdown: str,
    ) -> None:
        document = self._base("resume_suggestions", "resume-suggestions", user_id)
        document.update(
            resume_text=resume_text,
            job_description_text=job_description_text,
            tone=tone,
            generated_markdown=generated_markdown,
        )
        await self._save(document)

    async def save_cover_letter(
        self,
        *,
        user_id: str | None,
        company_name: str,
        role_title: str,
        tone: str,
        generated_text: str,
    ) -> None:
        document = self._base("cover_letter", "cover-letter", user_id)
        document.update(
            company_name=company_name,
            role_title=role_title,
            tone=tone,
            generated_text=generated_text,
        )
        await self._save(document)

    async def delete_for_user(self, user_id: str) -> int:
        def _delete() -> int:
            container = self._container
            items = list(
                container.query_items(
                    query="SELECT c.id, c.type FROM c WHERE c.userId = @user",
                    parameters=[{"name": "@user", "value": user_id}],
                    enable_cross_partition_query=True,
                )
            )
            for item in items:
                container.delete_item(item=item["id"], partition_key=item["type"])
            return len(items)

        return await _run(_delete)


def _is_missing_container(exc: CosmosResourceNotFoundError) -> bool:
    """A 404 for a document and a 404 for the whole container look alike; tell them apart."""
    if getattr(exc, "sub_status", None) == 1003:  # "Owner resource does not exist"
        return True
    return "owner resource does not exist" in (exc.message or "").lower()
