from datetime import UTC, datetime, timedelta
from itertools import count

import pytest

from app.domain.resumes import Resume, ResumeValidationError, clean_name, clean_text, next_default, sort_for_display
from app.repositories.memory import InMemoryResumeRepository
from app.services.resumes import ResumeLimitError, ResumeNotFoundError, ResumeService
from tests.conftest import FakeClock

TEXT = "Backend engineer with Python, FastAPI and Azure experience."
T0 = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


def make_resume(resume_id: str, *, default: bool = False, minutes: int = 0) -> Resume:
    moment = T0 + timedelta(minutes=minutes)
    return Resume(
        id=resume_id, user_id="u1", name=resume_id, text=TEXT, is_default=default, created_at=moment, updated_at=moment
    )


def make_service(clock: FakeClock, max_per_user: int = 3) -> tuple[ResumeService, InMemoryResumeRepository]:
    repository = InMemoryResumeRepository()
    ids = count(1)
    service = ResumeService(repository, max_per_user=max_per_user, clock=clock, new_id=lambda: f"r{next(ids)}")
    return service, repository


# --- Domain rules ------------------------------------------------------------------------


def test_names_are_trimmed_and_collapsed() -> None:
    assert clean_name("  Backend   resume \n") == "Backend resume"


@pytest.mark.parametrize("name", ["", "   ", "x" * 121])
def test_invalid_names_are_rejected(name: str) -> None:
    with pytest.raises(ResumeValidationError):
        clean_name(name)


def test_text_is_trimmed_and_length_checked() -> None:
    assert clean_text(f"  {TEXT}\n") == TEXT
    with pytest.raises(ResumeValidationError, match="too short"):
        clean_text("short")
    with pytest.raises(ResumeValidationError, match="at most"):
        clean_text("x" * 60_001)


def test_sorting_puts_the_default_first_then_most_recent() -> None:
    resumes = [make_resume("old", minutes=1), make_resume("default", default=True), make_resume("new", minutes=5)]

    assert [r.id for r in sort_for_display(resumes)] == ["default", "new", "old"]


def test_next_default_is_the_most_recent_when_none_is_default() -> None:
    assert next_default([]) is None
    assert next_default([make_resume("a", default=True), make_resume("b")]) is None
    promoted = next_default([make_resume("a", minutes=1), make_resume("b", minutes=9)])
    assert promoted is not None
    assert promoted.id == "b"


def test_content_hash_and_char_count_follow_the_text() -> None:
    resume = make_resume("a")

    assert resume.char_count == len(TEXT)
    assert len(resume.content_hash) == 64
    assert resume.with_default(False, T0) is resume  # no change, no new timestamp


# --- Service -----------------------------------------------------------------------------


async def test_first_resume_becomes_the_default(clock: FakeClock) -> None:
    service, _ = make_service(clock)

    first = await service.create("u1", name="  General  ", text=f" {TEXT} ", source_filename="cv.pdf")
    second = await service.create("u1", name="Backend", text=TEXT)

    assert (first.id, first.name, first.text, first.is_default) == ("r1", "General", TEXT, True)
    assert first.source_filename == "cv.pdf"
    assert not second.is_default


async def test_creating_with_make_default_moves_the_default(clock: FakeClock) -> None:
    service, _ = make_service(clock)
    await service.create("u1", name="General", text=TEXT)

    await service.create("u1", name="Backend", text=TEXT, make_default=True)

    listed = await service.list_for_user("u1")
    assert [(r.name, r.is_default) for r in listed] == [("Backend", True), ("General", False)]


async def test_resume_limit_is_enforced_per_user(clock: FakeClock) -> None:
    service, _ = make_service(clock, max_per_user=2)
    await service.create("u1", name="One", text=TEXT)
    await service.create("u1", name="Two", text=TEXT)

    with pytest.raises(ResumeLimitError) as excinfo:
        await service.create("u1", name="Three", text=TEXT)

    assert excinfo.value.limit == 2
    assert "up to 2 resumes" in str(excinfo.value)
    await service.create("u2", name="Other user", text=TEXT)  # separate allowance


async def test_invalid_resume_is_not_stored(clock: FakeClock) -> None:
    service, repository = make_service(clock)

    with pytest.raises(ResumeValidationError):
        await service.create("u1", name="Short", text="too short")

    assert await repository.list_for_user("u1") == []


async def test_rename_and_set_default(clock: FakeClock) -> None:
    service, _ = make_service(clock)
    first = await service.create("u1", name="General", text=TEXT)
    second = await service.create("u1", name="Backend", text=TEXT)
    clock.advance(minutes=5)

    renamed = await service.update("u1", second.id, name="Backend (Python)", is_default=True)

    assert renamed.name == "Backend (Python)"
    assert renamed.is_default
    assert renamed.updated_at > second.updated_at
    assert not (await service.get("u1", first.id)).is_default


async def test_default_cannot_be_unset_directly(clock: FakeClock) -> None:
    service, _ = make_service(clock)
    first = await service.create("u1", name="General", text=TEXT)

    with pytest.raises(ResumeValidationError, match="Choose another resume"):
        await service.update("u1", first.id, is_default=False)

    assert (await service.get("u1", first.id)).is_default


async def test_deleting_the_default_promotes_the_most_recent(clock: FakeClock) -> None:
    service, _ = make_service(clock)
    first = await service.create("u1", name="General", text=TEXT)
    clock.advance(minutes=1)
    await service.create("u1", name="Older", text=TEXT)
    clock.advance(minutes=1)
    newest = await service.create("u1", name="Newest", text=TEXT)

    await service.delete("u1", first.id)

    listed = await service.list_for_user("u1")
    assert [(r.id, r.is_default) for r in listed] == [(newest.id, True), ("r2", False)]


async def test_deleting_a_non_default_keeps_the_default(clock: FakeClock) -> None:
    service, _ = make_service(clock)
    first = await service.create("u1", name="General", text=TEXT)
    second = await service.create("u1", name="Backend", text=TEXT)

    await service.delete("u1", second.id)

    assert [r.id for r in await service.list_for_user("u1")] == [first.id]
    assert (await service.get("u1", first.id)).is_default


async def test_resumes_are_isolated_between_users(clock: FakeClock) -> None:
    service, _ = make_service(clock)
    mine = await service.create("u1", name="Mine", text=TEXT)

    with pytest.raises(ResumeNotFoundError):
        await service.get("u2", mine.id)
    with pytest.raises(ResumeNotFoundError):
        await service.update("u2", mine.id, name="Stolen")
    with pytest.raises(ResumeNotFoundError):
        await service.delete("u2", mine.id)
    assert await service.list_for_user("u2") == []
