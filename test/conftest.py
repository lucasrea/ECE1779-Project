import os
import sys
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.api import app  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    """Give each test its own empty cache file so tests don't leak state."""
    monkeypatch.setattr("src.semantic_cache.CACHE_FILE", str(tmp_path / "cache.json"))


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
