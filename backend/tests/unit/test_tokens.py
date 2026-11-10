import base64
import json
import time

import jwt
import pytest

from app.auth.principal import PrincipalKind
from app.auth.tokens import (
    EntraTokenValidator,
    InsufficientScopeError,
    InvalidTokenError,
    JwksCache,
    JwksUnavailableError,
)
from tests.support import API_CLIENT_ID, ISSUER, USER_OID, FakeJwks, SigningKey, make_token


@pytest.fixture(scope="module")
def key() -> SigningKey:
    return SigningKey("key-1")


@pytest.fixture(scope="module")
def other_key() -> SigningKey:
    return SigningKey("key-2")


class ManualTime:
    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        return self.value


def make_validator(jwks: FakeJwks, clock: ManualTime | None = None) -> EntraTokenValidator:
    cache = JwksCache(jwks, clock=clock) if clock else JwksCache(jwks)
    return EntraTokenValidator(
        issuer=ISSUER,
        audiences=[API_CLIENT_ID, f"api://{API_CLIENT_ID}"],
        jwks=cache,
        required_scope="access_as_user",
    )


# --- Accepted tokens ---------------------------------------------------------------------


async def test_valid_user_token_yields_a_user_principal(key: SigningKey) -> None:
    validator = make_validator(FakeJwks(key))

    principal = await validator.validate(make_token(key, roles=["Admin"]))

    assert principal.kind is PrincipalKind.USER
    assert principal.id == USER_OID
    assert principal.email == "alice@example.test"
    assert principal.display_name == "Alice Example"
    assert principal.has_role("Admin")
    assert principal.quota_subject.owner_id == USER_OID


async def test_app_id_uri_audience_and_multiple_scopes_are_accepted(key: SigningKey) -> None:
    validator = make_validator(FakeJwks(key))

    principal = await validator.validate(make_token(key, aud=f"api://{API_CLIENT_ID}", scp="openid access_as_user"))

    assert principal.is_user


async def test_subject_falls_back_to_sub_and_email_to_preferred_username(key: SigningKey) -> None:
    validator = make_validator(FakeJwks(key))

    principal = await validator.validate(
        make_token(key, oid=None, email=None, name=None, preferred_username="alice@contoso.test")
    )

    assert principal.id == "pairwise-subject"
    assert principal.email == "alice@contoso.test"
    assert principal.display_name is None


async def test_application_token_yields_a_service_principal(key: SigningKey) -> None:
    validator = make_validator(FakeJwks(key))

    principal = await validator.validate(make_token(key, scp=None, roles=["Postings.Ingest"], azp="watcher-client-id"))

    assert principal.kind is PrincipalKind.SERVICE
    assert principal.id == "watcher-client-id"
    assert principal.has_role("Postings.Ingest")
    assert not principal.is_user


# --- Rejected tokens ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"exp": int(time.time()) - 3600}, "expired"),
        ({"aud": "some-other-api"}, "not issued for this API"),
        ({"iss": "https://login.evil.example/v2.0"}, "untrusted authority"),
        ({"nbf": int(time.time()) + 3600}, "not valid"),
        ({"exp": None}, "not valid"),
        ({"iat": None}, "not valid"),
    ],
)
async def test_invalid_claims_are_rejected(key: SigningKey, overrides: dict[str, object], message: str) -> None:
    validator = make_validator(FakeJwks(key))

    with pytest.raises(InvalidTokenError, match=message):
        await validator.validate(make_token(key, **overrides))


async def test_token_signed_by_an_unknown_key_is_rejected(key: SigningKey, other_key: SigningKey) -> None:
    validator = make_validator(FakeJwks(key))

    with pytest.raises(InvalidTokenError, match="unknown key"):
        await validator.validate(make_token(other_key))


async def test_token_claiming_a_known_kid_but_signed_by_another_key_is_rejected(
    key: SigningKey, other_key: SigningKey
) -> None:
    validator = make_validator(FakeJwks(key))
    forged = make_token(other_key, headers={"kid": key.kid})

    with pytest.raises(InvalidTokenError, match="not valid"):
        await validator.validate(forged)


async def test_tampered_payload_is_rejected(key: SigningKey) -> None:
    validator = make_validator(FakeJwks(key))
    header, payload, signature = make_token(key).split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    claims["roles"] = ["Admin"]
    tampered = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()

    with pytest.raises(InvalidTokenError, match="not valid"):
        await validator.validate(f"{header}.{tampered}.{signature}")


async def test_unsigned_and_symmetric_tokens_are_rejected(key: SigningKey) -> None:
    validator = make_validator(FakeJwks(key))
    claims = {"iss": ISSUER, "aud": API_CLIENT_ID, "exp": int(time.time()) + 60, "iat": int(time.time())}
    unsigned = jwt.encode(claims, key=None, algorithm="none", headers={"kid": key.kid})  # type: ignore[arg-type]
    symmetric = jwt.encode(claims, key="x" * 48, algorithm="HS256", headers={"kid": key.kid})

    for token in (unsigned, symmetric):
        with pytest.raises(InvalidTokenError, match="unsupported signing algorithm"):
            await validator.validate(token)


