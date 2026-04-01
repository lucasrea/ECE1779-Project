import json
import logging
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Header, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator

from src.models import ChatRequest
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
    provider_cls = PROVIDER_REGISTRY.get(x_provider.lower())
    if not provider_cls:
        raise HTTPException(400, f"Unknown provider: {x_provider}")

    provider = provider_cls()
    cache = getattr(app.state, "cache", None)

    if cache:
        cached = await cache.lookup(request.messages)
        if cached:
            record_cache_hit(x_provider.lower(), x_model, json.dumps(cached))
            return cached
        else:
            record_cache_miss(x_provider.lower(), x_model)

    t0 = time.perf_counter()
    payload = provider.to_provider_format(request, model=x_model)
    record_transform(x_provider.lower(), x_model, time.perf_counter() - t0)

    t1 = time.perf_counter()
    try:
        raw_response = await provider.call(payload)
        response = provider.normalize(raw_response)
        record_provider_call(x_provider.lower(), x_model, "success", time.perf_counter() - t1)
    except Exception:
        record_provider_call(x_provider.lower(), x_model, "failure", time.perf_counter() - t1)
        logging.exception(
            "Primary provider %s failed, entering fallback chain", x_provider,
        )
        response = await _fallback_chain(request, skip=x_provider.lower())

    if cache:
        await cache.store(request.messages, response, x_provider.lower(), x_model)

    return response


async def _fallback_chain(request: ChatRequest, skip: str) -> dict:
    for name in FALLBACK_ORDER:
        if name == skip:
            continue
        provider_cls = PROVIDER_REGISTRY.get(name)
        if not provider_cls:
            continue
        provider = provider_cls()
        payload = provider.to_provider_format(request, model=DEFAULT_MODELS[name])
        try:
            raw = await provider.call(payload)
            return provider.normalize(raw)
        except Exception:
            logging.exception("Fallback provider %s failed", name)
            continue
    raise HTTPException(500, "All providers failed")
