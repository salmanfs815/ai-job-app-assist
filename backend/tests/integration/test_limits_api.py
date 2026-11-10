"""Acceptance tests for §8.1: every limit returns 429/503 with ``Retry-After``."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.domain.usage import GLOBAL_OWNER_ID, LLMUsage, guest_owner_id, utc_day
from app.integrations.llm import LLMEvent, LLMStreamError, TextDelta
from app.repositories.base import RepositoryUnavailableError
from tests.conftest import ClientFactory

PAYLOAD = {
    "resume_text": "Backend engineer with Python API and cloud delivery experience.",
    "job_description_text": "Seeking a backend engineer to build Python APIs and reliable cloud services.",
}
ALICE = {"X-Forwarded-For": "203.0.113.7"}
BOB = {"X-Forwarded-For": "203.0.113.8"}


def generate(client: TestClient, headers: dict[str, str] = ALICE) -> Any:
    return client.post("/generate/resume-suggestions", json=PAYLOAD, headers=headers)


def assert_problem(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["status"] == status
    assert body["code"] == code
    assert int(response.headers["Retry-After"]) == body["retryAfterSeconds"] >= 1
    return body


# --- Per-IP rate limiting -------------------------------------------------------------


def test_per_ip_limit_returns_429_with_retry_after(make_client: ClientFactory) -> None:
    client, _ = make_client(rate_limit_burst=3, rate_limit_refill_per_second=0.01)

    statuses = [client.get("/quota", headers=ALICE).status_code for _ in range(4)]
    limited = client.get("/quota", headers=ALICE)

    assert statuses == [200, 200, 200, 429]
    body = assert_problem(limited, 429, "rate_limited")
    assert body["retryAfterSeconds"] == 100
    # A different client address is unaffected.
    assert client.get("/quota", headers=BOB).status_code == 200


def test_forged_forwarded_for_entries_do_not_bypass_the_limit(make_client: ClientFactory) -> None:
    client, _ = make_client(rate_limit_burst=2, rate_limit_refill_per_second=0.01)

    responses = [
        client.get("/quota", headers={"X-Forwarded-For": f"10.9.9.{i}, 203.0.113.7"}).status_code for i in range(3)
    ]

    assert responses == [200, 200, 429]


def test_generation_and_upload_requests_cost_more(make_client: ClientFactory) -> None:
    client, _ = make_client(rate_limit_burst=10, rate_limit_refill_per_second=0.01, rate_limit_expensive_cost=5)

    assert generate(client).status_code == 200
    assert generate(client).status_code == 200
    assert_problem(generate(client), 429, "rate_limited")


def test_rate_limited_responses_are_readable_cross_origin(make_client: ClientFactory) -> None:
    client, _ = make_client(rate_limit_burst=1, rate_limit_refill_per_second=0.01)
    headers = {**ALICE, "Origin": "http://localhost:3000"}
    client.get("/quota", headers=headers)

    limited = client.get("/quota", headers=headers)

    assert limited.status_code == 429
    assert limited.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "Retry-After" in limited.headers["access-control-expose-headers"]


def test_health_probes_and_preflights_are_never_limited(make_client: ClientFactory) -> None:
    client, _ = make_client(rate_limit_burst=1, rate_limit_refill_per_second=0.01)
    preflight = {
        **ALICE,
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
    }

    assert all(client.get("/health", headers=ALICE).status_code == 200 for _ in range(5))
    assert all(client.options("/generate/cover-letter", headers=preflight).status_code == 200 for _ in range(5))


def test_rate_limiting_can_be_disabled(make_client: ClientFactory) -> None:
    client, _ = make_client(rate_limit_enabled=False, rate_limit_burst=1)

    assert all(client.get("/quota", headers=ALICE).status_code == 200 for _ in range(5))


def test_remaining_tokens_are_reported(make_client: ClientFactory) -> None:
    client, _ = make_client(rate_limit_burst=5, rate_limit_refill_per_second=0.01)

    assert client.get("/quota", headers=ALICE).headers["X-RateLimit-Remaining"] == "4"


# --- Guest quota ----------------------------------------------------------------------


def test_guest_quota_returns_429_until_the_next_utc_day(make_client: ClientFactory) -> None:
    client, _ = make_client(guest_daily_generation_limit=2, rate_limit_enabled=False)

    assert generate(client).status_code == 200
    assert generate(client).status_code == 200
    rejected = generate(client)

    body = assert_problem(rejected, 429, "quota_exceeded")
    assert body["scope"] == "guest"
    assert body["limit"] == 2
    assert "2 free generations" in body["detail"]
    resets_at = datetime.fromisoformat(body["resetsAt"])
    assert resets_at > datetime.now(UTC)
    assert (resets_at.hour, resets_at.minute, resets_at.tzinfo) == (0, 0, UTC)
    assert body["retryAfterSeconds"] <= 24 * 3600
    # Quotas are per address.
    assert generate(client, BOB).status_code == 200


def test_quota_endpoint_reflects_usage(make_client: ClientFactory) -> None:
    client, _ = make_client(guest_daily_generation_limit=3, rate_limit_enabled=False)

    before = client.get("/quota", headers=ALICE).json()
    generate(client)
    after = client.get("/quota", headers=ALICE).json()

    assert (before["scope"], before["limit"], before["used"], before["remaining"]) == ("guest", 3, 0, 3)
    assert (after["used"], after["remaining"]) == (1, 2)
    assert after["llmAvailable"] is True
    assert after["demo"] is True


def test_guest_ip_addresses_are_stored_only_as_salted_hashes(make_client: ClientFactory) -> None:
    client, container = make_client(rate_limit_enabled=False, ip_hash_salt="pepper")

    generate(client)

    owner_id = guest_owner_id("203.0.113.7", "pepper")
    record = container.usage._repository._records  # type: ignore[attr-defined]
    assert {key[0] for key in record} == {owner_id, GLOBAL_OWNER_ID}
    assert "203.0.113.7" not in owner_id


def test_failed_generation_without_output_does_not_consume_quota(make_client: ClientFactory) -> None:
    async def failing(*_args: Any, **_kwargs: Any) -> AsyncIterator[LLMEvent]:
        raise LLMStreamError("OpenAI is temporarily rate limited.", retryable=True)
        yield  # pragma: no cover

    client, container = make_client(guest_daily_generation_limit=1, rate_limit_enabled=False)
    container.llm.stream_markdown = failing  # type: ignore[method-assign]

    response = generate(client)

    assert "event: error" in response.text
    assert client.get("/quota", headers=ALICE).json()["used"] == 0


def test_failed_generation_with_partial_output_still_counts(make_client: ClientFactory) -> None:
    async def partial(*_args: Any, **_kwargs: Any) -> AsyncIterator[LLMEvent]:
        yield TextDelta("Partial")
        raise LLMStreamError("The connection to OpenAI was interrupted.", retryable=True)

    client, container = make_client(guest_daily_generation_limit=1, rate_limit_enabled=False)
    container.llm.stream_markdown = partial  # type: ignore[method-assign]

    generate(client)

    assert client.get("/quota", headers=ALICE).json()["used"] == 1


# --- Global daily budget --------------------------------------------------------------


def paid_stream(input_tokens: int, output_tokens: int) -> Any:
    async def stream(*_args: Any, **_kwargs: Any) -> AsyncIterator[LLMEvent]:
        yield TextDelta("# Tailored resume")
        yield LLMUsage(model="gpt-4.1-mini", input_tokens=input_tokens, output_tokens=output_tokens)

    return stream


def test_global_budget_returns_503_once_spent_and_keeps_other_features_working(
    make_client: ClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, container = make_client(
        openai_api_key="sk-test",
        global_daily_llm_budget_usd=0.50,
        guest_daily_generation_limit=10,
        rate_limit_enabled=False,
    )
    # 1M input tokens of gpt-4.1-mini = $0.40 per call.
    monkeypatch.setattr(container.llm, "stream_markdown", paid_stream(1_000_000, 0))

    assert generate(client).status_code == 200  # spent $0.40
    assert generate(client, BOB).status_code == 200  # spent $0.80: over budget now
    blocked = generate(client)

    body = assert_problem(blocked, 503, "llm_budget_exhausted")
    assert "budget" in body["detail"]
    assert datetime.fromisoformat(body["resetsAt"]) > datetime.now(UTC)
    # The blocked request did not use up the caller's quota, and it applies to everyone.
    assert_problem(generate(client, BOB), 503, "llm_budget_exhausted")
    quota = client.get("/quota", headers=ALICE).json()
    assert quota["used"] == 1
    assert quota["llmAvailable"] is False
    # Non-LLM features keep working.
    assert client.get("/health").status_code == 200


def test_provider_reported_usage_is_recorded_against_the_budget(
    make_client: ClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, container = make_client(openai_api_key="sk-test", rate_limit_enabled=False)
    monkeypatch.setattr(container.llm, "stream_markdown", paid_stream(2000, 1000))

    generate(client)

    records = container.usage._repository._records  # type: ignore[attr-defined]
    total = records[(GLOBAL_OWNER_ID, utc_day(datetime.now(UTC)))]
    assert (total.input_tokens, total.output_tokens, total.generations) == (2000, 1000, 1)
    assert total.estimated_cost_usd == pytest.approx(2000 * 0.40 / 1e6 + 1000 * 1.60 / 1e6)


def test_usage_is_estimated_when_the_provider_reports_none(
    make_client: ClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def silent(*_args: Any, **_kwargs: Any) -> AsyncIterator[LLMEvent]:
        yield TextDelta("x" * 400)

    client, container = make_client(openai_api_key="sk-test", rate_limit_enabled=False)
    monkeypatch.setattr(container.llm, "stream_markdown", silent)

    generate(client)

    records = container.usage._repository._records  # type: ignore[attr-defined]
    total = records[(GLOBAL_OWNER_ID, utc_day(datetime.now(UTC)))]
    assert total.output_tokens == 100
    assert total.input_tokens > 0
    assert total.estimated_cost_usd > 0


def test_mock_mode_never_spends_budget(make_client: ClientFactory) -> None:
    client, container = make_client(global_daily_llm_budget_usd=0.01, rate_limit_enabled=False)

    for _ in range(3):
        assert generate(client).status_code == 200

    assert client.get("/quota", headers=ALICE).json()["llmAvailable"] is True


def test_usage_store_failure_refuses_generation_instead_of_failing_open(
    make_client: ClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unavailable(*_args: Any, **_kwargs: Any) -> None:
        raise RepositoryUnavailableError("down")

    client, container = make_client(rate_limit_enabled=False)
    monkeypatch.setattr(container.usage._repository, "get", unavailable)  # type: ignore[attr-defined]

    assert_problem(generate(client), 503, "usage_unavailable")
