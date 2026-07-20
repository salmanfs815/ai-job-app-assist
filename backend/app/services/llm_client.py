import json

from openai import OpenAI
from openai import APIConnectionError, APITimeoutError, APIStatusError, RateLimitError

from app.config import settings


def _mock_analyze() -> str:
    return json.dumps(
        {
            "extracted_keywords": ["Python", "FastAPI", "Cloud" , "AWS"],
            "matched_skills": ["Python", "Cloud"],
            "missing_skills": ["FastAPI", "AWS"],
            "rewritten_bullets": [
                {
                    "original": "Built backend services for internal tools.",
                    "tailored": "Built Python APIs and optimized data workflows supporting scalable service delivery.",
                    "rationale": "Highlights backend/API impact and relevance to target stack.",
                }
            ],
            "summary": "Strong backend profile with opportunities to emphasize framework and cloud alignment.",
        }
    )


def _mock_cover_letter() -> str:
    return (
        "Dear Hiring Manager,\n\n"
        "I’m excited to apply for this role. I bring experience building backend services, improving reliability, "
        "and delivering measurable outcomes in cross-functional teams.\n\n"
        "In recent work, I designed API layers, strengthened data workflows, and focused on clear impact—"
        "performance, maintainability, and operational stability. I’m confident I can bring the same rigor and "
        "execution to your team.\n\n"
        "Thank you for your time and consideration. I’d welcome the chance to discuss how I can contribute.\n\n"
        "Sincerely,\nYour Name"
    )


def _chat_completion_text(client: OpenAI, prompt: str, temperature: float) -> str:
    """Use Chat Completions API (supported by openai>=1.x; no client.responses)."""
    resp = client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    choice0 = resp.choices[0]
    content = getattr(choice0.message, "content", None)
    if content is not None:
        return content
    return getattr(choice0, "text", "") or ""


def call_llm_json(prompt: str) -> str:
    if not settings.openai_api_key:
        return _mock_analyze()

    client = OpenAI(api_key=settings.openai_api_key)
    try:
        return _chat_completion_text(client, prompt, temperature=0.2)
    except RateLimitError:
        # Includes insufficient_quota 429 errors.
        return _mock_analyze()
    except (APITimeoutError, APIConnectionError):
        return _mock_analyze()
    except APIStatusError as exc:
        # Best-effort fallback for non-2xx responses.
        if getattr(exc, "status_code", None) == 429:
            return _mock_analyze()
        raise


def call_llm_text(prompt: str) -> str:
    if not settings.openai_api_key:
        return _mock_cover_letter()

    client = OpenAI(api_key=settings.openai_api_key)
    try:
        return _chat_completion_text(client, prompt, temperature=0.4)
    except RateLimitError:
        return _mock_cover_letter()
    except (APITimeoutError, APIConnectionError):
        return _mock_cover_letter()
    except APIStatusError as exc:
        if getattr(exc, "status_code", None) == 429:
            return _mock_cover_letter()
        raise
