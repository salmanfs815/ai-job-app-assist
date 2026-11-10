import pytest
from pydantic import ValidationError

from tests.conftest import make_settings


def test_defaults_are_safe_for_an_unconfigured_deployment() -> None:
    settings = make_settings(environment="production")

    assert settings.auth_mode == "entra"
    assert settings.rate_limit_enabled
    assert settings.guest_mode_enabled
    assert settings.guest_daily_generation_limit == 3
    assert settings.user_daily_generation_limit == 20
    assert settings.global_daily_llm_budget_usd == 1.0
    assert settings.mock_llm
    assert not settings.entra_configured


def test_dev_auth_is_refused_outside_local() -> None:
    with pytest.raises(ValidationError, match="AUTH_MODE=dev is only allowed when ENVIRONMENT=local"):
        make_settings(environment="production", auth_mode="dev")


def test_dev_auth_is_allowed_locally() -> None:
    assert make_settings(environment="local", auth_mode="dev").auth_mode == "dev"


def test_entra_endpoints_are_derived_from_the_tenant() -> None:
    settings = make_settings(
        entra_tenant_id="11111111-2222-3333-4444-555555555555",
        entra_tenant_subdomain="jobassist",
        entra_api_client_id="api-client-id",
    )

    assert settings.entra_configured
    assert settings.resolved_entra_issuer == (
        "https://11111111-2222-3333-4444-555555555555.ciamlogin.com/11111111-2222-3333-4444-555555555555/v2.0"
    )
    assert settings.resolved_entra_jwks_uri == (
        "https://jobassist.ciamlogin.com/11111111-2222-3333-4444-555555555555/discovery/v2.0/keys"
    )
    assert settings.resolved_entra_audiences == ("api-client-id", "api://api-client-id")


def test_entra_overrides_win() -> None:
    settings = make_settings(
        entra_tenant_id="t",
        entra_tenant_subdomain="s",
        entra_api_client_id="c",
        entra_issuer="https://issuer.example/v2.0",
        entra_jwks_uri="https://issuer.example/keys",
        entra_audience="api://custom",
    )

    assert settings.resolved_entra_issuer == "https://issuer.example/v2.0"
    assert settings.resolved_entra_jwks_uri == "https://issuer.example/keys"
    assert settings.resolved_entra_audiences == ("api://custom",)
