import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers — fake SDK responses matching each provider's real shape
# ---------------------------------------------------------------------------

def _openai_response(content="hello"):
    resp = MagicMock()
    choice = MagicMock()
    choice.message.content = content
    resp.choices = [choice]
    resp.usage.prompt_tokens = 10
    resp.usage.completion_tokens = 5
    return resp


def _anthropic_response(content="hello"):
    resp = MagicMock()
    block = MagicMock()
    block.text = content
    resp.content = [block]
    resp.usage.input_tokens = 10
    resp.usage.output_tokens = 5
    return resp


def _gemini_response(content="hello"):
    resp = MagicMock()
    resp.text = content
    resp.usage_metadata.prompt_token_count = 10
    resp.usage_metadata.candidates_token_count = 5
    return resp


BODY = {"messages": [{"role": "user", "content": "hi"}]}
OPENAI_HEADERS = {"X-Provider": "openai", "X-Model": "gpt-4.1"}
ANTHROPIC_HEADERS = {"X-Provider": "anthropic", "X-Model": "claude-haiku-4-5"}
GEMINI_HEADERS = {"X-Provider": "gemini", "X-Model": "gemini-2.5-flash"}


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_openai_call(client, mock_openai_call):
    mock_openai_call.return_value = _openai_response()
    resp = client.post("/v1/chat/completions", json=BODY, headers=OPENAI_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["choices"][0]["message"]["content"] == "hello"
    mock_openai_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_anthropic_call(client, mock_anthropic_call):
    mock_anthropic_call.return_value = _anthropic_response()
    resp = client.post("/v1/chat/completions", json=BODY, headers=ANTHROPIC_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["choices"][0]["message"]["content"] == "hello"
    mock_anthropic_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_gemini_call(client, mock_gemini_call):
    mock_gemini_call.return_value = _gemini_response()
    resp = client.post("/v1/chat/completions", json=BODY, headers=GEMINI_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["choices"][0]["message"]["content"] == "hello"
    mock_gemini_call.assert_awaited_once()


# ---------------------------------------------------------------------------
# Cache hit short-circuits the provider
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_hit(client):
    cached = {"choices": [{"message": {"role": "assistant", "content": "cached"}}], "usage": {}}
    with patch("src.models.OpenAIProvider.cache_lookup", return_value=cached):
        resp = client.post("/v1/chat/completions", json=BODY, headers=OPENAI_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["choices"][0]["message"]["content"] == "cached"


# ---------------------------------------------------------------------------
# Fallback chain
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fallback_to_anthropic(client, mock_openai_call, mock_anthropic_call):
    mock_openai_call.side_effect = Exception("OpenAI down")
    mock_anthropic_call.return_value = _anthropic_response("fallback")

    resp = client.post("/v1/chat/completions", json=BODY, headers=OPENAI_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["choices"][0]["message"]["content"] == "fallback"
    mock_anthropic_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_all_providers_fail(client, mock_openai_call, mock_anthropic_call, mock_gemini_call):
    mock_openai_call.side_effect = Exception("fail")
    mock_anthropic_call.side_effect = Exception("fail")
    mock_gemini_call.side_effect = Exception("fail")

    resp = client.post("/v1/chat/completions", json=BODY, headers=OPENAI_HEADERS)
    assert resp.status_code == 500
    assert "All providers failed" in resp.text


# ---------------------------------------------------------------------------
# Bad / missing headers
# ---------------------------------------------------------------------------

def test_unknown_provider(client):
    resp = client.post(
        "/v1/chat/completions",
        json=BODY,
        headers={"X-Provider": "nope", "X-Model": "x"},
    )
    assert resp.status_code == 400
    assert "Unknown provider" in resp.text


def test_missing_provider_header(client):
    resp = client.post("/v1/chat/completions", json=BODY, headers={"X-Model": "gpt-4.1"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Response normalization shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_response_shape(client, mock_openai_call):
    mock_openai_call.return_value = _openai_response("world")
    resp = client.post("/v1/chat/completions", json=BODY, headers=OPENAI_HEADERS)
    data = resp.json()
    assert "choices" in data
    assert "usage" in data
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert data["usage"]["prompt_tokens"] == 10
    assert data["usage"]["completion_tokens"] == 5
