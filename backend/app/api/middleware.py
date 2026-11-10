"""ASGI middleware. Written against the raw ASGI interface so streamed (SSE) responses
are passed through untouched."""

from collections.abc import Sequence

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.clock import Monotonic, monotonic
from app.core.errors import problem_response, retry_extensions
from app.core.network import client_ip_from_scope
from app.domain.rate_limit import TokenBucketLimiter

EXEMPT_PATHS = frozenset({"/health"})
EXPENSIVE_PREFIXES = ("/generate/", "/resume/extract", "/job-description/extract")


class RateLimitMiddleware:
    """Per-IP token bucket applied to every endpoint except health probes and CORS preflights."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        limiter: TokenBucketLimiter,
        trusted_proxy_hops: int,
        expensive_cost: int,
        expensive_prefixes: Sequence[str] = EXPENSIVE_PREFIXES,
        clock: Monotonic = monotonic,
    ) -> None:
        self._app = app
        self._limiter = limiter
        self._trusted_proxy_hops = trusted_proxy_hops
        self._expensive_cost = expensive_cost
        self._expensive_prefixes = tuple(expensive_prefixes)
        self._clock = clock

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] == "OPTIONS" or scope["path"] in EXEMPT_PATHS:
            await self._app(scope, receive, send)
            return

        path: str = scope["path"]
        cost = self._expensive_cost if path.startswith(self._expensive_prefixes) else 1
        key = client_ip_from_scope(scope, self._trusted_proxy_hops)
        decision = self._limiter.consume(key, now=self._clock(), cost=cost)

        if not decision.allowed:
            response = problem_response(
                429,
                "Too many requests from your network. Please slow down and try again shortly.",
                code="rate_limited",
                headers={"Retry-After": str(decision.retry_after_seconds)},
                extensions=retry_extensions(decision.retry_after_seconds),
            )
            await response(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-RateLimit-Remaining"] = str(decision.remaining)
            await send(message)

        await self._app(scope, receive, send_with_headers)
