import httpx
import pytest

from app.auth.principal import ADMIN_ROLE, Principal, PrincipalKind, guest_principal
from app.auth.resolver import AuthenticationError, bearer_token, dev_principal, resolve_principal
from app.auth.tokens import http_jwks_fetcher
from app.domain.usage import UsageKind


class StubValidator:
    def __init__(self) -> None:
        self.tokens: list[str] = []

    async def validate(self, token: str) -> Principal:
        self.tokens.append(token)
        return Principal(kind=PrincipalKind.USER, id="user-1")


def test_dev_principal_from_headers() -> None:
    principal = dev_principal({"x-dev-user": " alice ", "x-dev-roles": "Admin, Other", "x-dev-email": "a@b.test"})

    assert principal is not None
    assert principal.id == "dev-alice"
    assert principal.email == "a@b.test"
    assert principal.display_name == "Alice"
    assert principal.roles == frozenset({ADMIN_ROLE, "Other"})
    assert dev_principal({}) is None
    assert dev_principal({"x-dev-user": "  "}) is None


def test_dev_principal_defaults() -> None:
    principal = dev_principal({"x-dev-user": "bob"})

    assert principal is not None
    assert principal.email == "bob@example.test"
    assert principal.roles == frozenset()


@pytest.mark.parametrize(
    ("header", "expected"),
    [(None, None), ("", None), ("Bearer abc.def.ghi", "abc.def.ghi"), ("bearer  abc ", "abc")],
)
def test_bearer_token_extraction(header: str | None, expected: str | None) -> None:
    assert bearer_token(header) == expected


@pytest.mark.parametrize("header", ["Basic dXNlcjpwYXNz", "Bearer", "Bearer   ", "abc.def.ghi"])
def test_non_bearer_credentials_are_rejected_not_downgraded_to_guest(header: str) -> None:
    with pytest.raises(AuthenticationError, match="Bearer"):
        bearer_token(header)


async def test_no_credentials_means_guest() -> None:
    principal = await resolve_principal(headers={}, auth_mode="entra", validator=StubValidator(), guest_id="guest:abc")

    assert principal == guest_principal("guest:abc")
    assert principal.is_guest
    assert principal.quota_subject.kind is UsageKind.GUEST


async def test_bearer_token_is_validated() -> None:
    validator = StubValidator()

    principal = await resolve_principal(
        headers={"authorization": "Bearer token-123"}, auth_mode="entra", validator=validator, guest_id="guest:abc"
    )

    assert principal.id == "user-1"
    assert principal.quota_subject.kind is UsageKind.USER
    assert validator.tokens == ["token-123"]


async def test_token_without_configured_validator_is_an_error() -> None:
    with pytest.raises(AuthenticationError) as excinfo:
        await resolve_principal(
            headers={"authorization": "Bearer token-123"}, auth_mode="entra", validator=None, guest_id="guest:abc"
        )

    assert excinfo.value.code == "auth_not_configured"


async def test_dev_mode_uses_headers_and_ignores_bearer_tokens() -> None:
    validator = StubValidator()

    user = await resolve_principal(
        headers={"x-dev-user": "alice", "authorization": "Bearer ignored"},
        auth_mode="dev",
        validator=validator,
        guest_id="guest:abc",
    )
    guest = await resolve_principal(headers={}, auth_mode="dev", validator=validator, guest_id="guest:abc")

    assert user.id == "dev-alice"
    assert guest.is_guest
    assert validator.tokens == []


async def test_dev_headers_are_ignored_outside_dev_mode() -> None:
    principal = await resolve_principal(
        headers={"x-dev-user": "alice"}, auth_mode="entra", validator=StubValidator(), guest_id="guest:abc"
    )

    assert principal.is_guest


async def test_http_jwks_fetcher_downloads_the_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, json={"keys": [{"kid": "k1"}]})

    real_client = httpx.AsyncClient

    def client_with_mock_transport(**kwargs: object) -> httpx.AsyncClient:
        return real_client(transport=httpx.MockTransport(handler), **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "AsyncClient", client_with_mock_transport)

    document = await http_jwks_fetcher("https://tenant.ciamlogin.com/tid/discovery/v2.0/keys")()

    assert document == {"keys": [{"kid": "k1"}]}
    assert requested == ["https://tenant.ciamlogin.com/tid/discovery/v2.0/keys"]
