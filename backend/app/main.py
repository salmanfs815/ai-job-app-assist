import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.container import AppContainer, build_container
from app.api.middleware import RateLimitMiddleware
from app.api.routers import analyze, health, me, resumes, usage
from app.core.errors import install_error_handlers, problem_response, retry_extensions
from app.core.logging import configure_logging
from app.core.settings import Settings, get_settings
from app.repositories.base import RepositoryError

logger = logging.getLogger(__name__)

# Response headers the browser may read cross-origin (beyond the CORS safelist).
EXPOSED_HEADERS = ["X-Resume-OCR-Status", "Retry-After", "X-RateLimit-Remaining"]


def create_app(settings: Settings | None = None, container: AppContainer | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="AI Job Application Assistant API", version="0.2.0")
    app.state.container = container or build_container(settings)
    container = app.state.container

    # Middleware added last runs first. CORS must be outermost so that 429 responses
    # produced by the rate limiter still carry CORS headers and stay readable in the browser.
    if settings.rate_limit_enabled:
        app.add_middleware(
            RateLimitMiddleware,
            limiter=container.limiter,
            trusted_proxy_hops=settings.trusted_proxy_hops,
            expensive_cost=settings.rate_limit_expensive_cost,
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=EXPOSED_HEADERS,
    )

    install_error_handlers(app)

    @app.exception_handler(RepositoryError)
    async def _storage_unavailable(request: Request, exc: RepositoryError) -> JSONResponse:
        logger.error("Storage failure on %s %s", request.method, request.url.path, exc_info=exc)
        return problem_response(
            503,
            "Your data could not be reached right now. Please try again in a moment.",
            code="storage_unavailable",
            headers={"Retry-After": "5"},
            extensions=retry_extensions(5),
        )

    app.include_router(health.router)
    app.include_router(analyze.router)
    app.include_router(usage.router)
    app.include_router(me.router)
    app.include_router(resumes.router)
    return app


app = create_app()
