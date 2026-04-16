"""Ops authentication helpers for the gateway host."""

from __future__ import annotations

import os

from fastapi import Header, HTTPException


def load_ops_api_keys() -> set[str]:
    raw = os.getenv("MINI_AGENT_STUDIO_API_KEYS", "")
    return {item.strip() for item in raw.split(",") if item and item.strip()}


def extract_auth_token(authorization: str | None, x_api_key: str | None) -> str:
    if authorization:
        lower = authorization.lower()
        if lower.startswith("bearer "):
            token = authorization[7:].strip()
            if token:
                return token
    if x_api_key and x_api_key.strip():
        return x_api_key.strip()
    return ""


async def require_ops_auth(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> None:
    allowed = load_ops_api_keys()
    if not allowed:
        return
    token = extract_auth_token(authorization, x_api_key)
    if token in allowed:
        return
    raise HTTPException(status_code=401, detail="Unauthorized. Provide valid ops API token.")


__all__ = ["extract_auth_token", "load_ops_api_keys", "require_ops_auth"]
