from src.models import OpenAIProvider, GeminiProvider, AnthropicProvider

PROVIDER_REGISTRY = {
    "OpenAI": OpenAIProvider(),
    "Gemini": GeminiProvider(),
    "Claude": AnthropicProvider(),
}