from prometheus_client import Counter, Histogram

# ── Provider Health ───────────────────────────────────────────────────────────

llm_requests_total = Counter(
    "llm_requests_total",
    "Total LLM provider requests",
    ["provider", "model", "status"],  # status: success | failure
)

# ── Latency ───────────────────────────────────────────────────────────────────

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

# ── Cache / Cost Savings ──────────────────────────────────────────────────────

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

# ── Pricing ───────────────────────────────────────────────────────────────────
# Phase 1: hardcoded output-token price in USD per token.
#
# Phase 2 (planned): on app startup, a background asyncio task fetches the
# community-maintained LiteLLM pricing JSON and refreshes every 24 h:
#   URL: https://raw.githubusercontent.com/BerriAI/liteLLM/main/model_prices_and_context_window.json
#   Key per model: {"output_cost_per_token": <float>}
#   Wrap the fetch in try/except so failure silently falls back to these defaults.

_OUTPUT_PRICE_PER_TOKEN: dict[str, float] = {
    "gpt-4.1":          8.00 / 1_000_000,   # $8.00 / 1M output tokens
    "gemini-2.5-flash": 0.60 / 1_000_000,   # $0.60 / 1M output tokens
    "claude-haiku-4-5": 4.00 / 1_000_000,   # $4.00 / 1M output tokens
}

_DEFAULT_OUTPUT_PRICE = 5.00 / 1_000_000    # conservative fallback

# Maps PROVIDER_REGISTRY key → model name used in metric labels.
# Kept in sync with the model strings in models.py.
_PROVIDER_MODEL: dict[str, str] = {
    "OpenAI": "gpt-4.1",
    "Gemini": "gemini-2.5-flash",
    "Claude": "claude-haiku-4-5",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def model_for(provider: str) -> str:
    """Return the model label for a given provider registry key."""
    return _PROVIDER_MODEL.get(provider, "unknown")


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: words × 1.3."""
    return int(len(text.split()) * 1.3)


def record_cache_hit(provider: str, model: str, response_text: str) -> None:
    tokens = _estimate_tokens(response_text)
    price = _OUTPUT_PRICE_PER_TOKEN.get(model, _DEFAULT_OUTPUT_PRICE)
    cache_hits_total.labels(provider=provider, model=model).inc()
    cache_tokens_saved_total.labels(provider=provider, model=model).inc(tokens)
    cache_cost_saved_usd_total.labels(provider=provider, model=model).inc(tokens * price)


def record_cache_miss(provider: str, model: str) -> None:
    cache_misses_total.labels(provider=provider, model=model).inc()


def record_transform(provider: str, model: str, duration: float) -> None:
    llm_transform_duration_seconds.labels(provider=provider, model=model).observe(duration)


def record_provider_call(provider: str, model: str, status: str, duration: float) -> None:
    llm_requests_total.labels(provider=provider, model=model, status=status).inc()
    llm_request_duration_seconds.labels(provider=provider, model=model).observe(duration)
