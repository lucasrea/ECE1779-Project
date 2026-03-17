from datetime import datetime, timezone
import time

from fastapi import HTTPException, FastAPI
from src.models import Chat, OpenAIProvider, GeminiProvider, AnthropicProvider
from src.constants import PROVIDER_REGISTRY

app = FastAPI()

@app.post("/chat")
# @limiter.limit("10/minute; 1000/day")
async def chat(request: Chat):
    provider = PROVIDER_REGISTRY.get(request.input.provider)
    if not provider:
        raise HTTPException(400, f"Unsupported model: {request.input.provider}")
    
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    session = {
        "id": request.session_id,
        "user_id": request.user_id,
        "created_at": timestamp,
        "chat_history": [],
    }

    # semantic cache lookup
    cached = provider.cache_lookup(session["chat_history"], request.input.message)
    if cached:
        response = cached
    else:
        session["chat_history"].append({
            "role": "user", 
            "content": request.input.message, 
            "timestamp": timestamp, 
            "provider": request.input.provider
        })
    
    # if not cached, call the provider
    # transform messages to provider format
    request_formatted = provider.to_provider_format(request)
    # call the provider
    try:
        response = await provider.call(request_formatted)
        session["chat_history"].append({
            "role": "assistant", 
            "content": response, 
            "timestamp": timestamp ,
            "provider": request.input.provider
        })
        session["last_active"] = int(time.time())
        session["last_updated"] = timestamp
    except Exception:
        # try OpenAI, if 500, fallback to Anthropic, if 500, fallback to Google Gemini
        response = await OpenAIProvider().call(request_formatted)
        if response.status_code >= 500:
            response = await AnthropicProvider().call(request_formatted)
            if response.status_code >= 500:
                response = await GeminiProvider().call(request_formatted)
                if response.status_code >= 500:
                    raise HTTPException(500, "All providers failed")
        

    # store in semantic cache (TODO)
    await provider.cache_store(session["id"], session, request.user_id)

    return {
        "session_id": session["id"],
        "response": response,
    }