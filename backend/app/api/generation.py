"""Shared plumbing for the streamed (SSE) LLM endpoints: limits in, usage out."""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable

import anyio
from fastapi import Request
from fastapi.responses import StreamingResponse

from app.api.container import AppContainer
from app.api.sse import SSE_HEADERS, sse_event
from app.core.clock import utc_now
from app.core.errors import ProblemError, retry_extensions
from app.domain.usage import LLMUsage, QuotaSubject, UsageKind, seconds_until
from app.integrations.llm import LLMStreamError, Messages, TextDelta, estimate_usage
from app.repositories.base import RepositoryError
from app.services.usage import BudgetExceededError, QuotaExceededError, Reservation

logger = logging.getLogger(__name__)

Persist = Callable[[str], Awaitable[None]]


async def admit_generation(container: AppContainer, subject: QuotaSubject) -> Reservation:
    """Apply the global budget and the caller's daily quota before any LLM work starts.

    Raises problem+json errors: 503 when the budget is spent, 429 when the quota is.
    """
    now = utc_now()
    try:
        await container.usage.ensure_budget_available()
        return await container.usage.reserve_generation(subject)
    except BudgetExceededError as exc:
        retry_after = seconds_until(now, exc.status.resets_at)
        raise ProblemError(
            503,
            "The demo has reached its AI budget for today. Generation is paused until the budget resets; "
            "everything else keeps working.",
            code="llm_budget_exhausted",
            headers={"Retry-After": str(retry_after)},
            extensions=retry_extensions(retry_after, exc.status.resets_at),
        ) from exc
    except QuotaExceededError as exc:
        retry_after = seconds_until(now, exc.status.resets_at)
        is_guest = exc.status.kind is UsageKind.GUEST
        detail = (
            f"You have used all {exc.status.limit} free generations for today."
            if is_guest
            else f"You have used all {exc.status.limit} generations for today."
        )
        raise ProblemError(
            429,
            detail,
            code="quota_exceeded",
            headers={"Retry-After": str(retry_after)},
            extensions={
                **retry_extensions(retry_after, exc.status.resets_at),
                "scope": exc.status.kind.value,
                "limit": exc.status.limit,
            },
        ) from exc
    except RepositoryError as exc:
        logger.error("Usage accounting failed; refusing to start a generation.", exc_info=True)
        raise ProblemError(
            503,
            "Usage limits could not be checked right now. Please try again in a moment.",
            code="usage_unavailable",
            headers={"Retry-After": "5"},
            extensions=retry_extensions(5),
        ) from exc


def stream_markdown_response(
    request: Request,
    *,
    container: AppContainer,
    reservation: Reservation,
    messages: Messages,
    mock_text: str,
    status_message: str,
    temperature: float,
    persist: Persist | None,
) -> StreamingResponse:
    llm = container.llm

    async def settle(parts: list[str], reported: LLMUsage | None, failed_without_output: bool) -> None:
        """Account for what the call cost. Runs even when the client disconnects."""
        try:
            if failed_without_output and reported is None:
                await container.usage.release_generation(reservation)
                return
            usage = reported or estimate_usage(llm.model, messages, "".join(parts))
            await container.usage.record_llm_usage(reservation, usage, billable=not llm.mock)
        except Exception:
            logger.error("Could not record LLM usage.", exc_info=True)

    async def events() -> AsyncIterator[str]:
        demo = llm.mock
        yield sse_event("status", {"message": status_message, "demo": demo})
        parts: list[str] = []
        reported: LLMUsage | None = None
        failed_without_output = False
        try:
            async for event in llm.stream_markdown(messages, temperature=temperature, mock_text=mock_text):
                if isinstance(event, LLMUsage):
                    reported = event
                    continue
                if not isinstance(event, TextDelta):
                    continue
                if await request.is_disconnected():
                    return
                parts.append(event.text)
                yield sse_event("delta", {"text": event.text})
        except asyncio.CancelledError:
            raise
        except LLMStreamError as exc:
            failed_without_output = not parts
            yield sse_event(
                "error",
                {"message": str(exc), "retryable": exc.retryable, "partial": bool(parts)},
            )
            return
        finally:
            # Shielded: a disconnect cancels this task, but the spend must still be recorded.
            with anyio.CancelScope(shield=True):
                await settle(parts, reported, failed_without_output)

        completed = "".join(parts).strip()
        if not completed:
            yield sse_event(
                "error",
                {"message": "OpenAI returned an empty response.", "retryable": True, "partial": False},
            )
            return

        if await request.is_disconnected():
            return
        if persist is not None:
            yield sse_event("status", {"message": "Finalizing and saving your result…", "demo": demo})
            await persist(completed)
        yield sse_event("done", {"demo": demo})

    return StreamingResponse(events(), media_type="text/event-stream", headers=SSE_HEADERS)
