import hashlib
import hmac
import os
from dataclasses import dataclass

import asyncpg

from src.db import build_database_url

TOKEN_PREFIX = "gg_live_"


@dataclass
class ApiKeyPrincipal:
    owner_name: str
    scopes: list[str]
    key_prefix: str


def hash_api_key(api_key: str) -> str:
    pepper = os.getenv("API_KEY_PEPPER", "")
    material = f"{pepper}{api_key}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    if not token:
        return None
    return token


def extract_key_prefix(api_key: str) -> str | None:
    if not api_key.startswith(TOKEN_PREFIX):
        return None
    suffix = api_key[len(TOKEN_PREFIX):]
    parts = suffix.split("_", 1)
    if len(parts) != 2:
        return None
    key_prefix, secret = parts
    if not key_prefix or not secret:
        return None
    return key_prefix


class ApiKeyStore:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @classmethod
    async def create(cls, database_url: str | None = None) -> "ApiKeyStore":
        url = database_url or build_database_url()
        pool = await asyncpg.create_pool(url, min_size=1, max_size=10)
        instance = cls(pool)
        await instance.init_db()
        return instance

    async def init_db(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_keys (
                    id BIGSERIAL PRIMARY KEY,
                    key_prefix TEXT UNIQUE NOT NULL,
                    key_hash TEXT UNIQUE NOT NULL,
                    owner_name TEXT NOT NULL,
                    scopes TEXT[] NOT NULL DEFAULT ARRAY['chat:completions']::TEXT[],
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_used_at TIMESTAMPTZ,
                    revoked_at TIMESTAMPTZ
                )
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_api_keys_active_prefix
                ON api_keys (key_prefix)
                WHERE revoked_at IS NULL
                """
            )

    async def authenticate(self, api_key: str) -> ApiKeyPrincipal | None:
        key_prefix = extract_key_prefix(api_key)
        if not key_prefix:
            return None

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT key_hash, owner_name, scopes
                FROM api_keys
                WHERE key_prefix = $1
                  AND revoked_at IS NULL
                LIMIT 1
                """,
                key_prefix,
            )
            if not row:
                return None

            calculated = hash_api_key(api_key)
            stored = row["key_hash"]
            if not hmac.compare_digest(calculated, stored):
                return None

            await conn.execute(
                """
                UPDATE api_keys
                SET last_used_at = NOW()
                WHERE key_prefix = $1
                """,
                key_prefix,
            )

            scopes = row["scopes"] or []
            return ApiKeyPrincipal(
                owner_name=row["owner_name"],
                scopes=scopes,
                key_prefix=key_prefix,
            )

    async def close(self) -> None:
        await self.pool.close()
