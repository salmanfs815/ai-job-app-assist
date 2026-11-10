"""RFC 9457 ``application/problem+json`` errors.

Every error the API returns has the same shape so clients can rely on ``title``,
``status``, ``detail`` and the documented extension members (``code``,
``retryAfterSeconds``, ``resetsAt``, ``errors``).
"""

import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

PROBLEM_MEDIA_TYPE = "application/problem+json"

_TITLES: dict[int, str] = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    413: "Content Too Large",
    422: "Unprocessable Content",
    429: "Too Many Requests",
    500: "Internal Server Error",
    503: "Service Unavailable",
}


class ProblemError(Exception):
    """An error that maps directly onto a problem+json response."""

    def __init__(
        self,
        status: int,
        detail: str,
        *,
        code: str,
        title: str | None = None,
        headers: Mapping[str, str] | None = None,
        extensions: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.code = code
        self.title = title or _TITLES.get(status, "Error")
        self.headers = dict(headers or {})
        self.extensions = dict(extensions or {})


def retry_extensions(retry_after_seconds: int, resets_at: datetime | None = None) -> dict[str, Any]:
    extensions: dict[str, Any] = {"retryAfterSeconds": retry_after_seconds}
    if resets_at is not None:
        extensions["resetsAt"] = resets_at.isoformat().replace("+00:00", "Z")
    return extensions


def problem_body(
    status: int,
    detail: str,
    *,
    code: str,
    title: str | None = None,
    extensions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": f"https://github.com/salmanfs815/ai-job-app-assist/blob/master/docs/errors.md#{code}",
        "title": title or _TITLES.get(status, "Error"),
        "status": status,
        "detail": detail,
        "code": code,
    }
    body.update(extensions or {})
    return body


def problem_response(
    status: int,
    detail: str,
    *,
    code: str,
    title: str | None = None,
    headers: Mapping[str, str] | None = None,
    extensions: Mapping[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        problem_body(status, detail, code=code, title=title, extensions=extensions),
        status_code=status,
        headers=dict(headers or {}),
        media_type=PROBLEM_MEDIA_TYPE,
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemError)
    async def _problem(_request: Request, exc: ProblemError) -> JSONResponse:
        return problem_response(
            exc.status,
            exc.detail,
            code=exc.code,
            title=exc.title,
            headers=exc.headers,
            extensions=exc.extensions,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else _TITLES.get(exc.status_code, "Error")
        return problem_response(
            exc.status_code,
            detail,
            code=f"http_{exc.status_code}",
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "field": ".".join(str(part) for part in error.get("loc", ()) if part != "body"),
                "message": error.get("msg", "Invalid value"),
            }
            for error in exc.errors()
        ]
        summary = "; ".join(f"{e['field']}: {e['message']}" if e["field"] else e["message"] for e in errors)
        return problem_response(
            422,
            summary or "The request is not valid.",
            code="validation_error",
            extensions={"errors": errors},
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Never echo exception text: it may contain user content.
        logger.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
        return problem_response(500, "Something went wrong on our side.", code="internal_error")
