import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from openai import APIConnectionError, APITimeoutError, APIStatusError, AsyncOpenAI, RateLimitError

from app.config import settings


MOCK_RESUME_SUGGESTIONS = """# Match score: 78/100

This is an evidence-based estimate of resume-to-job alignment, not a guarantee of ATS or hiring results.

## Match assessment

Your backend experience is relevant, with the strongest alignment around Python, APIs, and cloud delivery.

## Key strengths and gaps

- **Strength:** Supported Python, API, and cloud delivery experience.
- **Gap:** FastAPI is requested but is not demonstrated in the supplied resume.

## Actionable section-by-section feedback

1. **Headline:** Name the backend and API focus explicitly if that reflects your target role.
2. **Summary:** Lead with supported Python, service reliability, and cross-functional delivery experience.
3. **Experience:** Add outcomes to backend bullets where the resume provides defensible evidence.
4. **Skills:** Surface FastAPI or AWS only if you have genuine experience that is not already visible.

- **Before:** Built backend services for internal tools.
- **After:** Built Python API services and improved data workflows for internal product teams.

## Complete tailored resume

### Backend Engineer

Backend engineer with Python, API, cloud delivery, and service reliability experience.

#### Experience

- Built Python API services and improved data workflows for internal product teams.

## Length and page-fit check

- The rewrite remains close to the source length; verify final line wrapping in the rendered document.
"""


MOCK_COVER_LETTER = """Dear Hiring Manager,

I am excited to apply for the Software Engineer role. My background includes building backend services, improving reliability, and delivering maintainable systems with cross-functional teams.

In recent work, I designed API layers, strengthened data workflows, and focused on measurable product and operational outcomes. This experience aligns well with a team that values dependable delivery, clear engineering decisions, and thoughtful collaboration.

I would welcome the opportunity to bring that same rigor and execution to your team. Thank you for your time and consideration.

Sincerely,
Your Name
"""


class LLMStreamError(Exception):
    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


def sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _mock_chunks(text: str, chunk_size: int = 48) -> AsyncIterator[str]:
    for start in range(0, len(text), chunk_size):
        await asyncio.sleep(0)
        yield text[start : start + chunk_size]


async def stream_chat_markdown(
    messages: list[dict[str, str]],
    *,
    temperature: float,
    mock_text: str,
) -> AsyncIterator[str]:
    if not settings.openai_api_key:
        async for chunk in _mock_chunks(mock_text):
            yield chunk
        return

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        stream = await client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            temperature=temperature,
            stream=True,
        )
        async with stream:
            async for chunk in stream:
                if not chunk.choices:
                    continue
                content = chunk.choices[0].delta.content
                if content:
                    yield content
    except asyncio.CancelledError:
        raise
    except RateLimitError as exc:
        raise LLMStreamError("OpenAI is temporarily rate limited. Please try again shortly.", retryable=True) from exc
    except (APITimeoutError, APIConnectionError) as exc:
        raise LLMStreamError("The connection to OpenAI was interrupted. Please try again.", retryable=True) from exc
    except APIStatusError as exc:
        retryable = getattr(exc, "status_code", 0) >= 500
        message = "OpenAI could not complete the request. Please try again." if retryable else "OpenAI rejected the request."
        raise LLMStreamError(message, retryable=retryable) from exc
