import os
import asyncio
import json
import logging
import urllib.request
from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)

_LITELLM_PRICING_URL = os.getenv("LITELLM_PRICING_JSON_URL", "https://raw.githubusercontent.com/BerriAI/liteLLM/main/model_prices_and_context_window.json")
_REFRESH_INTERVAL_SECONDS = 24 * 60 * 60  # 24 hours

# request-related
llm_requests_total = Counter(
    "llm_requests_total",
    "Total LLM provider requests",
    ["provider", "model", "status"],  # status: success | failure
)

llm_request_duration_seconds = Histogram(
    "llm_request_duration_seconds",
    "Time spent calling the LLM provider",
    ["provider", "model"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

llm_transform_duration_seconds = Histogram(
    "llm_transform_duration_seconds",
    "Time spent transforming the request to provider format",
    ["provider", "model"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1],
)

# cache hit/miss count
cache_hits_total = Counter(
    "cache_hits_total",
    "Semantic cache hits",
    ["provider", "model"],
)

cache_misses_total = Counter(
    "cache_misses_total",
    "Semantic cache misses",
    ["provider", "model"],
)

# cache token saved
cache_tokens_saved_total = Counter(
    "cache_tokens_saved_total",
    "Estimated output tokens saved via semantic cache",
    ["provider", "model"],
)

cache_cost_saved_usd_total = Counter(
    "cache_cost_saved_usd_total",
    "Estimated USD saved via semantic cache",
    ["provider", "model"],
)

# pricing
_OUTPUT_PRICE_PER_TOKEN: dict[str, float] = {
    "gpt-4.1":          8.00 / 1_000_000,   # $8.00 / 1M output tokens
    "gemini-2.5-flash": 0.60 / 1_000_000,   # $0.60 / 1M output tokens
    "claude-haiku-4-5": 4.00 / 1_000_000,   # $4.00 / 1M output tokens
}

_DEFAULT_OUTPUT_PRICE = 5.00 / 1_000_000    # conservative fallback

# Maps PROVIDER_REGISTRY key → model name used in metric labels.
_PROVIDER_MODEL: dict[str, str] = {
    "OpenAI": "gpt-4.1",
    "Gemini": "gemini-2.5-flash",
    "Claude": "claude-haiku-4-5",
}


def model_for(provider: str) -> str:
    """Return the canonical model label for a given provider registry key.

    Use this to resolve the ``model`` argument required by all ``record_*``
    functions before calling them.

    Args:
        provider: Provider registry key. Must be one of ``"OpenAI"``,
            ``"Gemini"``, or ``"Claude"``.

    Returns:
        The model name string (e.g. ``"gpt-4.1"``), or ``"unknown"`` if the
        key is not recognised.

    Example::

        provider = "OpenAI"
        model = model_for(provider)   # "gpt-4.1"
    """
    return _PROVIDER_MODEL.get(provider, "unknown")


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: words * 1.3."""
    return int(len(text.split()) * 1.3)


def record_cache_hit(provider: str, model: str, response_text: str) -> None:
    """Record a semantic cache hit and estimate the cost saved.

    Call this immediately after a cache lookup returns a result, **instead of**
    calling the LLM provider. Increments the cache-hit counter and estimates
    token and USD savings from the cached response text.

    Args:
        provider: Provider registry key (e.g. ``"OpenAI"``). Used as a
            Prometheus label — must match one of the keys in ``_PROVIDER_MODEL``.
        model: Model name returned by :func:`model_for` (e.g. ``"gpt-4.1"``).
        response_text: The cached response string. Used to estimate output
            token count (``words × 1.3``) and multiply by the current output
            token price to calculate USD saved.

    Metrics updated:
        - ``cache_hits_total`` — incremented by 1
        - ``cache_tokens_saved_total`` — incremented by estimated token count
        - ``cache_cost_saved_usd_total`` — incremented by ``tokens × price/token``

    Example::

        cached = provider.cache_lookup(messages)
        if cached:
            record_cache_hit("OpenAI", model_for("OpenAI"), cached["response"])
            return cached
    """
    tokens = _estimate_tokens(response_text)
    price = _OUTPUT_PRICE_PER_TOKEN.get(model, _DEFAULT_OUTPUT_PRICE)
    cache_hits_total.labels(provider=provider, model=model).inc()
    cache_tokens_saved_total.labels(provider=provider, model=model).inc(tokens)
    cache_cost_saved_usd_total.labels(provider=provider, model=model).inc(tokens * price)


def record_cache_miss(provider: str, model: str) -> None:
    """Record a semantic cache miss.

    Call this when a cache lookup returns nothing and the request will proceed
    to the LLM provider. Pair with :func:`record_provider_call` after the
    provider responds.

    Args:
        provider: Provider registry key (e.g. ``"OpenAI"``).
        model: Model name returned by :func:`model_for`.

    Metrics updated:
        - ``cache_misses_total`` — incremented by 1

    Example::

        cached = provider.cache_lookup(messages)
        if not cached:
            record_cache_miss("OpenAI", model_for("OpenAI"))
            # ... call provider ...
    """
    cache_misses_total.labels(provider=provider, model=model).inc()


def record_transform(provider: str, model: str, duration: float) -> None:
    """Record the time spent transforming a request into provider-native format.

    Call this after ``to_provider_format()`` completes, passing the wall-clock
    duration measured with ``time.perf_counter()``. Appears in Grafana as the
    **Transform overhead** panel.

    Args:
        provider: Provider registry key (e.g. ``"OpenAI"``).
        model: Model name returned by :func:`model_for`.
        duration: Elapsed time in **seconds** (float). Measure with
            ``time.perf_counter()`` for sub-millisecond precision.

    Metrics updated:
        - ``llm_transform_duration_seconds`` — observes ``duration``

    Example::

        t0 = time.perf_counter()
        payload = provider.to_provider_format(request, model=x_model)
        record_transform("OpenAI", model_for("OpenAI"), time.perf_counter() - t0)
    """
    llm_transform_duration_seconds.labels(provider=provider, model=model).observe(duration)


def record_provider_call(provider: str, model: str, status: str, duration: float) -> None:
    """Record the outcome and duration of a live LLM provider call.

    Call this once after ``provider.call()`` resolves — whether it succeeded
    or raised an exception. Drives the **Provider Health** and **Latency**
    Grafana rows.

    Args:
        provider: Provider registry key (e.g. ``"OpenAI"``).
        model: Model name returned by :func:`model_for`.
        status: ``"success"`` if the call returned a response, ``"failure"``
            if it raised an exception. Any other string is accepted but will
            not match existing Grafana queries.
        duration: Elapsed time in **seconds** (float) from just before
            ``provider.call()`` to just after it returns or raises.

    Metrics updated:
        - ``llm_requests_total`` — incremented by 1 (labelled by status)
        - ``llm_request_duration_seconds`` — observes ``duration``

    Example::

        t0 = time.perf_counter()
        try:
            response = await provider.call(payload)
            record_provider_call("OpenAI", model_for("OpenAI"), "success", time.perf_counter() - t0)
        except Exception:
            record_provider_call("OpenAI", model_for("OpenAI"), "failure", time.perf_counter() - t0)
            raise
    """
    llm_requests_total.labels(provider=provider, model=model, status=status).inc()
    llm_request_duration_seconds.labels(provider=provider, model=model).observe(duration)


async def _refresh_prices() -> None:
    """Fetch latest output token prices from LiteLLM and update _OUTPUT_PRICE_PER_TOKEN."""
    def _fetch() -> dict:
        with urllib.request.urlopen(_LITELLM_PRICING_URL, timeout=10) as resp:
            return json.loads(resp.read().decode())

    try:
        data = await asyncio.to_thread(_fetch)
        updated = []
        for model in list(_PROVIDER_MODEL.values()):
            if model == "claude-haiku-4-5":
                entry = data.get("claude-haiku-4-5-20251001")
            else:
                entry = data.get(model)

            if entry and "output_cost_per_token" in entry:
                _OUTPUT_PRICE_PER_TOKEN[model] = entry["output_cost_per_token"]
                updated.append(model)
        logger.info(f"Prices refreshed for: {updated}")
    except Exception as exc:
        logger.warning(f"Price refresh failed, keeping existing values: {exc}")


_price_refresh_task: asyncio.Task | None = None


async def _price_refresh_worker() -> None:
    """Background worker that periodically refreshes prices."""
    while True:
        await _refresh_prices()
        try:
            await asyncio.sleep(_REFRESH_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            # Allow clean shutdown when the task is cancelled.
            break


async def start_price_refresh_loop() -> None:
    """
    Call once at app startup.

    Schedules a background task that refreshes prices immediately, then every 24 h.
    Safe to `await` during startup; this function returns after scheduling the task.
    """
    global _price_refresh_task
    if _price_refresh_task is None or _price_refresh_task.done():
        _price_refresh_task = asyncio.create_task(_price_refresh_worker())


async def stop_price_refresh_loop() -> None:
    """Cancel the background price refresh loop, if running, and wait for it to finish."""
    global _price_refresh_task
    if _price_refresh_task is not None and not _price_refresh_task.done():
        _price_refresh_task.cancel()
        try:
            await _price_refresh_task
        except asyncio.CancelledError:
            pass
    _price_refresh_task = None
