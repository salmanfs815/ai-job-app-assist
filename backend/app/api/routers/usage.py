from fastapi import APIRouter

from app.api.deps import Container, Subject
from app.api.schemas.problem import problem_responses
from app.api.schemas.usage import QuotaResponse

router = APIRouter(tags=["usage"])


@router.get("/quota", response_model=QuotaResponse, responses=problem_responses(429))
async def get_quota(container: Container, subject: Subject) -> QuotaResponse:
    """Today's generation allowance for the caller, so the UI can show what is left."""
    quota = await container.usage.quota_status(subject)
    budget = await container.usage.budget_status()
    return QuotaResponse(
        scope="user" if quota.kind.value == "user" else "guest",
        limit=quota.limit,
        used=quota.used,
        remaining=quota.remaining,
        resetsAt=quota.resets_at,
        llmAvailable=not budget.exhausted,
        demo=container.llm.mock,
    )
