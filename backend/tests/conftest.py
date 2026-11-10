"""Shared fixtures. Tests never read the developer's ``.env`` file."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.container import AppContainer, build_container
from app.core.settings import Settings
from app.main import create_app


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": "local",
        "openai_api_key": "",
        "persistence_enabled": False,
        "frontend_origin": "http://localhost:3000",
        "trusted_proxy_hops": 1,
        "ip_hash_salt": "test-salt",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class FakeClock:
    """A settable UTC clock."""

    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or datetime(2026, 11, 9, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


ClientFactory = Callable[..., tuple[TestClient, AppContainer]]


@pytest.fixture
def make_client() -> Iterator[ClientFactory]:
    clients: list[TestClient] = []

    def factory(**overrides: Any) -> tuple[TestClient, AppContainer]:
        settings = make_settings(**overrides)
        container = build_container(settings)
        client = TestClient(create_app(settings, container))
        clients.append(client)
        return client, container

    yield factory
    for client in clients:
        client.close()


@pytest.fixture
def client(make_client: ClientFactory) -> TestClient:
    return make_client()[0]
