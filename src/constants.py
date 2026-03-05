from src.models import OpenAI, GoogleGemini, Anthropic

PROVIDER_REGISTRY = {
    "OpenAI": OpenAI(),
    "GoogleGemini": GoogleGemini(),
    "Anthropic": Anthropic(),
}