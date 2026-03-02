from typing import Optional
import openai

from semantic_cache import SemanticCache

class ChatMessage:
    def __init__(self, role: str, content: str):
        self.role = role  # "system", "user", or "assistant"
        self.content = content

class ChatCompletionRequest:
    def __init__(
            self, 
            model: str, 
            messages: list[ChatMessage],
            temperature: float = 1.0,
            max_tokens: Optional[int] = 2048,
        ):
        self.model = model
        self.messages = messages
        self.temperature = temperature
        self.max_tokens = max_tokens

class BaseProvider(SemanticCache):
    async def to_provider_format(self, request: ChatCompletionRequest):
        pass

    async def call(self, payload):
        pass

    async def normalize(self, response):
        pass

    async def cache_lookup(self, request: ChatCompletionRequest):
        # generate a key for semantic cache lookup
        key = f"{request.model}_{hash(str(request.messages))}"
        return self.get(key)
    async def cache_store(self, request: ChatCompletionRequest, response):
        # generate a key for semantic cache storage
        key = f"{request.model}_{hash(str(request.messages))}"
        self.set(key, response)

class OpenAI(BaseProvider):
    async def to_provider_format(self, request):
        # transform ChatCompletionRequest to OpenAI format
        return {
            "model": request.model,
            "messages": [m.dict() for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

    async def call(self, payload):
        return await openai.chat.completions.create(**payload)

    async def normalize(self, response):
        # transform OpenAI response to normalized format
        return {
            "id": response.id,
            "content": response.choices[0].message.content,
            "model": response.model,
            "usage": response.usage,
        }
    
class GoogleGemini():
    async def to_provider_format(self, request):
        # transform ChatCompletionRequest to Google Gemini format
        pass

    async def call(self, payload):
        # call Google Gemini API
        pass

    async def normalize(self, response):
        # transform Google Gemini response to normalized format
        pass

class Anthropic():
    async def to_provider_format(self, request):
        # transform ChatCompletionRequest to Anthropic format
        pass

    async def call(self, payload):
        # call Anthropic API
        pass

    async def normalize(self, response):
        # transform Anthropic response to normalized format
        pass