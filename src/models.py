import logging
import os
from typing import Optional
import uuid
from fastapi import Depends, Query, Response
from fastapi.params import Cookie
from pydantic import BaseModel
import openai
from google import genai
from google.genai import types

from src.semantic_cache import SemanticCache

def get_session_id(session_id: Optional[str] = Cookie(None)) -> str:
    return session_id or str(uuid.uuid4())

class ChatInput(BaseModel):
    message: str
    provider: str

class Chat(BaseModel):
    input: ChatInput
    session_id: str = Depends(get_session_id)
    user_id: str = Query(...)
    response: Response = None

class BaseProvider(SemanticCache):
    async def to_provider_format(self, request: Chat):
        pass

    async def call(self, payload):
        pass

    async def normalize(self, response):
        pass

    async def cache_lookup(self, request: Chat):
        # generate a key for semantic cache lookup
        key = f"{request.model}_{hash(str(request.messages))}"
        return self.get(key)
    async def cache_store(self, request: Chat, response):
        # generate a key for semantic cache storage
        key = f"{request.model}_{hash(str(request.messages))}"
        self.set(key, response)


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

class OpenAI(BaseProvider):
    async def to_provider_format(self, session_history):
        # transform ChatCompletionRequest to OpenAI format
        return {
            "model": "gpt-4.1",
            "messages": session_history,
            "temperature": 0.7,
            "max_tokens": 300,
        }

    async def call(self, payload):
        openai.api_key = OPENAI_API_KEY
        logging.info(f"Calling OpenAI")
        response = await openai.ChatCompletion.create(**payload)
        return response["choices"][0]["message"]["content"]
    
class GoogleGemini():
    async def to_provider_format(self, session_history):
        return {
            "model": "gemini-2.5-flash",
            "messages": session_history,
            "temperature": 0.7,
            "max_tokens": 1024,
        }

    async def call(self, payload):
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.generate_content(
                model=payload["model"],
                contents= {'text': payload["messages"]},
                config=types.GenerateContentConfig({
                    "temperature": payload["temperature"],
                    "maxOutputTokens": payload["max_tokens"],
                })
        )
        return response.text
        