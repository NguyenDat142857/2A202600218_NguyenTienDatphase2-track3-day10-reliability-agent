from __future__ import annotations

import time
from dataclasses import dataclass

from reliability_lab.cache import ResponseCache, SharedRedisCache
from reliability_lab.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
)
from reliability_lab.providers import (
    FakeLLMProvider,
    ProviderError,
    ProviderResponse,
)


@dataclass(slots=True)
class GatewayResponse:
    text: str
    route: str
    provider: str | None
    cache_hit: bool
    latency_ms: float
    estimated_cost: float
    error: str | None = None


class ReliabilityGateway:
    """
    Routes requests through:
    - cache
    - circuit breakers
    - fallback providers
    """

    COST_BUDGET = 1.0

    def __init__(
        self,
        providers: list[FakeLLMProvider],
        breakers: dict[str, CircuitBreaker],
        cache: ResponseCache | SharedRedisCache | None = None,
    ):
        self.providers = providers
        self.breakers = breakers
        self.cache = cache

        self.total_estimated_cost = 0.0

    def complete(self, prompt: str) -> GatewayResponse:

        started_at = time.perf_counter()

        # -------------------------------------------------
        # Cache lookup
        # -------------------------------------------------

        if self.cache is not None:

            cached, score = self.cache.get(prompt)

            if cached is not None:

                latency_ms = (
                    time.perf_counter() - started_at
                ) * 1000

                return GatewayResponse(
                    text=cached,
                    route=f"cache_hit:{score:.2f}",
                    provider=None,
                    cache_hit=True,
                    latency_ms=latency_ms,
                    estimated_cost=0.0,
                )

        last_error: str | None = None

        # -------------------------------------------------
        # Provider routing
        # -------------------------------------------------

        for idx, provider in enumerate(self.providers):

            breaker = self.breakers[provider.name]

            # ---------------------------------------------
            # Cost-aware routing
            # ---------------------------------------------

            if (
                self.total_estimated_cost >= self.COST_BUDGET
                and idx == 0
            ):
                continue

            # ---------------------------------------------
            # Circuit breaker open -> skip fast
            # ---------------------------------------------

            if not breaker.allow_request():
                last_error = (
                    f"circuit_open:{provider.name}"
                )
                continue

            try:

                response: ProviderResponse = breaker.call(
                    provider.complete,
                    prompt,
                )

                self.total_estimated_cost += (
                    response.estimated_cost
                )

                # -----------------------------------------
                # Cache successful response
                # -----------------------------------------

                if self.cache is not None:
                    self.cache.set(
                        prompt,
                        response.text,
                        {"provider": provider.name},
                    )

                latency_ms = (
                    time.perf_counter() - started_at
                ) * 1000

                # -----------------------------------------
                # Route labels
                # -----------------------------------------

                if idx == 0:
                    route = f"primary:{provider.name}"
                else:
                    route = f"fallback:{provider.name}"

                return GatewayResponse(
                    text=response.text,
                    route=route,
                    provider=provider.name,
                    cache_hit=False,
                    latency_ms=latency_ms,
                    estimated_cost=response.estimated_cost,
                )

            except CircuitOpenError as exc:

                last_error = str(exc)

                continue

            except ProviderError as exc:

                last_error = str(exc)

                continue

            except Exception as exc:

                last_error = f"unexpected:{exc}"

                continue

        # -------------------------------------------------
        # Static fallback
        # -------------------------------------------------

        latency_ms = (
            time.perf_counter() - started_at
        ) * 1000

        return GatewayResponse(
            text=(
                "The service is temporarily degraded. "
                "Please try again soon."
            ),
            route="static_fallback",
            provider=None,
            cache_hit=False,
            latency_ms=latency_ms,
            estimated_cost=0.0,
            error=last_error,
        )