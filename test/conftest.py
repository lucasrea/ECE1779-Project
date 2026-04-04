import os
import sys
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.api import app  # noqa: E402


@pytest.fixture(autouse=True)
def mock_cache():
    """Provide a mock SemanticCache so tests never hit a real database."""
    mock = AsyncMock()
    mock.lookup = AsyncMock(return_value=None)
    mock.store = AsyncMock(return_value=None)
    mock.close = AsyncMock(return_value=None)
    with patch(
        "src.semantic_cache.SemanticCache.create",
        new_callable=AsyncMock,
        return_value=mock,
    ):
        yield mock


@pytest.fixture(autouse=True)
def mock_api_key_store():
    """Provide a mock ApiKeyStore so tests can control auth outcomes."""
    mock = AsyncMock()
    mock.authenticate = AsyncMock(
        return_value={"owner_name": "test-user", "scopes": ["chat:completions"], "key_prefix": "testprefix"}
    )
    mock.close = AsyncMock(return_value=None)
    with patch(
        "src.auth.ApiKeyStore.create",
        new_callable=AsyncMock,
        return_value=mock,
    ):
        yield mock


@pytest.fixture
def client(mock_cache, mock_api_key_store):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mock_openai_call():
    with patch("src.models.OpenAIProvider.call", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture
def mock_anthropic_call():
    with patch("src.models.AnthropicProvider.call", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture
def mock_gemini_call():
    with patch("src.models.GeminiProvider.call", new_callable=AsyncMock) as mock:
        yield mock
