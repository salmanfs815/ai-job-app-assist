"""The signed-in user's account."""

from fastapi import APIRouter

from app.api.deps import Container, CurrentUser, UserPrincipal
from app.api.routers.usage import build_quota_response
from app.api.schemas.accounts import AccountDeletedResponse, MeResponse
from app.api.schemas.problem import problem_responses

router = APIRouter(tags=["account"])


@router.get("/me", response_model=MeResponse, responses=problem_responses(401, 403, 429, 503))
async def get_me(user: CurrentUser, principal: UserPrincipal, container: Container) -> MeResponse:
    """Profile and today's allowance. The account is created on the first call after sign-in."""
    quota = await build_quota_response(container, principal)
    return MeResponse.from_domain(user, principal.roles, quota)


@router.delete("/me", response_model=AccountDeletedResponse, responses=problem_responses(401, 403, 429, 503))
async def delete_me(principal: UserPrincipal, container: Container) -> AccountDeletedResponse:
    """Delete the account and everything stored for it: resumes, results and usage records.

    The sign-in identity itself lives in Microsoft Entra External ID and is not removed here;
    signing in again simply creates a fresh, empty account.
    """
    summary = await container.users.delete_account(principal.id)
    return AccountDeletedResponse(
        resumes=summary.resumes,
        results=summary.results,
        usageRecords=summary.usage_records,
    )
