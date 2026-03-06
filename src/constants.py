from src.models import OpenAI, Gemini, Claude

PROVIDER_REGISTRY = {
    "OpenAI": OpenAI(),
    "Gemini": Gemini(),
    "Claude": Claude(),
}