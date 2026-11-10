"""Composition root: builds the object graph for one application instance."""

from dataclasses import dataclass

from app.core.settings import Settings
from app.domain.pricing import ModelPrice
from app.domain.rate_limit import TokenBucketLimiter
from app.integrations.llm import LLMClient
from app.repositories.base import ResultsRepository, UsageRepository
from app.repositories.memory import InMemoryUsageRepository, NoopResultsRepository
from app.services.usage import UsageService


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    llm: LLMClient
    limiter: TokenBucketLimiter
    usage: UsageService
    results: ResultsRepository


def _price_override(settings: Settings) -> ModelPrice | None:
    if settings.llm_input_cost_per_1m_usd is None or settings.llm_output_cost_per_1m_usd is None:
        return None
    return ModelPrice(settings.llm_input_cost_per_1m_usd, settings.llm_output_cost_per_1m_usd)


def build_container(settings: Settings) -> AppContainer:
    usage_repository: UsageRepository
    results: ResultsRepository
    if settings.persistence_enabled:
        # Imported lazily so local/mock runs do not need the Cosmos SDK configured.
        from app.repositories.cosmos import CosmosContainers, CosmosResultsRepository, CosmosUsageRepository
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
    else:
        usage_repository = InMemoryUsageRepository()
        results = NoopResultsRepository()

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
    )
