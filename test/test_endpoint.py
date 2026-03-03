import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helper factories for fake provider responses
# ---------------------------------------------------------------------------

def make_fake_openai_response():
    resp = MagicMock()
    resp.id = "123"
    resp.model = "gpt-5.2"

    choice = MagicMock()
    choice.message = MagicMock()
    choice.message.content = "hello"
    resp.choices = [choice]

    resp.usage = {"prompt_tokens": 1, "completion_tokens": 1}
    return resp


def make_fake_anthropic_response():
    resp = MagicMock()
    resp.id = "anthropic123"
    resp.model = "claude-3"
    resp.content = [{"text": "hello"}]
    resp.usage = {"input_tokens": 1, "output_tokens": 1}
    return resp


def make_fake_gemini_response():
    resp = MagicMock()
    resp.id = "gem123"
    resp.model = "gemini-pro"
    resp.candidates = [{"content": [{"text": "hello"}]}]
    resp.usage = {"prompt_tokens": 1, "completion_tokens": 1}
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_provider_selection(client, mock_openai_call):
    fake = make_fake_openai_response()
    mock_openai_call.return_value = fake

    req = {
        "model": "gpt-5.2",
        "messages": [{"role": "user", "content": "hi"}],
    }

    resp = client.post("/chat", json=req)

    assert resp.status_code == 200
    mock_openai_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_cache_hit_short_circuits_provider(client):
    mock_provider = MagicMock()
    mock_provider.cache_lookup = AsyncMock(return_value={"cached": True})
    mock_provider.call = AsyncMock()

    with patch("constants.PROVIDER_REGISTRY", {"gpt-5.2": mock_provider}):
        req = {"model": "gpt-5.2", "messages": [{"role": "user", "content": "hi"}]}
        resp = client.post("/chat", json=req)

    assert resp.json() == {"cached": True}
    mock_provider.call.assert_not_called()


@pytest.mark.asyncio
async def test_fallback_to_anthropic(client, mock_openai_call, mock_anthropic_call):
    mock_openai_call.side_effect = Exception("OpenAI down")

    fake = make_fake_anthropic_response()
    mock_anthropic_call.return_value = fake

    req = {
        "model": "gpt-5.2",
        "messages": [{"role": "user", "content": "hi"}],
    }

    resp = client.post("/chat", json=req)

    assert resp.status_code == 200
    mock_anthropic_call.assert_awaited_once()


def test_all_providers_fail(client, mock_openai_call, mock_anthropic_call, mock_gemini_call):
    mock_openai_call.side_effect = Exception("fail")
    mock_anthropic_call.side_effect = Exception("fail")
    mock_gemini_call.side_effect = Exception("fail")

    req = {
        "model": "gpt-5.2",
        "messages": [{"role": "user", "content": "hi"}],
    }

    resp = client.post("/chat", json=req)

    assert resp.status_code == 500
    assert "All providers failed" in resp.text


@pytest.mark.asyncio
async def test_cache_store(client):
    with patch("src.models.OpenAI.cache_lookup", AsyncMock(return_value={"cached": True})):
        req = {
            "model": "gpt-5.2",
            "messages": [{"role": "user", "content": "hi"}],
        }
        resp = client.post("/chat", json=req)

    assert resp.json() == {"cached": True}


def test_normalization(client, mock_openai_call):
    fake = make_fake_openai_response()
    mock_openai_call.return_value = fake

    req = {
        "model": "gpt-5.2",
        "messages": [{"role": "user", "content": "hi"}],
    }

    resp = client.post("/chat", json=req)

    assert resp.json() == {
        "id": "123",
        "content": "hello",
        "model": "gpt-5.2",
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }