"""Acceptance tests for §8.2 and §8.3: sign-in, guest mode, account deletion, saved resumes."""

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.container import AppContainer
from app.api.deps import require_role
from app.auth.principal import ADMIN_ROLE
from app.auth.tokens import EntraTokenValidator, JwksCache
from app.repositories.base import RepositoryUnavailableError
from app.repositories.memory import InMemoryResultsRepository
from tests.conftest import ClientFactory
from tests.support import API_CLIENT_ID, ISSUER, TENANT_ID, USER_OID, FakeJwks, SigningKey, make_token

RESUME_TEXT = "Backend engineer with Python, FastAPI and Azure experience."
GENERATE = {
    "resume_text": RESUME_TEXT,
    "job_description_text": "Seeking a backend engineer to build Python APIs and reliable cloud services.",
}
ALICE = {"X-Dev-User": "alice"}
BOB = {"X-Dev-User": "bob"}


@pytest.fixture(scope="module")
def key() -> SigningKey:
    return SigningKey("test-key")


@pytest.fixture
def entra(make_client: ClientFactory, key: SigningKey) -> tuple[TestClient, AppContainer, FakeJwks]:
    """An app in real (Entra) auth mode whose signing keys come from a local fake JWKS."""
    client, container = make_client(
        environment="production",
        auth_mode="entra",
        entra_tenant_id=TENANT_ID,
        entra_tenant_subdomain="jobassist",
        entra_api_client_id=API_CLIENT_ID,
        rate_limit_enabled=False,
    )
    jwks = FakeJwks(key)
    container.token_validator = EntraTokenValidator(
        issuer=ISSUER,
        audiences=container.settings.resolved_entra_audiences,
        jwks=JwksCache(jwks),
        required_scope="access_as_user",
    )
    return client, container, jwks


@pytest.fixture
def dev(make_client: ClientFactory) -> tuple[TestClient, AppContainer]:
    return make_client(auth_mode="dev", rate_limit_enabled=False)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def assert_problem(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    body: dict[str, Any] = response.json()
    assert body["code"] == code
    return body


# --- Real token validation ---------------------------------------------------------------


def test_valid_token_signs_in_and_creates_the_account(
    entra: tuple[TestClient, AppContainer, FakeJwks], key: SigningKey
) -> None:
    client, _, _ = entra

    response = client.get("/me", headers=bearer(make_token(key, roles=[ADMIN_ROLE])))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == USER_OID
    assert body["email"] == "alice@example.test"
    assert body["displayName"] == "Alice Example"
    assert body["roles"] == [ADMIN_ROLE]
    assert body["quota"]["scope"] == "user"
    assert body["quota"]["limit"] == 20
    # The same account is returned on the next request.
    assert client.get("/me", headers=bearer(make_token(key))).json()["createdAt"] == body["createdAt"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": int(time.time()) - 3600},
        {"aud": "another-api"},
        {"iss": "https://login.evil.example/v2.0"},
    ],
    ids=["expired", "wrong-audience", "wrong-issuer"],
)
def test_invalid_tokens_are_rejected_with_401(
    entra: tuple[TestClient, AppContainer, FakeJwks], key: SigningKey, overrides: dict[str, Any]
) -> None:
    client, _, _ = entra

    response = client.get("/me", headers=bearer(make_token(key, **overrides)))

    assert_problem(response, 401, "invalid_token")
    assert response.headers["www-authenticate"].startswith("Bearer")


def test_token_signed_by_an_untrusted_key_is_rejected(entra: tuple[TestClient, AppContainer, FakeJwks]) -> None:
    client, _, _ = entra

    response = client.get("/me", headers=bearer(make_token(SigningKey("attacker-key"))))

    assert_problem(response, 401, "invalid_token")


