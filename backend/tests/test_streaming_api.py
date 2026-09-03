from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.api import routes
from app.config import settings
from app.main import app
from app.services.prompt_engineering import build_resume_suggestions_messages
from app.services.file_parsing import _join_pdf_pages
from app.services.streaming import LLMStreamError


client = TestClient(app)


def _analysis_payload() -> dict[str, str]:
    return {
        "resume_text": "Backend engineer with Python API and cloud delivery experience.",
        "job_description_text": "Seeking a backend engineer to build Python APIs and reliable cloud services.",
        "tone": "professional",
    }


def test_pdf_page_markers_preserve_original_page_numbers() -> None:
    extracted = _join_pdf_pages(["Page one content", "", "Page three content"])

    assert extracted == "[Page 1]\nPage one content\n\n[Page 3]\nPage three content"


def test_extract_resume_returns_text_and_ocr_status(monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "extract_text_from_resume_file",
        lambda _filename, _content: ("Extracted resume text with enough content for validation.", "not_used"),
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


def test_extract_job_description_returns_editable_text(monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "extract_text_from_resume_file",
        lambda _filename, _content: ("Senior integration lead role with SQL and ETL requirements.", "not_used"),
    )

    response = client.post(
        "/job-description/extract",
        files={"job_description_file": ("job-description.docx", b"docx bytes", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "job_description_text": "Senior integration lead role with SQL and ETL requirements.",
        "ocr_status": "not_used",
    }


def test_extract_resume_rejects_empty_and_oversized_files(monkeypatch) -> None:
    empty = client.post(
        "/resume/extract",
        files={"resume_file": ("resume.pdf", b"", "application/pdf")},
    )
    assert empty.status_code == 400

    monkeypatch.setattr(settings, "max_upload_bytes", 3)
    oversized = client.post(
        "/resume/extract",
        files={"resume_file": ("resume.pdf", b"1234", "application/pdf")},
    )
    assert oversized.status_code == 413


def test_extract_resume_rejects_unsupported_and_insufficient_content(monkeypatch) -> None:
    unsupported = client.post(
        "/resume/extract",
        files={"resume_file": ("resume.txt", b"plain text", "text/plain")},
    )
    assert unsupported.status_code == 400

    monkeypatch.setattr(routes, "extract_text_from_resume_file", lambda _filename, _content: ("short", "failed"))
    insufficient = client.post(
        "/resume/extract",
        files={"resume_file": ("resume.pdf", b"pdf bytes", "application/pdf")},
    )
    assert insufficient.status_code == 400


def test_resume_suggestions_streams_sse_and_persists_completed_markdown(monkeypatch) -> None:
    monkeypatch.setattr(settings, "openai_api_key", "")
    persist = Mock()
    monkeypatch.setattr(routes, "save_resume_suggestions", persist)

    response = client.post("/generate/resume-suggestions", json=_analysis_payload())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: status" in response.text
    assert "event: delta" in response.text
    assert "event: done" in response.text
    assert "# Match score: 78/100" in response.text
    persist.assert_called_once()
    assert "# Match score: 78/100" in persist.call_args.kwargs["generated_markdown"]


def test_cover_letter_streams_and_persists_completed_markdown(monkeypatch) -> None:
    monkeypatch.setattr(settings, "openai_api_key", "")
    persist = Mock()
    monkeypatch.setattr(routes, "save_cover_letter", persist)
    payload = {
        **_analysis_payload(),
        "company_name": "Example Company",
        "role_title": "Backend Engineer",
    }

    response = client.post("/generate/cover-letter", json=payload)

    assert response.status_code == 200
    assert "event: status" in response.text
    assert "event: delta" in response.text
    assert "event: done" in response.text
    assert "Dear Hiring Manager" in response.text
    persist.assert_called_once()
    assert "Dear Hiring Manager" in persist.call_args.kwargs["generated_text"]


def test_stream_error_is_reported_and_partial_output_is_not_persisted(monkeypatch) -> None:
    async def failing_stream(*_args, **_kwargs):
        yield "Partial text"
        raise LLMStreamError("Temporary upstream failure", retryable=True)

    persist = Mock()
    monkeypatch.setattr(routes, "stream_chat_markdown", failing_stream)
    monkeypatch.setattr(routes, "save_resume_suggestions", persist)

    response = client.post("/generate/resume-suggestions", json=_analysis_payload())

    assert "event: error" in response.text
    assert '"retryable": true' in response.text
    assert '"partial": true' in response.text
    assert "event: done" not in response.text
    persist.assert_not_called()


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


def test_legacy_routes_are_removed() -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert "/analyze" not in paths
    assert "/analyze-upload" not in paths
    assert "/cover-letter" not in paths
    assert "/cover-letter-upload" not in paths
