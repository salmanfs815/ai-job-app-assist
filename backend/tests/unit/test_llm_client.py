from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from openai import APIConnectionError, APIStatusError, RateLimitError

from app.domain.usage import LLMUsage
from app.integrations.llm import LLMClient, LLMEvent, LLMStreamError, TextDelta, estimate_usage

MESSAGES = [{"role": "system", "content": "s" * 40}, {"role": "user", "content": "u" * 360}]


def chunk(content: str | None = None, usage: tuple[int, int] | None = None) -> SimpleNamespace:
    choices = [] if content is None else [SimpleNamespace(delta=SimpleNamespace(content=content))]
    reported = SimpleNamespace(prompt_tokens=usage[0], completion_tokens=usage[1]) if usage else None
    return SimpleNamespace(choices=choices, usage=reported, model="gpt-4.1-mini-2025-04-14")


class FakeStream:
    def __init__(self, chunks: list[SimpleNamespace]) -> None:
        self._chunks = chunks

    async def __aenter__(self) -> "FakeStream":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def __aiter__(self) -> "FakeStream":
        self._iter = iter(self._chunks)
        return self

    async def __anext__(self) -> SimpleNamespace:
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration from None


class FakeOpenAI:
    def __init__(self, result: Any) -> None:
        self.calls: list[dict[str, Any]] = []
        self._result = result
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def make_client(result: Any, api_key: str = "sk-test") -> tuple[LLMClient, FakeOpenAI]:
    fake = FakeOpenAI(result)
    client = LLMClient(
        api_key=api_key,
        model="gpt-4.1-mini",
        max_output_tokens=1234,
        client_factory=lambda **_: fake,
    )
    return client, fake


async def collect(client: LLMClient) -> list[LLMEvent]:
    return [event async for event in client.stream_markdown(MESSAGES, temperature=0.2, mock_text="mock " * 30)]


async def test_mock_mode_replays_the_sample_text_and_estimates_usage() -> None:
    client, fake = make_client(None, api_key="")

    events = await collect(client)

    assert client.mock
    assert client.model == "mock"
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "mock " * 30
    assert events[-1] == LLMUsage(model="mock", input_tokens=100, output_tokens=37, reported=False)
    assert fake.calls == []


async def test_streams_text_and_reports_provider_usage() -> None:
    stream = FakeStream([chunk("Hello"), chunk(""), chunk(" world"), chunk(usage=(120, 45))])
    client, fake = make_client(stream)

    events = await collect(client)

    assert [e.text for e in events if isinstance(e, TextDelta)] == ["Hello", " world"]
    assert events[-1] == LLMUsage(model="gpt-4.1-mini-2025-04-14", input_tokens=120, output_tokens=45)
    request = fake.calls[0]
    assert request["stream_options"] == {"include_usage": True}
    assert request["max_completion_tokens"] == 1234
    assert request["model"] == "gpt-4.1-mini"
    assert not client.mock
    assert client.model == "gpt-4.1-mini"


def _status_error(cls: type[APIStatusError], status: int) -> APIStatusError:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return cls("upstream", response=httpx.Response(status, request=request), body=None)


@pytest.mark.parametrize(
    ("error", "retryable", "fragment"),
    [
        (_status_error(RateLimitError, 429), True, "rate limited"),
        (APIConnectionError(request=httpx.Request("POST", "https://api.openai.com")), True, "interrupted"),
        (_status_error(APIStatusError, 503), True, "could not complete"),
        (_status_error(APIStatusError, 400), False, "rejected"),
    ],
)
async def test_provider_errors_become_safe_stream_errors(error: Exception, retryable: bool, fragment: str) -> None:
    client, _ = make_client(error)

    with pytest.raises(LLMStreamError) as excinfo:
        await collect(client)

    assert excinfo.value.retryable is retryable
    assert fragment in str(excinfo.value)


def test_estimate_usage_counts_prompt_and_output_characters() -> None:
    usage = estimate_usage("gpt-4.1-mini", MESSAGES, "o" * 80)

    assert usage == LLMUsage(model="gpt-4.1-mini", input_tokens=100, output_tokens=20, reported=False)
