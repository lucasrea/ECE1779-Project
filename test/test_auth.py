import time
from unittest.mock import MagicMock

import jwt
import pytest
from fastapi import HTTPException

from src.auth import AuthSettings, validate_access_token

BODY = {"messages": [{"role": "user", "content": "hi"}]}
OPENAI_HEADERS = {"X-Provider": "openai", "X-Model": "gpt-4.1"}


def _issue_token(
    *,
    secret: str,
    issuer: str,
    audience: str,
    sub: str = "user-1",
    scope: str = "gateway:chat:invoke",
    exp_offset_seconds: int = 300,
) -> str:
    now = int(time.time())
    payload = {
        "sub": sub,
        "iss": issuer,
        "aud": audience,
        "scope": scope,
        "exp": now + exp_offset_seconds,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _openai_response(content="hello"):
    resp = MagicMock()
    choice = MagicMock()
    choice.message.content = content
    resp.choices = [choice]
    resp.usage.prompt_tokens = 10
    resp.usage.completion_tokens = 5
    return resp


@pytest.fixture
def auth_env(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_SHARED_SECRET", "test-secret-value-with-32-byte-length")
    monkeypatch.setenv("AUTH_ISSUER", "https://issuer.example.com")
    monkeypatch.setenv("AUTH_AUDIENCE", "golden-gate-gateway")
    monkeypatch.setenv("AUTH_REQUIRED_SCOPE", "gateway:chat:invoke")
    return {
        "secret": "test-secret-value-with-32-byte-length",
        "issuer": "https://issuer.example.com",
        "audience": "golden-gate-gateway",
    }


def test_validate_access_token_accepts_valid_token(auth_env):
    token = _issue_token(
        secret=auth_env["secret"],
        issuer=auth_env["issuer"],
        audience=auth_env["audience"],
    )
    principal = validate_access_token(token, AuthSettings.from_env())
    assert principal.sub == "user-1"
    assert "gateway:chat:invoke" in principal.scopes


def test_validate_access_token_rejects_invalid_signature(auth_env):
    token = _issue_token(
        secret="wrong-secret-value-with-32-byte-length",
        issuer=auth_env["issuer"],
        audience=auth_env["audience"],
    )
    with pytest.raises(HTTPException) as exc:
        validate_access_token(token, AuthSettings.from_env())
    assert exc.value.status_code == 401


def test_chat_completions_returns_401_without_token(client, auth_env):
    resp = client.post("/v1/chat/completions", json=BODY, headers=OPENAI_HEADERS)
    assert resp.status_code == 401


def test_chat_completions_returns_403_without_scope(client, auth_env):
    token = _issue_token(
        secret=auth_env["secret"],
        issuer=auth_env["issuer"],
        audience=auth_env["audience"],
        scope="gateway:read",
    )
    headers = dict(OPENAI_HEADERS)
    headers["Authorization"] = f"Bearer {token}"
    resp = client.post("/v1/chat/completions", json=BODY, headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_chat_completions_returns_200_with_valid_jwt(client, auth_env, mock_openai_call):
    token = _issue_token(
        secret=auth_env["secret"],
        issuer=auth_env["issuer"],
        audience=auth_env["audience"],
    )
    headers = dict(OPENAI_HEADERS)
    headers["Authorization"] = f"Bearer {token}"
    mock_openai_call.return_value = _openai_response("secured")

    resp = client.post("/v1/chat/completions", json=BODY, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["choices"][0]["message"]["content"] == "secured"


def test_health_endpoint_stays_public(client, auth_env):
    resp = client.get("/health")
    assert resp.status_code == 200
