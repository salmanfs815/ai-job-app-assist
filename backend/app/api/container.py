"""Composition root: builds the object graph for one application instance."""

from dataclasses import dataclass

from app.auth.tokens import EntraTokenValidator, JwksCache, TokenValidator, http_jwks_fetcher
from app.core.settings import Settings
from app.domain.pricing import ModelPrice
from app.domain.rate_limit import TokenBucketLimiter
from app.integrations.llm import LLMClient
from app.repositories.base import ResultsRepository, ResumeRepository, UsageRepository, UserRepository
from app.repositories.memory import (
    InMemoryResumeRepository,
    InMemoryUsageRepository,
    InMemoryUserRepository,
    NoopResultsRepository,
)
from app.services.resumes import ResumeService
from app.services.usage import UsageService
from app.services.users import UserService


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    llm: LLMClient
    limiter: TokenBucketLimiter
    usage: UsageService
    results: ResultsRepository
    users: UserService
    resumes: ResumeService
    # None when Entra is not configured: sign-in is unavailable, guests still work.
    token_validator: TokenValidator | None


def _price_override(settings: Settings) -> ModelPrice | None:
    if settings.llm_input_cost_per_1m_usd is None or settings.llm_output_cost_per_1m_usd is None:
        return None
    return ModelPrice(settings.llm_input_cost_per_1m_usd, settings.llm_output_cost_per_1m_usd)


def _token_validator(settings: Settings) -> TokenValidator | None:
    if settings.auth_mode != "entra" or not settings.entra_configured:
        return None
    return EntraTokenValidator(
        issuer=settings.resolved_entra_issuer,
        audiences=settings.resolved_entra_audiences,
        jwks=JwksCache(http_jwks_fetcher(settings.resolved_entra_jwks_uri)),
        required_scope=settings.entra_required_scope,
    )


def build_container(settings: Settings) -> AppContainer:
    usage_repository: UsageRepository
    results: ResultsRepository
    user_repository: UserRepository
    resume_repository: ResumeRepository
    if settings.persistence_enabled:
        # Imported lazily so local/mock runs do not need the Cosmos SDK configured.
        from app.repositories.cosmos import CosmosContainers, CosmosResultsRepository, CosmosUsageRepository
        from app.repositories.cosmos_accounts import CosmosResumeRepository, CosmosUserRepository
        from app.repositories.fallback import FallbackUsageRepository

        containers = CosmosContainers(
            endpoint=settings.cosmos_endpoint,
            key=settings.cosmos_key,
            database_name=settings.cosmos_database_name,
        )
        usage_repository = FallbackUsageRepository(
            CosmosUsageRepository(containers, settings.cosmos_usage_container_name),
            InMemoryUsageRepository(),
        )
        results = CosmosResultsRepository(containers, settings.cosmos_container_name)
        user_repository = CosmosUserRepository(containers, settings.cosmos_users_container_name)
        resume_repository = CosmosResumeRepository(containers, settings.cosmos_resumes_container_name)
    else:
        usage_repository = InMemoryUsageRepository()
        results = NoopResultsRepository()
        user_repository = InMemoryUserRepository()
        resume_repository = InMemoryResumeRepository()

    return AppContainer(
        settings=settings,
        llm=LLMClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            max_output_tokens=settings.llm_max_output_tokens,
        ),
        limiter=TokenBucketLimiter(
            capacity=settings.rate_limit_burst,
            refill_per_second=settings.rate_limit_refill_per_second,
        ),
        usage=UsageService(
            usage_repository,
            user_daily_limit=settings.user_daily_generation_limit,
            guest_daily_limit=settings.guest_daily_generation_limit,
            daily_budget_usd=settings.global_daily_llm_budget_usd,
            price_override=_price_override(settings),
        ),
        results=results,
        users=UserService(user_repository, resume_repository, usage_repository, results),
        resumes=ResumeService(resume_repository, max_per_user=settings.max_resumes_per_user),
        token_validator=_token_validator(settings),
    )
