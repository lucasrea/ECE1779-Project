import asyncio
import json
import logging
import urllib.request
from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)

_LITELLM_PRICING_URL = (
    "https://raw.githubusercontent.com/BerriAI/liteLLM/main/model_prices_and_context_window.json"
)
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
    """Return the model label for a given provider registry key."""
    return _PROVIDER_MODEL.get(provider, "unknown")


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: words * 1.3."""
    return int(len(text.split()) * 1.3)


def record_cache_hit(provider: str, model: str, response_text: str) -> None:
    """Call this when cache search hit."""
    tokens = _estimate_tokens(response_text)
    price = _OUTPUT_PRICE_PER_TOKEN.get(model, _DEFAULT_OUTPUT_PRICE)
    cache_hits_total.labels(provider=provider, model=model).inc()
    cache_tokens_saved_total.labels(provider=provider, model=model).inc(tokens)
    cache_cost_saved_usd_total.labels(provider=provider, model=model).inc(tokens * price)


def record_cache_miss(provider: str, model: str) -> None:
    """Call this when cache search missed."""
    cache_misses_total.labels(provider=provider, model=model).inc()


def record_transform(provider: str, model: str, duration: float) -> None:
    """Call this to record duration of every format transformation."""
    llm_transform_duration_seconds.labels(provider=provider, model=model).observe(duration)


def record_provider_call(provider: str, model: str, status: str, duration: float) -> None:
    """Call this to record time-taken and result of calling a model."""
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


async def start_price_refresh_loop() -> None:
    """Call once at app startup. Refreshes prices immediately, then every 24 h."""
    while True:
        await _refresh_prices()
        await asyncio.sleep(_REFRESH_INTERVAL_SECONDS)