@pytest.mark.parametrize("token", ["", "not-a-jwt", "a.b.c"])
async def test_malformed_tokens_are_rejected(key: SigningKey, token: str) -> None:
    validator = make_validator(FakeJwks(key))

    with pytest.raises(InvalidTokenError, match="malformed"):
        await validator.validate(token)


async def test_token_without_kid_is_rejected(key: SigningKey) -> None:
    validator = make_validator(FakeJwks(key))
    token = jwt.encode({"iss": ISSUER}, key.private_key, algorithm="RS256")

    with pytest.raises(InvalidTokenError, match="does not identify its signing key"):
        await validator.validate(token)


async def test_user_token_without_the_required_scope_is_forbidden(key: SigningKey) -> None:
    validator = make_validator(FakeJwks(key))

    with pytest.raises(InsufficientScopeError, match="access_as_user"):
        await validator.validate(make_token(key, scp="some.other.scope"))


async def test_token_with_neither_scope_nor_role_is_forbidden(key: SigningKey) -> None:
    validator = make_validator(FakeJwks(key))

    with pytest.raises(InsufficientScopeError, match="neither"):
        await validator.validate(make_token(key, scp=None))


async def test_tokens_without_a_subject_are_rejected(key: SigningKey) -> None:
    validator = make_validator(FakeJwks(key))

    with pytest.raises(InvalidTokenError, match="does not identify a user"):
        await validator.validate(make_token(key, oid=None, sub=None))
    with pytest.raises(InvalidTokenError, match="client application"):
        await validator.validate(make_token(key, scp=None, roles="Postings.Ingest", sub=None))


# --- JWKS caching ------------------------------------------------------------------------


async def test_signing_keys_are_fetched_once_and_cached(key: SigningKey) -> None:
    jwks = FakeJwks(key)
    validator = make_validator(jwks)

    for _ in range(5):
        await validator.validate(make_token(key))

    assert jwks.fetches == 1


async def test_key_rotation_is_picked_up_but_refreshes_are_throttled(key: SigningKey, other_key: SigningKey) -> None:
    jwks, clock = FakeJwks(key), ManualTime()
    validator = make_validator(jwks, clock)
    await validator.validate(make_token(key))

    # A token with an unknown kid right after a fetch does not trigger another fetch.
    with pytest.raises(InvalidTokenError):
        await validator.validate(make_token(other_key))
    assert jwks.fetches == 1

    # After the throttle window the rotated key is loaded.
    jwks.keys.append(other_key)
    clock.value += 301
    assert (await validator.validate(make_token(other_key))).is_user
    assert jwks.fetches == 2


async def test_keys_are_refreshed_after_the_ttl(key: SigningKey) -> None:
    jwks, clock = FakeJwks(key), ManualTime()
    validator = make_validator(jwks, clock)
    await validator.validate(make_token(key))

    clock.value += 24 * 60 * 60 + 1
    await validator.validate(make_token(key))

    assert jwks.fetches == 2


async def test_cached_keys_survive_an_identity_provider_outage(key: SigningKey) -> None:
    jwks, clock = FakeJwks(key), ManualTime()
    validator = make_validator(jwks, clock)
    await validator.validate(make_token(key))

    jwks.fail = True
    clock.value += 24 * 60 * 60 + 1

    assert (await validator.validate(make_token(key))).is_user


async def test_outage_with_no_cached_keys_is_reported_as_unavailable(key: SigningKey) -> None:
    jwks, clock = FakeJwks(key), ManualTime()
    jwks.fail = True
    validator = make_validator(jwks, clock)

    with pytest.raises(JwksUnavailableError):
        await validator.validate(make_token(key))

    # Recovers on a later request once the provider is back.
    jwks.fail = False
    clock.value += 2
    assert (await validator.validate(make_token(key))).is_user


async def test_jwks_without_usable_keys_is_unavailable(key: SigningKey) -> None:
    async def fetch() -> dict[str, object]:
        return {"keys": [{"kty": "EC", "kid": "ec-key"}, {"kty": "RSA", "kid": "enc", "use": "enc"}, {"kty": "RSA"}]}

    validator = EntraTokenValidator(
        issuer=ISSUER, audiences=[API_CLIENT_ID], jwks=JwksCache(fetch), required_scope="access_as_user"
    )

    with pytest.raises(JwksUnavailableError):
        await validator.validate(make_token(key))


async def test_malformed_rsa_keys_in_the_jwks_are_skipped(key: SigningKey) -> None:
    async def fetch() -> dict[str, object]:
        return {"keys": [{"kty": "RSA", "kid": "broken", "n": "!!", "e": "!!"}, key.jwk]}

    validator = EntraTokenValidator(
        issuer=ISSUER, audiences=[API_CLIENT_ID], jwks=JwksCache(fetch), required_scope="access_as_user"
    )

    assert (await validator.validate(make_token(key))).is_user
