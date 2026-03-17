import json
import logging
import os

import anyio
import asyncpg
import numpy as np
from pgvector.asyncpg import register_vector

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.95"))
EMBEDDING_DIMENSIONS = 1536


class SemanticCache:
    def __init__(self):
        self._pool: asyncpg.Pool | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def init(self):
        """Create the connection pool and ensure the table exists."""
        self._pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            setup=self._setup_connection,
        )
        await self._create_table()

    @staticmethod
    async def _setup_connection(conn: asyncpg.Connection):
        await register_vector(conn)

    async def _create_table(self):
        async with self._pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS semantic_cache (
                    id SERIAL PRIMARY KEY,
                    embedding VECTOR({EMBEDDING_DIMENSIONS}),
                    messages_text TEXT NOT NULL,
                    response JSONB NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_semantic_cache_embedding
                ON semantic_cache USING hnsw (embedding vector_cosine_ops)
            """)

    async def close(self):
        if self._pool:
            await self._pool.close()
            self._pool = None

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------

    async def _embed(self, text: str) -> np.ndarray:
        from openai import OpenAI

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = await anyio.to_thread.run_sync(
            lambda: client.embeddings.create(model=EMBEDDING_MODEL, input=text)
        )
        return np.array(response.data[0].embedding)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _messages_to_text(messages) -> str:
        """Concatenate messages into a single string for embedding.

        Provider-agnostic: the same conversation produces the same text
        regardless of which provider is selected.
        """
        return "\n".join(f"{m.role}: {m.content}" for m in messages)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get(self, messages) -> dict | None:
        """Return a cached response if a semantically similar query exists."""
        text = self._messages_to_text(messages)
        embedding = await self._embed(text)

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT response,
                       1 - (embedding <=> $1) AS similarity
                FROM semantic_cache
                WHERE 1 - (embedding <=> $1) >= $2
                ORDER BY embedding <=> $1
                LIMIT 1
                """,
                embedding,
                SIMILARITY_THRESHOLD,
            )

        if row:
            logger.info("Cache hit (similarity=%.4f)", row["similarity"])
            return json.loads(row["response"])
        return None

    async def set(self, messages, response: dict):
        """Store a new response with its embedding."""
        text = self._messages_to_text(messages)
        embedding = await self._embed(text)

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO semantic_cache (embedding, messages_text, response)
                VALUES ($1, $2, $3::jsonb)
                """,
                embedding,
                text,
                json.dumps(response),
            )


# Global singleton – initialised at app startup via lifespan
semantic_cache = SemanticCache()
