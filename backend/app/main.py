from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.container import AppContainer, build_container
from app.api.middleware import RateLimitMiddleware
from app.api.routers import analyze, health, usage
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.settings import Settings, get_settings

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
    app.include_router(health.router)
    app.include_router(analyze.router)
    app.include_router(usage.router)
    return app


app = create_app()
