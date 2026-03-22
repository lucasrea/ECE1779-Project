#!/usr/bin/env python3
"""Internal-only JWT issuer for gateway team tokens."""

import argparse
import datetime as dt
import os
import uuid

import jwt


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Issue an HS256 gateway token for a team/service.",
    )
    parser.add_argument(
        "--team-id",
        required=True,
        help="Team/service identifier written to `sub` claim.",
    )
    parser.add_argument(
        "--scope",
        default=os.getenv("AUTH_REQUIRED_SCOPE", "gateway:chat:invoke"),
        help="Space-delimited scope claim. Default: AUTH_REQUIRED_SCOPE or gateway:chat:invoke",
    )
    parser.add_argument(
        "--issuer",
        default=os.getenv("AUTH_ISSUER") or None,
        help="Optional `iss` claim. Default: AUTH_ISSUER.",
    )
    parser.add_argument(
        "--audience",
        default=os.getenv("AUTH_AUDIENCE") or None,
        help="Optional `aud` claim. Default: AUTH_AUDIENCE.",
    )
    parser.add_argument(
        "--expires-in-hours",
        type=int,
        default=24 * 30,
        help="Token lifetime in hours. Default: 720 (30 days).",
    )
    parser.add_argument(
        "--token-only",
        action="store_true",
        help="Print only the token string (useful for scripting).",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    secret = os.getenv("AUTH_SHARED_SECRET")
    if not secret:
        raise SystemExit("ERROR: AUTH_SHARED_SECRET must be set.")

    now = dt.datetime.now(dt.timezone.utc)
    exp = now + dt.timedelta(hours=args.expires_in_hours)

    payload: dict[str, object] = {
        "sub": args.team_id,
        "scope": args.scope,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": str(uuid.uuid4()),
    }
    if args.issuer:
        payload["iss"] = args.issuer
    if args.audience:
        payload["aud"] = args.audience

    token = jwt.encode(payload, secret, algorithm="HS256")

    if args.token_only:
        print(token)
        return

    print("Issued gateway JWT:")
    print(f"  team_id:  {args.team_id}")
    print(f"  scope:    {args.scope}")
    print(f"  expires:  {exp.isoformat()}")
    print(f"  issuer:   {args.issuer or '(none)'}")
    print(f"  audience: {args.audience or '(none)'}")
    print("")
    print(token)


if __name__ == "__main__":
    main()
