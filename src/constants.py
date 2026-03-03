from src.models import OpenAI, GoogleGemini, Anthropic

PROVIDER_REGISTRY = {
    "gpt-5.2": OpenAI(),
    "gemini-1.5": GoogleGemini(),
    "claude-4.6-opus": Anthropic(),
}