"""OpenAI chat-completions streaming with token usage, plus a deterministic mock.

Without ``OPENAI_API_KEY`` the client replays canned Markdown so the whole product
can be exercised (and tested) at no cost.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, RateLimitError

from app.domain.pricing import estimate_tokens
from app.domain.usage import LLMUsage

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

- Keep a concise source resume close to its original length. Condense a multi-page master resume to one or two targeted pages; verify final line wrapping in the rendered document.
"""


MOCK_COVER_LETTER = """Dear Hiring Manager,

I am excited to apply for the Software Engineer role. My background includes building backend services, improving reliability, and delivering maintainable systems with cross-functional teams.

In recent work, I designed API layers, strengthened data workflows, and focused on measurable product and operational outcomes. This experience aligns well with a team that values dependable delivery, clear engineering decisions, and thoughtful collaboration.

I would welcome the opportunity to bring that same rigor and execution to your team. Thank you for your time and consideration.

Sincerely,
Your Name
"""

MOCK_MODEL = "mock"


class LLMStreamError(Exception):
    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class TextDelta:
    text: str


# A stream yields text deltas and, when the provider reports it, one final usage event.
LLMEvent = TextDelta | LLMUsage
Messages = list[dict[str, str]]


def estimate_usage(model: str, messages: Messages, output_text: str) -> LLMUsage:
    """Character-based estimate for when the provider reported nothing (mock, interrupted stream)."""
    prompt_chars = sum(len(message.get("content", "")) for message in messages)
    return LLMUsage(
        model=model,
        input_tokens=estimate_tokens("x" * prompt_chars),
        output_tokens=estimate_tokens(output_text),
        reported=False,
    )


async def _mock_chunks(text: str, chunk_size: int = 48) -> AsyncIterator[str]:
    for start in range(0, len(text), chunk_size):
        await asyncio.sleep(0)
        yield text[start : start + chunk_size]


class LLMClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_output_tokens: int,
        client_factory: Callable[..., Any] = AsyncOpenAI,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._max_output_tokens = max_output_tokens
        self._client_factory = client_factory
        self._client: Any | None = None

    @property
    def mock(self) -> bool:
        return not self._api_key

    @property
    def model(self) -> str:
        return MOCK_MODEL if self.mock else self._model

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = self._client_factory(api_key=self._api_key)
        return self._client

    async def stream_markdown(
        self,
        messages: Messages,
        *,
        temperature: float,
        mock_text: str,
    ) -> AsyncIterator[LLMEvent]:
        if self.mock:
            async for chunk in _mock_chunks(mock_text):
                yield TextDelta(chunk)
            yield estimate_usage(MOCK_MODEL, messages, mock_text)
            return

        try:
            stream = await self._get_client().chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_completion_tokens=self._max_output_tokens,
                stream=True,
                # Adds a final chunk (with empty ``choices``) carrying token usage for the request.
                stream_options={"include_usage": True},
            )
            async with stream:
                async for chunk in stream:
                    usage = getattr(chunk, "usage", None)
                    if usage is not None:
                        yield LLMUsage(
                            model=getattr(chunk, "model", None) or self._model,
                            input_tokens=int(usage.prompt_tokens or 0),
                            output_tokens=int(usage.completion_tokens or 0),
                        )
                    if not chunk.choices:
                        continue
                    content = chunk.choices[0].delta.content
                    if content:
                        yield TextDelta(content)
        except asyncio.CancelledError:
            raise
        except RateLimitError as exc:
            raise LLMStreamError(
                "OpenAI is temporarily rate limited. Please try again shortly.", retryable=True
            ) from exc
        except (APITimeoutError, APIConnectionError) as exc:
            raise LLMStreamError("The connection to OpenAI was interrupted. Please try again.", retryable=True) from exc
        except APIStatusError as exc:
            retryable = getattr(exc, "status_code", 0) >= 500
            message = (
                "OpenAI could not complete the request. Please try again."
                if retryable
                else "OpenAI rejected the request."
            )
            raise LLMStreamError(message, retryable=retryable) from exc
