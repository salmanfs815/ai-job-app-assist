"""Saved resumes. Text and metadata only: uploaded files are parsed by ``/resume/extract`` and discarded."""

from fastapi import APIRouter, Response, status

from app.api.deps import Container, CurrentUser
from app.api.schemas.accounts import (
    CreateResumeRequest,
    ResumeDetail,
    ResumeListResponse,
    ResumeSummary,
    UpdateResumeRequest,
)
from app.api.schemas.problem import problem_responses
from app.core.errors import ProblemError
from app.domain.resumes import ResumeValidationError
from app.services.resumes import ResumeLimitError, ResumeNotFoundError

router = APIRouter(prefix="/resumes", tags=["resumes"])


def _not_found() -> ProblemError:
    return ProblemError(404, "That resume does not exist.", code="resume_not_found")


@router.get("", response_model=ResumeListResponse, responses=problem_responses(401, 403, 429, 503))
async def list_resumes(user: CurrentUser, container: Container) -> ResumeListResponse:
    resumes = await container.resumes.list_for_user(user.id)
    return ResumeListResponse(items=[ResumeSummary.from_domain(resume) for resume in resumes])


@router.post(
    "",
    response_model=ResumeDetail,
    status_code=status.HTTP_201_CREATED,
    responses=problem_responses(401, 403, 409, 422, 429, 503),
)
async def create_resume(
    payload: CreateResumeRequest, user: CurrentUser, container: Container, response: Response
) -> ResumeDetail:
    try:
        resume = await container.resumes.create(
            user.id,
            name=payload.name,
            text=payload.text,
            source_filename=payload.sourceFilename,
            ocr_status=payload.ocrStatus,
            make_default=payload.makeDefault,
        )
    except ResumeLimitError as exc:
        raise ProblemError(409, str(exc), code="resume_limit_reached", extensions={"limit": exc.limit}) from exc
    except ResumeValidationError as exc:
        raise ProblemError(422, str(exc), code="validation_error") from exc
    response.headers["Location"] = f"/resumes/{resume.id}"
    return ResumeDetail.from_domain(resume)


@router.get("/{resume_id}", response_model=ResumeDetail, responses=problem_responses(401, 403, 404, 429, 503))
async def get_resume(resume_id: str, user: CurrentUser, container: Container) -> ResumeDetail:
    try:
        return ResumeDetail.from_domain(await container.resumes.get(user.id, resume_id))
    except ResumeNotFoundError as exc:
        raise _not_found() from exc


@router.patch(
    "/{resume_id}",
    response_model=ResumeSummary,
    responses=problem_responses(401, 403, 404, 422, 429, 503),
)
async def update_resume(
    resume_id: str, payload: UpdateResumeRequest, user: CurrentUser, container: Container
) -> ResumeSummary:
    """Rename a resume and/or make it the default."""
    try:
        resume = await container.resumes.update(user.id, resume_id, name=payload.name, is_default=payload.isDefault)
    except ResumeNotFoundError as exc:
        raise _not_found() from exc
    except ResumeValidationError as exc:
        raise ProblemError(422, str(exc), code="validation_error") from exc
    return ResumeSummary.from_domain(resume)


@router.delete(
    "/{resume_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=problem_responses(401, 403, 404, 429, 503),
)
async def delete_resume(resume_id: str, user: CurrentUser, container: Container) -> Response:
    try:
        await container.resumes.delete(user.id, resume_id)
    except ResumeNotFoundError as exc:
        raise _not_found() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
