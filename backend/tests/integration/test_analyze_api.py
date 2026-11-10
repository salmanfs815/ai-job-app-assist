from collections.abc import AsyncIterator
from typing import Any

from fastapi.testclient import TestClient

from app.api.routers import analyze
from app.domain.prompts import build_resume_suggestions_messages
from app.integrations.llm import LLMEvent, LLMStreamError, TextDelta
from app.parsing.file_parsing import _join_pdf_pages
from app.repositories.memory import InMemoryResultsRepository
from tests.conftest import ClientFactory


def analysis_payload() -> dict[str, str]:
    return {
        "resume_text": "Backend engineer with Python API and cloud delivery experience.",
        "job_description_text": "Seeking a backend engineer to build Python APIs and reliable cloud services.",
        "tone": "professional",
    }


def fake_extract(text: str, status: str = "not_used") -> Any:
    return lambda _filename, _content, **_options: (text, status)


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_pdf_page_markers_preserve_original_page_numbers() -> None:
    extracted = _join_pdf_pages(["Page one content", "", "Page three content"])

    assert extracted == "[Page 1]\nPage one content\n\n[Page 3]\nPage three content"


def test_extract_resume_returns_text_and_ocr_status(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        analyze,
        "extract_text_from_resume_file",
        fake_extract("Extracted resume text with enough content for validation."),
    )

    response = client.post(
        "/resume/extract",
        files={"resume_file": ("resume.pdf", b"pdf bytes", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "resume_text": "Extracted resume text with enough content for validation.",
        "ocr_status": "not_used",
    }


def test_extract_job_description_returns_editable_text(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        analyze,
        "extract_text_from_resume_file",
        fake_extract("Senior integration lead role with SQL and ETL requirements."),
    )

    response = client.post(
        "/job-description/extract",
        files={
            "job_description_file": (
                "job-description.docx",
                b"docx bytes",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "job_description_text": "Senior integration lead role with SQL and ETL requirements.",
        "ocr_status": "not_used",
    }


def test_extract_resume_rejects_empty_and_oversized_files(make_client: ClientFactory) -> None:
    client, _ = make_client(max_upload_bytes=3)

    empty = client.post("/resume/extract", files={"resume_file": ("resume.pdf", b"", "application/pdf")})
    oversized = client.post("/resume/extract", files={"resume_file": ("resume.pdf", b"1234", "application/pdf")})

    assert empty.status_code == 400
    assert oversized.status_code == 413
    assert oversized.headers["content-type"] == "application/problem+json"
    assert "too large" in oversized.json()["detail"]


def test_extract_resume_rejects_unsupported_and_insufficient_content(client: TestClient, monkeypatch) -> None:
    unsupported = client.post(
        "/resume/extract",
        files={"resume_file": ("resume.txt", b"plain text", "text/plain")},
    )
    assert unsupported.status_code == 400
    assert "PDF or DOCX" in unsupported.json()["detail"]

    monkeypatch.setattr(analyze, "extract_text_from_resume_file", fake_extract("short", "failed"))
    insufficient = client.post(
        "/resume/extract",
        files={"resume_file": ("resume.pdf", b"pdf bytes", "application/pdf")},
    )
    assert insufficient.status_code == 400


def test_extract_passes_ocr_settings_to_the_parser(make_client: ClientFactory, monkeypatch) -> None:
    seen: dict[str, Any] = {}

    def capture(_filename: str, _content: bytes, **options: Any) -> tuple[str, str]:
        seen.update(options)
        return "Extracted resume text with enough content for validation.", "not_used"

    monkeypatch.setattr(analyze, "extract_text_from_resume_file", capture)
    client, _ = make_client(enable_pdf_ocr_fallback=False, tesseract_cmd="/opt/tesseract")

    client.post("/resume/extract", files={"resume_file": ("resume.pdf", b"pdf bytes", "application/pdf")})

    assert seen == {"enable_ocr": False, "tesseract_cmd": "/opt/tesseract"}


DEV_USER = {"X-Dev-User": "alice"}


def test_resume_suggestions_streams_sse_and_persists_completed_markdown(make_client: ClientFactory) -> None:
    client, container = make_client(auth_mode="dev")
    results = InMemoryResultsRepository()
    container.results = results

    response = client.post("/generate/resume-suggestions", json=analysis_payload(), headers=DEV_USER)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: status" in response.text
    assert "event: delta" in response.text
    assert "event: done" in response.text
    assert '"demo": true' in response.text
    assert "# Match score: 78/100" in response.text
    assert len(results.items) == 1
    assert "# Match score: 78/100" in results.items[0]["generated_markdown"]
    assert results.items[0]["userId"] == "dev-alice"


def test_cover_letter_streams_and_persists_completed_markdown(make_client: ClientFactory) -> None:
    client, container = make_client(auth_mode="dev")
    results = InMemoryResultsRepository()
    container.results = results
    payload = {**analysis_payload(), "company_name": "Example Company", "role_title": "Backend Engineer"}

    response = client.post("/generate/cover-letter", json=payload, headers=DEV_USER)

    assert response.status_code == 200
    assert "event: status" in response.text
    assert "event: delta" in response.text
    assert "event: done" in response.text
    assert "Dear Hiring Manager" in response.text
    assert len(results.items) == 1
    assert "Dear Hiring Manager" in results.items[0]["generated_text"]
    assert results.items[0]["company_name"] == "Example Company"


def test_guest_results_are_streamed_but_never_persisted(make_client: ClientFactory) -> None:
    client, container = make_client()
    results = InMemoryResultsRepository()
    container.results = results

    response = client.post("/generate/resume-suggestions", json=analysis_payload())

    assert "event: done" in response.text
    assert "Finalizing and saving" not in response.text
    assert results.items == []


def test_stream_error_is_reported_and_partial_output_is_not_persisted(make_client: ClientFactory) -> None:
    async def failing_stream(*_args: Any, **_kwargs: Any) -> AsyncIterator[LLMEvent]:
        yield TextDelta("Partial text")
        raise LLMStreamError("Temporary upstream failure", retryable=True)

    client, container = make_client(auth_mode="dev")
    results = InMemoryResultsRepository()
    container.results = results
    container.llm.stream_markdown = failing_stream  # type: ignore[method-assign]

    response = client.post("/generate/resume-suggestions", json=analysis_payload(), headers=DEV_USER)

    assert "event: error" in response.text
    assert '"retryable": true' in response.text
    assert '"partial": true' in response.text
    assert "event: done" not in response.text
    assert results.items == []


def test_empty_model_output_is_reported_as_an_error(make_client: ClientFactory) -> None:
    async def empty_stream(*_args: Any, **_kwargs: Any) -> AsyncIterator[LLMEvent]:
        yield TextDelta("   ")

    client, container = make_client()
    container.llm.stream_markdown = empty_stream  # type: ignore[method-assign]

    response = client.post("/generate/resume-suggestions", json=analysis_payload())

    assert "empty response" in response.text
    assert "event: done" not in response.text


def test_oversized_text_is_rejected_before_any_llm_work(make_client: ClientFactory) -> None:
    client, container = make_client()
    payload = {**analysis_payload(), "resume_text": "x" * 60_001}

    response = client.post("/generate/resume-suggestions", json=payload)

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["errors"][0]["field"] == "resume_text"
    assert "x" * 100 not in response.text  # the submitted text is not echoed back


def test_resume_prompt_requires_complete_rewrite_without_fabrication() -> None:
    messages = build_resume_suggestions_messages("resume", "job", "professional")
    system_prompt = messages[0]["content"]

    assert "headline or title" in system_prompt
    assert "professional summary" in system_prompt
    assert "Do not limit recommendations to experience bullets" in system_prompt
    assert "Never invent qualifications" in system_prompt
    assert "complete, ready-to-use rewrite of the entire resume" in system_prompt
    assert "Group content that is already effective" in system_prompt
    assert "long master resume" in system_prompt
    assert "focused one- or two-page resume" in system_prompt
    assert "Otherwise, keep the rewritten resume close to the original overall length" in system_prompt
    assert "Preserve clean page and" in system_prompt
    assert "Complete tailored resume" in system_prompt
    assert "# Match score: NN/100" in system_prompt


def test_legacy_routes_are_removed(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert "/analyze" not in paths
    assert "/analyze-upload" not in paths
    assert "/cover-letter" not in paths
    assert "/cover-letter-upload" not in paths


def test_openapi_documents_limit_responses(client: TestClient) -> None:
    operation = client.get("/openapi.json").json()["paths"]["/generate/resume-suggestions"]["post"]

    assert {"200", "422", "429", "503"} <= set(operation["responses"])
    assert "application/problem+json" in operation["responses"]["429"]["content"]
