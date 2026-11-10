from fastapi import APIRouter

from app.api.container import AppContainer
from app.api.deps import Container, ToolCaller
from app.api.schemas.problem import problem_responses
from app.api.schemas.usage import QuotaResponse
from app.auth.principal import Principal

router = APIRouter(tags=["usage"])


async def build_quota_response(container: AppContainer, principal: Principal) -> QuotaResponse:
    quota = await container.usage.quota_status(principal.quota_subject)
    budget = await container.usage.budget_status()
    return QuotaResponse(
        scope="user" if principal.is_user else "guest",
        limit=quota.limit,
        used=quota.used,
        remaining=quota.remaining,
        resetsAt=quota.resets_at,
        llmAvailable=not budget.exhausted,
        demo=container.llm.mock,
    )


@router.get("/quota", response_model=QuotaResponse, responses=problem_responses(401, 429))
async def get_quota(container: Container, caller: ToolCaller) -> QuotaResponse:
    """Today's generation allowance for the caller, so the UI can show what is left."""
    return await build_quota_response(container, caller)