def test_a_bad_token_is_never_downgraded_to_guest_access(
    entra: tuple[TestClient, AppContainer, FakeJwks], key: SigningKey
) -> None:
    client, _, _ = entra
    expired = bearer(make_token(key, exp=int(time.time()) - 3600))

    # Guests may call this endpoint, but a request that presents a token must present a valid one.
    assert_problem(client.get("/quota", headers=expired), 401, "invalid_token")
    assert_problem(client.post("/generate/resume-suggestions", json=GENERATE, headers=expired), 401, "invalid_token")
    assert_problem(client.get("/quota", headers={"Authorization": "Basic abc"}), 401, "invalid_token")


def test_token_without_the_api_scope_is_forbidden(
    entra: tuple[TestClient, AppContainer, FakeJwks], key: SigningKey
) -> None:
    client, _, _ = entra

    response = client.get("/me", headers=bearer(make_token(key, scp="other.scope")))

    assert_problem(response, 403, "insufficient_scope")


def test_service_tokens_cannot_use_user_endpoints(
    entra: tuple[TestClient, AppContainer, FakeJwks], key: SigningKey
) -> None:
    client, _, _ = entra
    service = bearer(make_token(key, scp=None, roles=["Postings.Ingest"], azp="watcher"))

    assert_problem(client.get("/me", headers=service), 403, "forbidden")
    assert_problem(client.get("/resumes", headers=service), 403, "forbidden")
    assert_problem(client.post("/generate/resume-suggestions", json=GENERATE, headers=service), 403, "forbidden")


def test_identity_provider_outage_is_a_503_not_a_401(
    entra: tuple[TestClient, AppContainer, FakeJwks], key: SigningKey
) -> None:
    client, _, jwks = entra
    jwks.fail = True

    response = client.get("/me", headers=bearer(make_token(key)))

    body = assert_problem(response, 503, "auth_unavailable")
    assert response.headers["Retry-After"] == str(body["retryAfterSeconds"])


def test_dev_headers_do_nothing_in_entra_mode(entra: tuple[TestClient, AppContainer, FakeJwks]) -> None:
    client, _, _ = entra

    assert_problem(client.get("/me", headers=ALICE), 401, "authentication_required")


def test_sign_in_unavailable_when_entra_is_not_configured(make_client: ClientFactory, key: SigningKey) -> None:
    client, container = make_client(environment="production", auth_mode="entra", rate_limit_enabled=False)

    assert container.token_validator is None
    assert_problem(client.get("/me", headers=bearer(make_token(key))), 401, "auth_not_configured")
    # The public demo keeps working for guests.
    assert client.post("/generate/resume-suggestions", json=GENERATE).status_code == 200


def test_validator_is_built_from_settings_when_entra_is_configured(make_client: ClientFactory) -> None:
    _, container = make_client(
        environment="production",
        auth_mode="entra",
        entra_tenant_id=TENANT_ID,
        entra_tenant_subdomain="jobassist",
        entra_api_client_id=API_CLIENT_ID,
    )

    assert isinstance(container.token_validator, EntraTokenValidator)


# --- Guest mode --------------------------------------------------------------------------


def test_guests_can_use_the_tool_but_nothing_else(dev: tuple[TestClient, AppContainer]) -> None:
    client, _ = dev

    assert client.get("/quota").json()["scope"] == "guest"
    assert client.post("/generate/resume-suggestions", json=GENERATE).status_code == 200
    for method, path in [("GET", "/me"), ("DELETE", "/me"), ("GET", "/resumes"), ("POST", "/resumes")]:
        response = client.request(method, path, json={"name": "x", "text": RESUME_TEXT})
        assert_problem(response, 401, "authentication_required")
        assert response.headers["www-authenticate"] == "Bearer"


def test_guest_mode_can_be_switched_off(make_client: ClientFactory) -> None:
    client, _ = make_client(auth_mode="dev", guest_mode_enabled=False, rate_limit_enabled=False)

    assert_problem(client.get("/quota"), 401, "authentication_required")
    assert_problem(client.post("/generate/resume-suggestions", json=GENERATE), 401, "authentication_required")
    assert_problem(
        client.post("/resume/extract", files={"resume_file": ("cv.pdf", b"x", "application/pdf")}),
        401,
        "authentication_required",
    )
    assert client.get("/health").status_code == 200
    assert client.get("/quota", headers=ALICE).status_code == 200


