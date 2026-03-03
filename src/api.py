from fastapi import APIRouter, HTTPException, FastAPI
from src.models import ChatCompletionRequest, OpenAI, GoogleGemini, Anthropic
from src.constants import PROVIDER_REGISTRY

router = APIRouter()

@router.post("/chat")
async def chat(request: ChatCompletionRequest):
    provider = PROVIDER_REGISTRY.get(request.model)
    if not provider:
        raise HTTPException(400, f"Unsupported model: {request.model}")
        # fallback to default provider
    
    # semantic cache lookup
    cached = provider.cache_lookup(request)
    if cached:
        return cached
    
    # if not cached, call the provider
    # transform messages to provider format
    provider_request = provider.to_provider_format(request)
    # call the provider
    try:
        provider_response = await provider.call(provider_request)
    except Exception:
        # try OpenAI, if 500, fallback to Anthropic, if 500, fallback to Google Gemini
        response = OpenAI().call(provider_request)
        if response.status_code >= 500:
            response = Anthropic().call(provider_request)
            if response.status_code >= 500:
                response = GoogleGemini().call(provider_request)
                if response.status_code >= 500:
                    raise HTTPException(500, "All providers failed")
                
    # normalize response
    normalized = provider.normalize(provider_response)

    # store in semantic cache (TODO)
    await provider.cache_store(request, normalized)

    return normalized

app = FastAPI()
app.include_router(router)