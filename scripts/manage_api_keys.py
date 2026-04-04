#!/usr/bin/env python3
import argparse
import asyncio
import secrets
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth import TOKEN_PREFIX, hash_api_key  # noqa: E402
from src.db import build_database_url  # noqa: E402


def _parse_scopes(raw: str | None) -> list[str]:
    if not raw:
        return ["chat:completions"]
    scopes = [item.strip() for item in raw.split(",") if item.strip()]
    return scopes or ["chat:completions"]


async def _create_key(conn: asyncpg.Connection, owner: str, scopes: list[str]) -> None:
    for _ in range(5):
        key_prefix = secrets.token_hex(8)
        secret = secrets.token_urlsafe(24)
        api_key = f"{TOKEN_PREFIX}{key_prefix}_{secret}"
        key_hash = hash_api_key(api_key)
        try:
            await conn.execute(
                """
                INSERT INTO api_keys (key_prefix, key_hash, owner_name, scopes)
                VALUES ($1, $2, $3, $4::TEXT[])
                """,
                key_prefix,
                key_hash,
                owner,
                scopes,
            )
            print("Created API key:")
            print(f"  owner: {owner}")
            print(f"  prefix: {key_prefix}")
            print(f"  scopes: {', '.join(scopes)}")
            print("")
            print("Plaintext key (shown once):")
            print(api_key)
            return
        except asyncpg.UniqueViolationError:
            continue
    raise RuntimeError("Could not allocate unique key prefix after multiple attempts")


async def _list_keys(conn: asyncpg.Connection, show_revoked: bool) -> None:
    query = """
        SELECT key_prefix, owner_name, scopes, created_at, last_used_at, revoked_at
        FROM api_keys
    """
    if not show_revoked:
        query += " WHERE revoked_at IS NULL"
    query += " ORDER BY created_at DESC"

    rows = await conn.fetch(query)
    if not rows:
        print("No API keys found.")
        return

    for row in rows:
        state = "revoked" if row["revoked_at"] else "active"
        scopes = ",".join(row["scopes"] or [])
        print(
            f"{row['key_prefix']} owner={row['owner_name']} scopes=[{scopes}] "
            f"created={row['created_at']} last_used={row['last_used_at']} status={state}"
        )


async def _revoke_key(conn: asyncpg.Connection, key_prefix: str) -> None:
    result = await conn.execute(
        """
        UPDATE api_keys
        SET revoked_at = NOW()
        WHERE key_prefix = $1
          AND revoked_at IS NULL
        """,
        key_prefix,
    )
    count = int(result.split(" ")[-1])
    if count == 0:
        print(f"No active key found for prefix: {key_prefix}")
        return
    print(f"Revoked key: {key_prefix}")


async def main() -> None:
    load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser(description="Manage gateway API keys")
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override DATABASE_URL for this command",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Create a new API key")
    create_parser.add_argument("--owner", required=True, help="Owner/user label")
    create_parser.add_argument(
        "--scopes",
        default="chat:completions",
        help="Comma-separated scopes (default: chat:completions)",
    )

    list_parser = subparsers.add_parser("list", help="List API keys")
    list_parser.add_argument(
        "--all",
        action="store_true",
        help="Include revoked keys",
    )

    revoke_parser = subparsers.add_parser("revoke", help="Revoke an API key by prefix")
    revoke_parser.add_argument("--prefix", required=True, help="Key prefix")

    args = parser.parse_args()
    db_url = args.database_url or build_database_url()

    conn = await asyncpg.connect(db_url)
    try:
        if args.command == "create":
            await _create_key(conn, owner=args.owner, scopes=_parse_scopes(args.scopes))
        elif args.command == "list":
            await _list_keys(conn, show_revoked=args.all)
        elif args.command == "revoke":
            await _revoke_key(conn, key_prefix=args.prefix)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
