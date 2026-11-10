import json
import logging

from fastapi.testclient import TestClient

from app.api.deps import get_tool_caller
from app.core.logging import JsonFormatter, configure_logging


def test_unknown_route_returns_problem_json(client: TestClient) -> None:
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "https://github.com/salmanfs815/ai-job-app-assist/blob/master/docs/errors.md#http_404",
        "title": "Not Found",
        "status": 404,
        "detail": "Not Found",
        "code": "http_404",
    }


def test_validation_errors_list_fields_without_echoing_input(client: TestClient) -> None:
    response = client.post("/generate/cover-letter", json={"resume_text": "too short"})

    body = response.json()
    assert response.status_code == 422
    assert body["code"] == "validation_error"
    fields = {error["field"] for error in body["errors"]}
    assert {"resume_text", "job_description_text", "company_name", "role_title"} <= fields
    assert isinstance(body["detail"], str)
    assert "too short" not in response.text


def test_unhandled_errors_are_hidden_behind_a_generic_problem(client: TestClient) -> None:
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    client.app.dependency_overrides[get_tool_caller] = boom  # type: ignore[attr-defined]
    quiet = TestClient(client.app, raise_server_exceptions=False)

    response = quiet.get("/quota")

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert "secret internal detail" not in response.text


def test_json_log_formatter_includes_extras_and_exceptions() -> None:
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    record.userId = "user-1"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["userId"] == "user-1"
    configure_logging("warning")
    configure_logging("info")  # idempotent: no duplicate handlers
    handlers = [h for h in logging.getLogger().handlers if isinstance(h.formatter, JsonFormatter)]
    assert len(handlers) == 1
