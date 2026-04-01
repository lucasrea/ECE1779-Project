import logging
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Header, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator

from src.models import ChatRequest, FallbackResponse
from src.semantic_cache import SemanticCache
from src.registry import PROVIDER_REGISTRY
from src.observability.metrics import (
    record_cache_hit,
    record_cache_miss,
    record_provider_call,
    record_transform,
    start_price_refresh_loop,
    stop_price_refresh_loop,
)
import src.models  # noqa: F401  — triggers @register_provider decorators

logger = logging.getLogger(__name__)

FALLBACK_ORDER = ["openai", "anthropic", "gemini"]
DEFAULT_MODELS = {
    "openai": "gpt-4.1",
    "anthropic": "claude-haiku-4-5",
    "gemini": "gemini-2.5-flash",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        cache = await SemanticCache.create()
        app.state.cache = cache
        logger.info("Semantic cache initialized (pgvector)")
    except Exception:
        logger.warning(
            "Could not connect to database; semantic cache disabled",
            exc_info=True,
        )
        app.state.cache = None
    await start_price_refresh_loop()
    yield
    await stop_price_refresh_loop()
    cache = getattr(app.state, "cache", None)
    if cache:
        await cache.close()


app = FastAPI(title="Golden Gate Gateway", lifespan=lifespan)

Instrumentator().instrument(app).expose(app)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatRequest,
    x_provider: str = Header(...),
    x_model: str = Header(...),
):
    provider_name = x_provider.lower()
    provider_cls = PROVIDER_REGISTRY.get(provider_name)
    if not provider_cls:
        raise HTTPException(400, f"Unknown provider: {x_provider}")

    provider = provider_cls()
    cache = getattr(app.state, "cache", None)

    if cache:
        cached = await cache.lookup(request.messages)
        if cached:
            response_text = cached.get("choices", [{}])[0].get("message", {}).get("content", "")
            record_cache_hit(provider_name, x_model, response_text)
            return cached
        record_cache_miss(provider_name, x_model)

    transform_start = time.perf_counter()
    payload = provider.to_provider_format(request, model=x_model)
    transform_elapsed = time.perf_counter() - transform_start

    call_start = time.perf_counter()
    actual_provider = provider_name
    actual_model = x_model

    try:
        raw_response = await provider.call(payload)
        response = provider.normalize(raw_response)
    except Exception:
        logging.exception(
            "Primary provider %s failed, entering fallback chain", x_provider,
        )
        record_provider_call(actual_provider, actual_model, "failure", time.perf_counter() - call_start)

        fallback_response = await _fallback_chain(
            request,
            skip=provider_name,
            fallback_start_time=call_start,
        )

        actual_provider = fallback_response.provider
        actual_model = fallback_response.model
        transform_elapsed = fallback_response.transform_time
        response = fallback_response.response
    else:
        record_transform(actual_provider, actual_model, transform_elapsed)
        record_provider_call(actual_provider, actual_model, "success", time.perf_counter() - call_start)

    if cache:
        await cache.store(request.messages, response, provider_name, x_model)

    return response


async def _fallback_chain(
    request: ChatRequest,
    skip: str,
    fallback_start_time: float,
) -> FallbackResponse:
    for name in FALLBACK_ORDER:
        if name == skip:
            continue

        provider_cls = PROVIDER_REGISTRY.get(name)
        if not provider_cls:
            continue

        provider = provider_cls()

        transform_start = time.perf_counter()
        payload = provider.to_provider_format(request, model=DEFAULT_MODELS[name])
        transform_elapsed = time.perf_counter() - transform_start

        call_start = time.perf_counter()
        try:
            raw = await provider.call(payload)
            response = provider.normalize(raw)
            record_transform(name, DEFAULT_MODELS[name], transform_elapsed)
            record_provider_call(name, DEFAULT_MODELS[name], "success", time.perf_counter() - call_start)
            return FallbackResponse(
                provider=name,
                model=DEFAULT_MODELS[name],
                transform_time=transform_elapsed,
                response=response,
            )
        except Exception:
            logging.exception("Fallback provider %s failed", name)
            record_provider_call(name, DEFAULT_MODELS[name], "failure", time.perf_counter() - fallback_start_time)
            continue

    raise HTTPException(500, "All providers failed")
