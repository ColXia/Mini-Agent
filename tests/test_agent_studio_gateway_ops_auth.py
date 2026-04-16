from __future__ import annotations

import pytest
from fastapi import HTTPException

from apps.agent_studio_gateway.ops_auth import extract_auth_token, load_ops_api_keys, require_ops_auth


def test_load_ops_api_keys_trims_and_skips_empty(monkeypatch) -> None:
    monkeypatch.setenv("MINI_AGENT_STUDIO_API_KEYS", " alpha ,, beta ,  ,gamma ")

    assert load_ops_api_keys() == {"alpha", "beta", "gamma"}


def test_extract_auth_token_prefers_bearer_before_x_api_key() -> None:
    assert extract_auth_token("Bearer demo-token", "fallback-token") == "demo-token"
    assert extract_auth_token(None, "fallback-token") == "fallback-token"
    assert extract_auth_token("Basic nope", "fallback-token") == "fallback-token"
    assert extract_auth_token(None, None) == ""


@pytest.mark.asyncio
async def test_require_ops_auth_allows_missing_key_config(monkeypatch) -> None:
    monkeypatch.delenv("MINI_AGENT_STUDIO_API_KEYS", raising=False)

    await require_ops_auth(authorization=None, x_api_key=None)


@pytest.mark.asyncio
async def test_require_ops_auth_accepts_bearer_and_rejects_invalid(monkeypatch) -> None:
    monkeypatch.setenv("MINI_AGENT_STUDIO_API_KEYS", "studio-token")

    await require_ops_auth(authorization="Bearer studio-token", x_api_key=None)
    await require_ops_auth(authorization=None, x_api_key="studio-token")

    with pytest.raises(HTTPException) as excinfo:
        await require_ops_auth(authorization="Bearer wrong-token", x_api_key=None)

    assert excinfo.value.status_code == 401
