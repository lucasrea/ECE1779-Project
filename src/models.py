import logging
import os

from typing import Literal

from pydantic import BaseModel
import anyio

from src.registry import register_provider

# ---------------------------------------------------------------------------
# Request / response schemas (OpenAI-compatible)
# ---------------------------------------------------------------------------

class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]
    temperature: float = 0.7
    max_tokens: int = 1024


# ---------------------------------------------------------------------------
# Base provider
# ---------------------------------------------------------------------------

class BaseProvider:
    def to_provider_format(self, request: ChatRequest, model: str) -> dict:
        raise NotImplementedError

    async def call(self, payload: dict) -> object:
        raise NotImplementedError

    def normalize(self, response: object) -> dict:
        raise NotImplementedError

# ---------------------------------------------------------------------------
# Fallback response wrapper
# ---------------------------------------------------------------------------

class FallBackResponse(BaseModel):
    provider: Literal["openai", "anthropic", "gemini"] # actual provider called
    model: str # actual model called
    transform_time: float # actual time taken for transformation
    response: dict

# ---------------------------------------------------------------------------
# Provider API keys
# ---------------------------------------------------------------------------

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")


# ---------------------------------------------------------------------------
# OpenAI — near pass-through
# ---------------------------------------------------------------------------

@register_provider("openai")
class OpenAIProvider(BaseProvider):
    def to_provider_format(self, request: ChatRequest, model: str) -> dict:
        return {
            "model": model,
            "messages": [m.model_dump() for m in request.messages],
            "temperature": request.temperature,
            "max_completion_tokens": request.max_tokens,
        }

    async def call(self, payload: dict):
        from openai import OpenAI as OpenAIClient
        client = OpenAIClient(api_key=OPENAI_API_KEY)
        logging.info("Calling OpenAI")
        response = await anyio.to_thread.run_sync(
            lambda: client.chat.completions.create(**payload)
        )
        return response

    def normalize(self, response) -> dict:
        return {
            "choices": [{"message": {"role": "assistant", "content": response.choices[0].message.content}}],
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            },
        }


# ---------------------------------------------------------------------------
# Anthropic — extract system messages, remap fields
# ---------------------------------------------------------------------------

@register_provider("anthropic")
class AnthropicProvider(BaseProvider):
    def to_provider_format(self, request: ChatRequest, model: str) -> dict:
        system_msgs = [m.content for m in request.messages if m.role == "system"]
        chat_msgs = [{"role": m.role, "content": m.content} for m in request.messages if m.role != "system"]

        payload: dict = {
            "model": model,
            "messages": chat_msgs,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if system_msgs:
            payload["system"] = "\n".join(system_msgs)
        return payload

    async def call(self, payload: dict):
        from anthropic import Anthropic as AnthropicClient
        client = AnthropicClient(api_key=ANTHROPIC_API_KEY)
        logging.info("Calling Anthropic")
        response = await anyio.to_thread.run_sync(
            lambda: client.messages.create(**payload)
        )
        return response

    def normalize(self, response) -> dict:
        return {
            "choices": [{"message": {"role": "assistant", "content": response.content[0].text}}],
            "usage": {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
            },
        }


# ---------------------------------------------------------------------------
# Gemini — convert messages to contents/parts, remap roles
# ---------------------------------------------------------------------------

GEMINI_ROLE_MAP = {"assistant": "model", "user": "user"}


@register_provider("gemini")
class GeminiProvider(BaseProvider):
    def to_provider_format(self, request: ChatRequest, model: str) -> dict:
        system_msgs = [m.content for m in request.messages if m.role == "system"]
        contents = []
        for m in request.messages:
            if m.role == "system":
                continue
            contents.append({
                "role": GEMINI_ROLE_MAP.get(m.role, m.role),
                "parts": [{"text": m.content}],
            })

        from google.genai import types

        config = types.GenerateContentConfig(
            temperature=request.temperature,
            max_output_tokens=request.max_tokens,
        )
        if system_msgs:
            config.system_instruction = "\n".join(system_msgs)

        return {
            "model": model,
            "contents": contents,
            "config": config,
        }

    async def call(self, payload: dict):
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        model = payload.pop("model")
        logging.info("Calling Gemini")
        response = await anyio.to_thread.run_sync(
            lambda: client.models.generate_content(model=model, **payload)
        )
        return response

    def normalize(self, response) -> dict:
        return {
            "choices": [{"message": {"role": "assistant", "content": response.text}}],
            "usage": {
                "prompt_tokens": response.usage_metadata.prompt_token_count,
                "completion_tokens": response.usage_metadata.candidates_token_count,
            },
        }