def test_signed_in_users_get_their_own_larger_quota(make_client: ClientFactory) -> None:
    client, _ = make_client(
        auth_mode="dev", user_daily_generation_limit=2, guest_daily_generation_limit=1, rate_limit_enabled=False
    )

    assert client.post("/generate/resume-suggestions", json=GENERATE).status_code == 200
    assert_problem(client.post("/generate/resume-suggestions", json=GENERATE), 429, "quota_exceeded")
    # Signing in from the same address gives a separate, larger allowance.
    for _ in range(2):
        assert client.post("/generate/resume-suggestions", json=GENERATE, headers=ALICE).status_code == 200
    body = assert_problem(
        client.post("/generate/resume-suggestions", json=GENERATE, headers=ALICE), 429, "quota_exceeded"
    )
    assert body["scope"] == "user"
    assert "free" not in body["detail"]
    # Another user is unaffected.
    assert client.get("/quota", headers=BOB).json()["remaining"] == 2


# --- Role checks -------------------------------------------------------------------------


def test_role_guard_allows_only_holders_of_the_role(dev: tuple[TestClient, AppContainer]) -> None:
    client, _ = dev
    app = client.app

    @app.get("/admin-only-test", dependencies=[])  # type: ignore[attr-defined]
    async def admin_only(principal: Any = pytest.importorskip("fastapi").Depends(require_role(ADMIN_ROLE))) -> dict:
        return {"id": principal.id}

    assert client.get("/admin-only-test", headers={**ALICE, "X-Dev-Roles": "Admin"}).json() == {"id": "dev-alice"}
    assert_problem(client.get("/admin-only-test", headers=ALICE), 403, "forbidden")
    assert_problem(client.get("/admin-only-test"), 401, "authentication_required")


# --- Saved resumes -----------------------------------------------------------------------


def create_resume(client: TestClient, headers: dict[str, str], name: str, **extra: Any) -> dict[str, Any]:
    response = client.post("/resumes", json={"name": name, "text": RESUME_TEXT, **extra}, headers=headers)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    assert response.headers["Location"] == f"/resumes/{body['id']}"
    return body


def test_resume_lifecycle(dev: tuple[TestClient, AppContainer]) -> None:
    client, _ = dev

    first = create_resume(client, ALICE, "General", sourceFilename="cv.pdf", ocrStatus="used")
    second = create_resume(client, ALICE, "Backend")

    assert first["isDefault"] is True
    assert (first["sourceFilename"], first["ocrStatus"], first["charCount"]) == ("cv.pdf", "used", len(RESUME_TEXT))
    assert first["text"] == RESUME_TEXT
    assert second["isDefault"] is False

    listing = client.get("/resumes", headers=ALICE).json()
    assert [item["name"] for item in listing["items"]] == ["General", "Backend"]
    assert listing["nextCursor"] is None
    assert "text" not in listing["items"][0]  # list responses stay small

    patched = client.patch(
        f"/resumes/{second['id']}", json={"name": "Backend (Python)", "isDefault": True}, headers=ALICE
    )
    assert patched.status_code == 200
    assert (patched.json()["name"], patched.json()["isDefault"]) == ("Backend (Python)", True)
    assert client.get(f"/resumes/{first['id']}", headers=ALICE).json()["isDefault"] is False

    assert client.delete(f"/resumes/{second['id']}", headers=ALICE).status_code == 204
    remaining = client.get("/resumes", headers=ALICE).json()["items"]
    assert [(item["name"], item["isDefault"]) for item in remaining] == [("General", True)]


