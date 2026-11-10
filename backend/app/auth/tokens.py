"""Validation of Microsoft Entra External ID access tokens (RS256 JWTs).

Checks, in order: token shape and algorithm, signing key (from a cached JWKS),
signature, expiry / not-before, issuer, audience, and finally scope or app role.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Protocol

import httpx
import jwt
from jwt import PyJWK

from app.auth.principal import Principal, PrincipalKind
from app.core.clock import Monotonic, monotonic

logger = logging.getLogger(__name__)

ALLOWED_ALGORITHMS = ("RS256",)
JwksFetcher = Callable[[], Awaitable[Mapping[str, Any]]]


class InvalidTokenError(Exception):
    """The bearer token is missing something, malformed, expired or not meant for this API."""


class InsufficientScopeError(Exception):
    """The token is valid but does not grant access to this API surface."""


class JwksUnavailableError(Exception):
    """Signing keys could not be fetched and none are cached."""


class TokenValidator(Protocol):
    async def validate(self, token: str) -> Principal: ...


def http_jwks_fetcher(jwks_uri: str, *, timeout_seconds: float = 5.0) -> JwksFetcher:
    async def fetch() -> Mapping[str, Any]:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.get(jwks_uri)
            response.raise_for_status()
            document: Mapping[str, Any] = response.json()
            return document

    return fetch


class JwksCache:
    """Caches signing keys by ``kid``.

    Keys are refreshed when they expire or when a token references an unknown ``kid``
    (key rotation), but never more often than ``min_refresh_seconds`` so that tokens
    with made-up key IDs cannot be used to hammer the identity provider.
    """

    def __init__(
        self,
        fetch: JwksFetcher,
        *,
        ttl_seconds: float = 24 * 60 * 60,
        min_refresh_seconds: float = 5 * 60,
        clock: Monotonic = monotonic,
    ) -> None:
        self._fetch = fetch
        self._ttl = ttl_seconds
        self._min_refresh = min_refresh_seconds
        self._clock = clock
        self._keys: dict[str, PyJWK] = {}
        self._fetched_at: float | None = None
        self._attempted_at: float | None = None
        self._lock = asyncio.Lock()

    async def get_key(self, kid: str) -> PyJWK | None:
        if self._needs_refresh(kid):
            async with self._lock:
                if self._needs_refresh(kid):
                    await self._refresh()
        return self._keys.get(kid)

    def _needs_refresh(self, kid: str) -> bool:
        now = self._clock()
        if self._fetched_at is None:
            # Nothing cached: retry, but back off briefly after a failed attempt.
            return self._attempted_at is None or now - self._attempted_at >= 1.0
        expired = now - self._fetched_at >= self._ttl
        unknown = kid not in self._keys
        recently_tried = self._attempted_at is not None and now - self._attempted_at < self._min_refresh
        return (expired or unknown) and not recently_tried

    async def _refresh(self) -> None:
        self._attempted_at = self._clock()
        try:
            document = await self._fetch()
            keys = _parse_jwks(document)
        except Exception as exc:
            if self._keys:
                logger.warning("JWKS refresh failed; continuing with cached signing keys.", exc_info=True)
                return
            raise JwksUnavailableError("Signing keys could not be loaded") from exc
        self._keys = keys
        self._fetched_at = self._clock()


def _parse_jwks(document: Mapping[str, Any]) -> dict[str, PyJWK]:
    keys: dict[str, PyJWK] = {}
    for entry in document.get("keys", []):
        kid = entry.get("kid")
        if not kid or entry.get("kty") != "RSA" or entry.get("use", "sig") != "sig":
            continue
        try:
            keys[kid] = PyJWK.from_dict(entry, algorithm="RS256")
        except jwt.PyJWTError:
            logger.warning("Skipping an unusable signing key in the JWKS document.")
    if not keys:
        raise ValueError("JWKS document contains no usable RSA signing keys")
    return keys


class EntraTokenValidator:
    def __init__(
        self,
        *,
        issuer: str,
        audiences: Sequence[str],
        jwks: JwksCache,
        required_scope: str,
        leeway_seconds: int = 60,
    ) -> None:
        self._issuer = issuer
        self._audiences = list(audiences)
        self._jwks = jwks
        self._required_scope = required_scope
        self._leeway = leeway_seconds

    async def validate(self, token: str) -> Principal:
        claims = await self._verified_claims(token)
        return self._principal_from_claims(claims)

    async def _verified_claims(self, token: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise InvalidTokenError("The token is malformed.") from exc

        # Never let the token choose the algorithm (blocks "none" and HMAC key confusion).
        if header.get("alg") not in ALLOWED_ALGORITHMS:
            raise InvalidTokenError("The token uses an unsupported signing algorithm.")
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise InvalidTokenError("The token does not identify its signing key.")

        key = await self._jwks.get_key(kid)
        if key is None:
            raise InvalidTokenError("The token was signed with an unknown key.")

        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key,
                algorithms=list(ALLOWED_ALGORITHMS),
                audience=self._audiences,
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": ["exp", "iat", "iss", "aud"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise InvalidTokenError("The token has expired.") from exc
        except jwt.InvalidAudienceError as exc:
            raise InvalidTokenError("The token was not issued for this API.") from exc
        except jwt.InvalidIssuerError as exc:
            raise InvalidTokenError("The token was issued by an untrusted authority.") from exc
        except jwt.PyJWTError as exc:
            raise InvalidTokenError("The token is not valid.") from exc
        return claims

    def _principal_from_claims(self, claims: Mapping[str, Any]) -> Principal:
        roles = frozenset(_string_list(claims.get("roles")))
        scopes = frozenset(str(claims.get("scp", "")).split())

        if scopes:
            # Delegated (user) token.
            if self._required_scope not in scopes:
                raise InsufficientScopeError(f"The token is missing the '{self._required_scope}' scope.")
            subject = claims.get("oid") or claims.get("sub")
            if not isinstance(subject, str) or not subject:
                raise InvalidTokenError("The token does not identify a user.")
            return Principal(
                kind=PrincipalKind.USER,
                id=subject,
                email=_first_string(claims, "email", "preferred_username"),
                display_name=_first_string(claims, "name"),
                roles=roles,
            )

        # Application (client-credentials) token: no scopes, authorisation comes from app roles.
        if not roles:
            raise InsufficientScopeError("The token grants neither a scope nor an application role.")
        client_id = claims.get("azp") or claims.get("appid") or claims.get("sub")
        if not isinstance(client_id, str) or not client_id:
            raise InvalidTokenError("The token does not identify a client application.")
        return Principal(kind=PrincipalKind.SERVICE, id=client_id, roles=roles)


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _first_string(claims: Mapping[str, Any], *names: str) -> str | None:
    for name in names:
        value = claims.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
