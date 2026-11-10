from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Problem(BaseModel):
    """RFC 9457 problem details. Extension members vary by ``code``."""

    model_config = ConfigDict(extra="allow")

    type: str
    title: str
    status: int
    detail: str
    code: str
    retryAfterSeconds: int | None = Field(default=None, description="Seconds until the request may be retried.")
    resetsAt: str | None = Field(default=None, description="UTC time at which the limit resets.")


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI ``responses`` entries for the given error statuses."""
    descriptions = {
        401: "Missing or invalid credentials.",
        403: "The caller is not allowed to do this.",
        404: "Not found.",
        409: "Conflict.",
        413: "Upload too large.",
        422: "Validation failed.",
        429: "Rate limit or daily quota reached. See `Retry-After`.",
        503: "Daily LLM budget reached or a dependency is unavailable. See `Retry-After`.",
    }
    return {
        status: {
            "model": Problem,
            "description": descriptions.get(status, "Error"),
            "content": {"application/problem+json": {}},
        }
        for status in statuses
    }
