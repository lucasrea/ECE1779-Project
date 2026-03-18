from datetime import datetime, timezone
import time
import logging

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Header, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator

from src.models import ChatRequest
from src.registry import PROVIDER_REGISTRY
import src.models  # noqa: F401  — triggers @register_provider decorators

app = FastAPI(title="Golden Gate Gateway")

Instrumentator().instrument(app).expose(app)

FALLBACK_ORDER = ["openai", "anthropic", "gemini"]
DEFAULT_MODELS = {
    "openai": "gpt-4.1",
    "anthropic": "claude-haiku-4-5",
    "gemini": "gemini-2.5-flash",
}


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

    # Semantic cache lookup
    cached = provider.cache_lookup(request.messages)
    if cached:
        return cached

    # Transform to provider-native format and call
    payload = provider.to_provider_format(request, model=x_model)
    try:
        raw_response = await provider.call(payload)
        response = provider.normalize(raw_response)
    except Exception:
        logging.exception("Primary provider %s failed, entering fallback chain", x_provider)
        response = await _fallback_chain(request, skip=x_provider.lower())

    # Store in semantic cache
    provider.cache_store(request.messages, response)

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
