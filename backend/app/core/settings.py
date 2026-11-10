"""Application settings.

Every value is read from the environment (or the repo-root ``.env`` file). Defaults are
chosen so that an image deployed with *no* extra configuration is safe: production
environment, real token validation, guest mode with strict quotas, limits enabled.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"

Environment = Literal["local", "production"]
AuthMode = Literal["entra", "dev"]


class Settings(BaseSettings):
    # --- Runtime -------------------------------------------------------------------
    environment: Environment = "production"
    log_level: str = "INFO"
    frontend_origin: str = "http://localhost:3000"

    # --- Persistence ---------------------------------------------------------------
    persistence_enabled: bool = False
    cosmos_endpoint: str = ""
    cosmos_key: str = ""
    cosmos_database_name: str = "jobassist"
    cosmos_container_name: str = "results"
    cosmos_users_container_name: str = "users"
    cosmos_resumes_container_name: str = "resumes"
    cosmos_usage_container_name: str = "usage"

    # --- LLM -----------------------------------------------------------------------
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    llm_max_output_tokens: int = Field(default=8000, ge=256)
    # Optional price override (USD per 1M tokens). When unset the built-in table in
    # ``app.domain.pricing`` is used for the configured model.
    llm_input_cost_per_1m_usd: float | None = Field(default=None, ge=0)
    llm_output_cost_per_1m_usd: float | None = Field(default=None, ge=0)

    # --- Document parsing ----------------------------------------------------------
    max_upload_bytes: int = 5 * 1024 * 1024
    enable_pdf_ocr_fallback: bool = True
    tesseract_cmd: str = ""

    # --- Per-IP rate limiting (in-memory token bucket; assumes a single replica) ----
    rate_limit_enabled: bool = True
    rate_limit_burst: int = Field(default=60, ge=1)
    rate_limit_refill_per_second: float = Field(default=1.0, gt=0)
    # Uploads (OCR) and generations draw this many tokens from the bucket.
    rate_limit_expensive_cost: int = Field(default=10, ge=1)
    # Number of reverse proxies in front of the app that append to X-Forwarded-For.
    # Azure Container Apps ingress is one hop. 0 = ignore the header entirely.
    trusted_proxy_hops: int = Field(default=1, ge=0)
    # Salt for the SHA-256 hash under which guest IPs are stored. Set a secret in prod.
    ip_hash_salt: str = "local-development-salt"

    # --- LLM quotas and spend protection --------------------------------------------
    user_daily_generation_limit: int = Field(default=20, ge=0)
    guest_daily_generation_limit: int = Field(default=3, ge=0)
    global_daily_llm_budget_usd: float = Field(default=1.0, ge=0)

    # --- Authentication --------------------------------------------------------------
    auth_mode: AuthMode = "entra"
    guest_mode_enabled: bool = True
    entra_tenant_id: str = ""
    entra_tenant_subdomain: str = ""
    entra_api_client_id: str = ""
    # Optional overrides; derived from the tenant settings when empty.
    entra_issuer: str = ""
    entra_jwks_uri: str = ""
    entra_audience: str = ""
    entra_required_scope: str = "access_as_user"

    # --- Saved resumes -----------------------------------------------------------------
    max_resumes_per_user: int = Field(default=10, ge=1)

    model_config = SettingsConfigDict(env_file=PROJECT_ROOT_ENV_FILE, extra="ignore")

    @model_validator(mode="after")
    def _refuse_dev_auth_outside_local(self) -> Self:
        if self.auth_mode == "dev" and self.environment != "local":
            raise ValueError(
                "AUTH_MODE=dev is only allowed when ENVIRONMENT=local. "
                "Refusing to start with fake authentication in a deployed environment."
            )
        return self

    @property
    def mock_llm(self) -> bool:
        return not self.openai_api_key

    @property
    def entra_configured(self) -> bool:
        return bool(self.entra_tenant_id and self.entra_tenant_subdomain and self.entra_api_client_id)

    @property
    def resolved_entra_issuer(self) -> str:
        # External ID v2.0 tokens carry the tenant ID (not the subdomain) in the issuer host.
        return self.entra_issuer or f"https://{self.entra_tenant_id}.ciamlogin.com/{self.entra_tenant_id}/v2.0"

    @property
    def resolved_entra_jwks_uri(self) -> str:
        return self.entra_jwks_uri or (
            f"https://{self.entra_tenant_subdomain}.ciamlogin.com/{self.entra_tenant_id}/discovery/v2.0/keys"
        )

    @property
    def resolved_entra_audiences(self) -> tuple[str, ...]:
        if self.entra_audience:
            return (self.entra_audience,)
        # v2.0 access tokens use the client ID as ``aud``; accept the App ID URI form too.
        return (self.entra_api_client_id, f"api://{self.entra_api_client_id}")


@lru_cache
def get_settings() -> Settings:
    return Settings()
