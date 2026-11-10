"""Test helpers: locally signed JWTs and a fake JWKS endpoint."""

import json
import time
from collections.abc import Mapping
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

TENANT_ID = "11111111-2222-3333-4444-555555555555"
API_CLIENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
ISSUER = f"https://{TENANT_ID}.ciamlogin.com/{TENANT_ID}/v2.0"
USER_OID = "00000000-0000-0000-0000-00000000a11c"


class SigningKey:
    def __init__(self, kid: str) -> None:
        self.kid = kid
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    @property
    def jwk(self) -> dict[str, Any]:
        jwk: dict[str, Any] = json.loads(RSAAlgorithm.to_jwk(self.private_key.public_key()))
        jwk.update(kid=self.kid, use="sig", alg="RS256")
        return jwk


class FakeJwks:
    """Stands in for the identity provider's JWKS endpoint and counts fetches."""

    def __init__(self, *keys: SigningKey) -> None:
        self.keys = list(keys)
        self.fetches = 0
        self.fail = False

    async def __call__(self) -> Mapping[str, Any]:
        self.fetches += 1
        if self.fail:
            raise ConnectionError("identity provider unreachable")
        return {"keys": [key.jwk for key in self.keys]}


def make_token(key: SigningKey, *, headers: dict[str, Any] | None = None, **overrides: Any) -> str:
    """A token shaped like an Entra External ID v2.0 access token for a signed-in user."""
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": ISSUER,
        "aud": API_CLIENT_ID,
        "iat": now - 10,
        "nbf": now - 10,
        "exp": now + 3600,
        "oid": USER_OID,
        "sub": "pairwise-subject",
        "tid": TENANT_ID,
        "scp": "access_as_user",
        "name": "Alice Example",
        "email": "alice@example.test",
        "ver": "2.0",
    }
    for name, value in overrides.items():
        if value is None:
            claims.pop(name, None)
        else:
            claims[name] = value
    return jwt.encode(claims, key.private_key, algorithm="RS256", headers={"kid": key.kid, **(headers or {})})