def test_resumes_are_private_to_their_owner(dev: tuple[TestClient, AppContainer]) -> None:
    client, _ = dev
    mine = create_resume(client, ALICE, "Mine")

    assert client.get("/resumes", headers=BOB).json()["items"] == []
    assert_problem(client.get(f"/resumes/{mine['id']}", headers=BOB), 404, "resume_not_found")
    assert_problem(client.patch(f"/resumes/{mine['id']}", json={"name": "x"}, headers=BOB), 404, "resume_not_found")
    assert_problem(client.delete(f"/resumes/{mine['id']}", headers=BOB), 404, "resume_not_found")
    assert client.get(f"/resumes/{mine['id']}", headers=ALICE).status_code == 200


def test_resume_validation_and_limits(make_client: ClientFactory) -> None:
    client, _ = make_client(auth_mode="dev", max_resumes_per_user=1, rate_limit_enabled=False)

    too_short = client.post("/resumes", json={"name": "CV", "text": "short"}, headers=ALICE)
    blank = client.post("/resumes", json={"name": "   ", "text": RESUME_TEXT}, headers=ALICE)
    assert_problem(too_short, 422, "validation_error")
    assert "resume needs a name" in assert_problem(blank, 422, "validation_error")["detail"]

    created = create_resume(client, ALICE, "Only one")
    body = assert_problem(
        client.post("/resumes", json={"name": "Two", "text": RESUME_TEXT}, headers=ALICE), 409, "resume_limit_reached"
    )
    assert body["limit"] == 1

    unset = client.patch(f"/resumes/{created['id']}", json={"isDefault": False}, headers=ALICE)
    assert "Choose another resume" in assert_problem(unset, 422, "validation_error")["detail"]


# --- Account deletion ----------------------------------------------------------------------


def test_delete_me_removes_resumes_results_and_usage(dev: tuple[TestClient, AppContainer]) -> None:
    client, container = dev
    results = InMemoryResultsRepository()
    container.results = results
    container.users._results = results  # type: ignore[attr-defined]
    for headers in (ALICE, BOB):
        create_resume(client, headers, "CV")
        assert client.post("/generate/resume-suggestions", json=GENERATE, headers=headers).status_code == 200
    created_at = client.get("/me", headers=ALICE).json()["createdAt"]

    response = client.delete("/me", headers=ALICE)

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "resumes": 1, "results": 1, "usageRecords": 1}
    assert [item["userId"] for item in results.items] == ["dev-bob"]
    assert client.get("/resumes", headers=BOB).json()["items"] != []
    assert client.get("/quota", headers=BOB).json()["used"] == 1
    # Signing in again starts from a clean, new account.
    fresh = client.get("/me", headers=ALICE).json()
    assert fresh["quota"]["used"] == 0
    assert fresh["createdAt"] >= created_at
    assert client.get("/resumes", headers=ALICE).json()["items"] == []


def test_storage_outage_is_reported_as_503(dev: tuple[TestClient, AppContainer], monkeypatch) -> None:
    client, container = dev

    async def unavailable(*_args: Any, **_kwargs: Any) -> None:
        raise RepositoryUnavailableError("down")

    client.get("/me", headers=ALICE)
    monkeypatch.setattr(container.resumes._repository, "list_for_user", unavailable)  # type: ignore[attr-defined]
    listing = client.get("/resumes", headers=ALICE)
    monkeypatch.setattr(container.users._users, "get", unavailable)  # type: ignore[attr-defined]
    account = client.get("/me", headers=BOB)

    for response in (listing, account):
        body = assert_problem(response, 503, "storage_unavailable")
        assert response.headers["Retry-After"] == str(body["retryAfterSeconds"])


def test_openapi_lists_the_account_and_resume_endpoints(dev: tuple[TestClient, AppContainer]) -> None:
    paths = dev[0].get("/openapi.json").json()["paths"]

    assert {"get", "delete"} <= set(paths["/me"])
    assert {"get", "post"} <= set(paths["/resumes"])
    assert {"get", "patch", "delete"} <= set(paths["/resumes/{resume_id}"])
    assert "401" in paths["/resumes"]["get"]["responses"]
