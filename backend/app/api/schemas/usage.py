from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class QuotaResponse(BaseModel):
    scope: Literal["user", "guest"]
    limit: int
    used: int
    remaining: int
    resetsAt: datetime
    # False once the global daily LLM budget is spent; generations return 503 until ``resetsAt``.
    llmAvailable: bool
    # True when the server runs without an OpenAI key and returns deterministic sample output.
    demo: bool
