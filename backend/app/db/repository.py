from datetime import datetime, timezone
from typing import Any

from app.config import settings


class _NoopPersistence:
    def save_analysis(self, **_: Any) -> None:
        return None

    def save_cover_letter(self, **_: Any) -> None:
        return None


class _CosmosPersistence:
    def __init__(self) -> None:
        self._container = None

    def _ensure_container(self) -> None:
        if self._container is not None:
            return

        if not settings.cosmos_endpoint or not settings.cosmos_key:
            raise RuntimeError("Cosmos DB endpoint/key is not configured.")

        try:
            from azure.cosmos import CosmosClient
        except ImportError as exc:  # pragma: no cover - environment-specific
            raise RuntimeError("azure-cosmos package is required when persistence is enabled.") from exc

        client = CosmosClient(url=settings.cosmos_endpoint, credential=settings.cosmos_key)
        database = client.get_database_client(settings.cosmos_database_name)
        self._container = database.get_container_client(settings.cosmos_container_name)

    def save_analysis(
        self,
        *,
        resume_text: str,
        job_description_text: str,
        extracted_keywords: list[str],
        match_score: int,
        result_payload: dict,
    ) -> None:
        self._ensure_container()
        document = {
            "id": f"analysis-{datetime.now(timezone.utc).timestamp()}",
            "type": "analysis",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "resume_text": resume_text,
            "job_description_text": job_description_text,
            "extracted_keywords": {"items": extracted_keywords},
            "match_score": match_score,
            "result_payload": result_payload,
        }
        self._container.upsert_item(body=document)

    def save_cover_letter(
        self,
        *,
        company_name: str,
        role_title: str,
        tone: str,
        generated_text: str,
    ) -> None:
        self._ensure_container()
        document = {
            "id": f"cover-letter-{datetime.now(timezone.utc).timestamp()}",
            "type": "cover_letter",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "company_name": company_name,
            "role_title": role_title,
            "tone": tone,
            "generated_text": generated_text,
        }
        self._container.upsert_item(body=document)


_persistence = _CosmosPersistence() if settings.persistence_enabled else _NoopPersistence()


def save_analysis(
    resume_text: str,
    job_description_text: str,
    extracted_keywords: list[str],
    match_score: int,
    result_payload: dict,
) -> None:
    if not settings.persistence_enabled:
        return None

    try:
        _persistence.save_analysis(
            resume_text=resume_text,
            job_description_text=job_description_text,
            extracted_keywords=extracted_keywords,
            match_score=match_score,
            result_payload=result_payload,
        )
    except Exception:
        return None


def save_cover_letter(
    company_name: str,
    role_title: str,
    tone: str,
    generated_text: str,
) -> None:
    if not settings.persistence_enabled:
        return None

    try:
        _persistence.save_cover_letter(
            company_name=company_name,
            role_title=role_title,
            tone=tone,
            generated_text=generated_text,
        )
    except Exception:
        return None
