"""Cosmos DB repositories for users and saved resumes."""

from datetime import datetime
from typing import Any

from azure.cosmos import ContainerProxy
from azure.cosmos.exceptions import CosmosResourceNotFoundError

from app.domain.resumes import Resume
from app.domain.users import User
from app.repositories.base import RepositoryUnavailableError
from app.repositories.cosmos import CosmosContainers, is_missing_container, run_blocking


class CosmosUserRepository:
    """``users`` container, partition key ``/id``: every lookup is a 1 RU point read."""

    def __init__(self, containers: CosmosContainers, container_name: str) -> None:
        self._containers = containers
        self._name = container_name

    @property
    def _container(self) -> ContainerProxy:
        return self._containers.container(self._name)

    @staticmethod
    def _to_document(user: User) -> dict[str, Any]:
        return {
            "id": user.id,
            "email": user.email,
            "displayName": user.display_name,
            "createdAt": user.created_at.isoformat(),
            "lastSeenAt": user.last_seen_at.isoformat(),
        }

    @staticmethod
    def _from_document(document: dict[str, Any]) -> User:
        return User(
            id=document["id"],
            email=document.get("email"),
            display_name=document.get("displayName"),
            created_at=datetime.fromisoformat(document["createdAt"]),
            last_seen_at=datetime.fromisoformat(document["lastSeenAt"]),
        )

    async def get(self, user_id: str) -> User | None:
        try:
            document = await run_blocking(lambda: self._container.read_item(item=user_id, partition_key=user_id))
        except CosmosResourceNotFoundError as exc:
            if is_missing_container(exc):
                raise RepositoryUnavailableError(f"Cosmos container '{self._name}' does not exist") from exc
            return None
        return self._from_document(document)

    async def upsert(self, user: User) -> User:
        try:
            document = await run_blocking(lambda: self._container.upsert_item(body=self._to_document(user)))
        except CosmosResourceNotFoundError as exc:
            raise RepositoryUnavailableError(f"Cosmos container '{self._name}' does not exist") from exc
        return self._from_document(document)

    async def delete(self, user_id: str) -> bool:
        try:
            await run_blocking(lambda: self._container.delete_item(item=user_id, partition_key=user_id))
        except CosmosResourceNotFoundError:
            return False
        return True


class CosmosResumeRepository:
    """``resumes`` container, partition key ``/userId``: one user's resumes share a partition."""

    def __init__(self, containers: CosmosContainers, container_name: str) -> None:
        self._containers = containers
        self._name = container_name

    @property
    def _container(self) -> ContainerProxy:
        return self._containers.container(self._name)

    @staticmethod
    def _to_document(resume: Resume) -> dict[str, Any]:
        return {
            "id": resume.id,
            "userId": resume.user_id,
            "name": resume.name,
            "text": resume.text,
            "charCount": resume.char_count,
            "contentHash": resume.content_hash,
            "sourceFilename": resume.source_filename,
            "ocrStatus": resume.ocr_status,
            "isDefault": resume.is_default,
            "version": resume.version,
            "createdAt": resume.created_at.isoformat(),
            "updatedAt": resume.updated_at.isoformat(),
        }

    @staticmethod
    def _from_document(document: dict[str, Any]) -> Resume:
        return Resume(
            id=document["id"],
            user_id=document["userId"],
            name=document["name"],
            text=document["text"],
            source_filename=document.get("sourceFilename"),
            ocr_status=document.get("ocrStatus", "not_used"),
            is_default=bool(document.get("isDefault", False)),
            version=int(document.get("version", 1)),
            created_at=datetime.fromisoformat(document["createdAt"]),
            updated_at=datetime.fromisoformat(document["updatedAt"]),
        )

    async def list_for_user(self, user_id: str) -> list[Resume]:
        def query() -> list[dict[str, Any]]:
            return list(
                self._container.query_items(
                    query="SELECT * FROM c WHERE c.userId = @user",
                    parameters=[{"name": "@user", "value": user_id}],
                    partition_key=user_id,
                )
            )

        try:
            documents = await run_blocking(query)
        except CosmosResourceNotFoundError as exc:
            raise RepositoryUnavailableError(f"Cosmos container '{self._name}' does not exist") from exc
        return [self._from_document(document) for document in documents]

    async def get(self, user_id: str, resume_id: str) -> Resume | None:
        try:
            document = await run_blocking(lambda: self._container.read_item(item=resume_id, partition_key=user_id))
        except CosmosResourceNotFoundError as exc:
            if is_missing_container(exc):
                raise RepositoryUnavailableError(f"Cosmos container '{self._name}' does not exist") from exc
            return None
        return self._from_document(document)

    async def upsert(self, resume: Resume) -> Resume:
        try:
            document = await run_blocking(lambda: self._container.upsert_item(body=self._to_document(resume)))
        except CosmosResourceNotFoundError as exc:
            raise RepositoryUnavailableError(f"Cosmos container '{self._name}' does not exist") from exc
        return self._from_document(document)

    async def delete(self, user_id: str, resume_id: str) -> bool:
        try:
            await run_blocking(lambda: self._container.delete_item(item=resume_id, partition_key=user_id))
        except CosmosResourceNotFoundError:
            return False
        return True

    async def delete_for_user(self, user_id: str) -> int:
        resumes = await self.list_for_user(user_id)
        for resume in resumes:
            await self.delete(user_id, resume.id)
        return len(resumes)
