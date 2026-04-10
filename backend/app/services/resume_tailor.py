from app.models.schemas import AnalyzeLLMResult
from app.services.llm_client import call_llm_json
from app.services.parser import parse_analyze_output
from app.services.prompt_engineering import build_analyze_prompt


def analyze_resume_against_jd(resume_text: str, jd_text: str, tone: str) -> AnalyzeLLMResult:
    prompt = build_analyze_prompt(resume_text, jd_text, tone)
    raw = call_llm_json(prompt)
    return parse_analyze_output(raw)
