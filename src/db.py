import os


def build_database_url() -> str:
    """Resolve database URL from env with local defaults."""
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "password")
    db = os.getenv("POSTGRES_DB", "gateway")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"
