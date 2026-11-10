"""FastAPI dependencies shared by the routers: wiring, identity and access checks."""

import logging
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Request

from app.api.container import AppContainer
from app.auth.principal import Principal
from app.auth.resolver import AuthenticationError, resolve_principal
from app.auth.tokens import InsufficientScopeError, InvalidTokenError, JwksUnavailableError
from app.core.errors import ProblemError, retry_extensions
from app.core.network import client_ip_from_scope
from app.domain.usage import guest_owner_id
from app.domain.users import User
from app.repositories.base import RepositoryError

logger = logging.getLogger(__name__)

BEARER_CHALLENGE = {"WWW-Authenticate": "Bearer"}


def get_container(request: Request) -> AppContainer:
    container: AppContainer = request.app.state.container
    return container


Container = Annotated[AppContainer, Depends(get_container)]


def get_client_ip(request: Request, container: Container) -> str:
    return client_ip_from_scope(request.scope, container.settings.trusted_proxy_hops)


ClientIp = Annotated[str, Depends(get_client_ip)]


async def get_principal(request: Request, container: Container, client_ip: ClientIp) -> Principal:
    """Identify the caller: a signed-in user, a service, or a guest. Bad tokens are 401s."""
    settings = container.settings
    try:
        return await resolve_principal(
            headers=request.headers,
            auth_mode=settings.auth_mode,
            validator=container.token_validator,
            guest_id=guest_owner_id(client_ip, settings.ip_hash_salt),
        )
    except (AuthenticationError, InvalidTokenError) as exc:
        code = exc.code if isinstance(exc, AuthenticationError) else "invalid_token"
        raise ProblemError(
            401,
            str(exc),
            code=code,
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        ) from exc
    except InsufficientScopeError as exc:
        raise ProblemError(
            403,
            str(exc),
            code="insufficient_scope",
            headers={"WWW-Authenticate": 'Bearer error="insufficient_scope"'},
        ) from exc
    except JwksUnavailableError as exc:
        logger.error("Token validation is unavailable: signing keys could not be loaded.", exc_info=True)
        raise ProblemError(
            503,
            "Sign-in is temporarily unavailable. Please try again in a moment.",
            code="auth_unavailable",
            headers={"Retry-After": "30"},
            extensions=retry_extensions(30),
        ) from exc


AnyPrincipal = Annotated[Principal, Depends(get_principal)]


def get_tool_caller(principal: AnyPrincipal, container: Container) -> Principal:
    """Callers of the original analyze / cover-letter tool: users, or guests while guest mode is on."""
    if principal.is_user:
        return principal
    if principal.is_guest and container.settings.guest_mode_enabled:
        return principal
    if principal.is_guest:
        raise ProblemError(
            401,
            "Please sign in to use this feature.",
            code="authentication_required",
            headers=BEARER_CHALLENGE,
        )
    raise ProblemError(403, "This endpoint is for people, not services.", code="forbidden")


ToolCaller = Annotated[Principal, Depends(get_tool_caller)]


def get_user_principal(principal: AnyPrincipal) -> Principal:
    if principal.is_guest:
        raise ProblemError(
            401,
            "Please sign in to use this feature.",
            code="authentication_required",
            headers=BEARER_CHALLENGE,
        )
    if not principal.is_user:
        raise ProblemError(403, "This endpoint is for people, not services.", code="forbidden")
    return principal


UserPrincipal = Annotated[Principal, Depends(get_user_principal)]


async def get_current_user(principal: UserPrincipal, container: Container) -> User:
    """The signed-in user's account, created on first sign-in."""
    try:
        return await container.users.ensure_user(principal)
    except RepositoryError as exc:
        logger.error("Could not load or create the user account.", exc_info=True)
        raise ProblemError(
            503,
            "Your account could not be loaded right now. Please try again in a moment.",
            code="storage_unavailable",
            headers={"Retry-After": "5"},
            extensions=retry_extensions(5),
        ) from exc


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(role: str) -> Callable[[Principal], Coroutine[Any, Any, Principal]]:
    """Dependency factory: the signed-in user must hold ``role`` (an Entra app role)."""

    async def dependency(principal: UserPrincipal) -> Principal:
        if not principal.has_role(role):
            raise ProblemError(403, "You do not have access to this area.", code="forbidden")
        return principal

    return dependency
