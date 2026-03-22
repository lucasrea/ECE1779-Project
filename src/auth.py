import logging
import os
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class Principal:
    sub: str
    scopes: set[str]
    claims: dict


@dataclass
class AuthSettings:
    enabled: bool
    issuer: str | None
    audience: str | None
    required_scope: str | None
    clock_skew_seconds: int
    shared_secret: str | None

    @classmethod
    def from_env(cls) -> "AuthSettings":
        return cls(
            enabled=_env_bool("AUTH_ENABLED", False),
            issuer=os.getenv("AUTH_ISSUER", "").strip() or None,
            audience=os.getenv("AUTH_AUDIENCE", "").strip() or None,
            required_scope=os.getenv("AUTH_REQUIRED_SCOPE", "").strip() or None,
            clock_skew_seconds=int(os.getenv("AUTH_CLOCK_SKEW_SECONDS", "30")),
            shared_secret=os.getenv("AUTH_SHARED_SECRET", "").strip() or None,
        )


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _extract_scopes(payload: dict) -> set[str]:
    scopes: set[str] = set()

    scope = payload.get("scope")
    if isinstance(scope, str):
        scopes.update(part for part in scope.split(" ") if part)

    scp = payload.get("scp")
    if isinstance(scp, list):
        scopes.update(str(part) for part in scp if part)
    elif isinstance(scp, str):
        scopes.update(part for part in scp.split(" ") if part)

    return scopes


def _validate_auth_config(settings: AuthSettings) -> None:
    if not settings.shared_secret:
        raise HTTPException(401, "Auth is misconfigured")


def validate_access_token(token: str, settings: AuthSettings | None = None) -> Principal:
    resolved_settings = settings or AuthSettings.from_env()
    _validate_auth_config(resolved_settings)

    options = {
        "require": ["exp", "sub"],
        "verify_iss": bool(resolved_settings.issuer),
        "verify_aud": bool(resolved_settings.audience),
    }
    try:
        payload = jwt.decode(
            token,
            resolved_settings.shared_secret,
            algorithms=["HS256"],
            issuer=resolved_settings.issuer,
            audience=resolved_settings.audience,
            leeway=resolved_settings.clock_skew_seconds,
            options=options,
        )
        principal = Principal(
            sub=str(payload.get("sub", "")),
            scopes=_extract_scopes(payload),
            claims=payload,
        )
        if not principal.sub:
            raise jwt.InvalidTokenError("Token missing subject")
        return principal
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(401, "Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(401, "Invalid token") from exc


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> Principal:
    settings = AuthSettings.from_env()
    if not settings.enabled:
        return Principal(sub="anonymous", scopes=set(), claims={})

    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(401, "Missing or invalid Authorization header")

    principal = validate_access_token(credentials.credentials, settings)
    if settings.required_scope and settings.required_scope not in principal.scopes:
        logger.info("Auth denied due to missing required scope")
        raise HTTPException(403, "Insufficient scope")

    return principal
