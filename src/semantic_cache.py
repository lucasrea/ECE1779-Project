import hashlib
import json
import logging
import os

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = float(os.getenv("CACHE_SIMILARITY_THRESHOLD", "0.95"))
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
EMBEDDING_DIM = 384


def _build_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "password")
    db = os.getenv("POSTGRES_DB", "gateway")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


class SemanticCache:
    """pgvector-backed semantic cache with local sentence-transformer embeddings."""

    def __init__(self, pool, model):
        self.pool = pool
        self.model = model

    @classmethod
    async def create(cls, database_url: str | None = None) -> "SemanticCache":
        import asyncpg
        from pgvector.asyncpg import register_vector
        from sentence_transformers import SentenceTransformer

        url = database_url or _build_database_url()

        # The vector extension must exist before register_vector can set up
        # type codecs, so bootstrap it with a one-off connection first.
        bootstrap = await asyncpg.connect(url)
        await bootstrap.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await bootstrap.close()

        pool = await asyncpg.create_pool(
            url, min_size=2, max_size=10, init=register_vector,
        )
        model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        instance = cls(pool, model)
        await instance.init_db()
        return instance

    async def init_db(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS semantic_cache (
                    id SERIAL PRIMARY KEY,
                    embedding vector({EMBEDDING_DIM}),
                    messages_hash TEXT UNIQUE NOT NULL,
                    messages_text TEXT NOT NULL,
                    response JSONB NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cache_embedding
                ON semantic_cache USING hnsw (embedding vector_cosine_ops)
            """)

    def _embed(self, messages):
        text = " ".join(m.content for m in messages)
        return self.model.encode(text)

    @staticmethod
    def _messages_hash(messages) -> str:
        text = str([(m.role, m.content) for m in messages])
        return hashlib.sha256(text.encode()).hexdigest()

    async def lookup(self, messages) -> dict | None:
        embedding = self._embed(messages)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT response, 1 - (embedding <=> $1) AS similarity
                FROM semantic_cache
                WHERE 1 - (embedding <=> $1) >= $2
                ORDER BY embedding <=> $1
                LIMIT 1
                """,
                embedding,
                SIMILARITY_THRESHOLD,
            )
            if row:
                return json.loads(row["response"])
            return None

    async def store(self, messages, response: dict, provider: str, model: str) -> None:
        embedding = self._embed(messages)
        msg_hash = self._messages_hash(messages)
        text = " ".join(m.content for m in messages)
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO semantic_cache
                    (embedding, messages_hash, messages_text, response, provider, model)
                VALUES ($1, $2, $3, $4::jsonb, $5, $6)
                ON CONFLICT (messages_hash) DO UPDATE
                    SET response = EXCLUDED.response,
                        provider = EXCLUDED.provider,
                        model    = EXCLUDED.model
                """,
                embedding,
                msg_hash,
                text,
                json.dumps(response),
                provider,
                model,
            )

    async def close(self) -> None:
        await self.pool.close()
