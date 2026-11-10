"""FastAPI dependencies shared by the routers."""

from typing import Annotated

from fastapi import Depends, Request

from app.api.container import AppContainer
from app.core.network import client_ip_from_scope
from app.domain.usage import QuotaSubject, guest_subject


def get_container(request: Request) -> AppContainer:
    container: AppContainer = request.app.state.container
    return container


Container = Annotated[AppContainer, Depends(get_container)]


def get_client_ip(request: Request, container: Container) -> str:
    return client_ip_from_scope(request.scope, container.settings.trusted_proxy_hops)


ClientIp = Annotated[str, Depends(get_client_ip)]


def get_quota_subject(client_ip: ClientIp, container: Container) -> QuotaSubject:
    """Who LLM usage is counted against. Every caller is a guest until accounts exist."""
    return guest_subject(client_ip, container.settings.ip_hash_salt)


Subject = Annotated[QuotaSubject, Depends(get_quota_subject)]
