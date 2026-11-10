"""Turns request credentials into a :class:`Principal`.

Three outcomes: a signed-in user (or service), a guest, or an authentication error.
There is deliberately no code path where a *bad* credential is downgraded to guest:
a request that presents a token must present a valid one.
"""

from collections.abc import Mapping
from typing import Literal

from app.auth.principal import Principal, PrincipalKind, guest_principal
from app.auth.tokens import TokenValidator

DEV_USER_HEADER = "x-dev-user"
DEV_ROLES_HEADER = "x-dev-roles"
DEV_EMAIL_HEADER = "x-dev-email"
DEV_NAME_HEADER = "x-dev-name"


class AuthenticationError(Exception):
    """Credentials were supplied but cannot be accepted (HTTP 401)."""

    def __init__(self, message: str, *, code: str = "invalid_token") -> None:
        super().__init__(message)
        self.code = code


def dev_principal(headers: Mapping[str, str]) -> Principal | None:
    """Fake user for local development: ``X-Dev-User: alice`` signs in as ``alice``.

    Only reachable when ``AUTH_MODE=dev``, which the settings refuse outside
    ``ENVIRONMENT=local``.
    """
    user_id = headers.get(DEV_USER_HEADER, "").strip()
    if not user_id:
        return None
    roles = frozenset(role.strip() for role in headers.get(DEV_ROLES_HEADER, "").split(",") if role.strip())
    return Principal(
        kind=PrincipalKind.USER,
        id=f"dev-{user_id}",
        email=headers.get(DEV_EMAIL_HEADER, "").strip() or f"{user_id}@example.test",
        display_name=headers.get(DEV_NAME_HEADER, "").strip() or user_id.title(),
        roles=roles,
    )


def bearer_token(authorization: str | None) -> str | None:
    """Extract the token from an ``Authorization`` header, or ``None`` if there is no header."""
    if authorization is None or not authorization.strip():
        return None
    scheme, _, token = authorization.strip().partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationError("Use the Authorization header with a Bearer token.")
    return token.strip()


async def resolve_principal(
    *,
    headers: Mapping[str, str],
    auth_mode: Literal["entra", "dev"],
    validator: TokenValidator | None,
    guest_id: str,
) -> Principal:
    if auth_mode == "dev":
        return dev_principal(headers) or guest_principal(guest_id)

    token = bearer_token(headers.get("authorization"))
    if token is None:
        return guest_principal(guest_id)
    if validator is None:
        raise AuthenticationError("Sign-in is not configured on this server.", code="auth_not_configured")
    return await validator.validate(token)
