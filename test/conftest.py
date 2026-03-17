import os
import sys
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.api import app  # noqa: E402


@pytest.fixture(autouse=True)
def _mock_cache():
    """Mock the global semantic cache so tests never hit a real DB."""
    with patch("src.api.semantic_cache") as mock:
        mock.get = AsyncMock(return_value=None)
        mock.set = AsyncMock(return_value=None)
        mock.init = AsyncMock(return_value=None)
        mock.close = AsyncMock(return_value=None)
        yield mock


@pytest.fixture
def client():
    return TestClient(app)


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
