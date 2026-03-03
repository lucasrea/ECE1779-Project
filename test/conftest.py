import os
import sys
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
import pytest

# Ensure project root is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.api import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_openai_call():
    # Patch your provider class, NOT the OpenAI SDK
    with patch("src.models.OpenAI.call", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture
def mock_anthropic_call():
    with patch("src.models.Anthropic.call", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture
def mock_gemini_call():
    with patch("src.models.GoogleGemini.call", new_callable=AsyncMock) as mock:
        yield mock