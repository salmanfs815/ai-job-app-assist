import json
import re

from pydantic import ValidationError

from app.models.schemas import AnalyzeLLMResult


def parse_analyze_output(raw_text: str) -> AnalyzeLLMResult:
    text = raw_text.strip()
    # Models sometimes wrap JSON in fenced code blocks.
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        if text.endswith("```"):
            text = text[:-3].strip()
    # If there is any extra text around the JSON, try to extract the outer object.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM output is not valid JSON") from exc

    try:
        return AnalyzeLLMResult.model_validate(data)
    except ValidationError as exc:
        raise ValueError("LLM output schema validation failed") from exc
