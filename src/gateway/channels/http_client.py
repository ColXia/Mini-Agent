"""HTTP Gateway client implementation.

This module provides an HTTP-based implementation of IGatewayClient
for channels to communicate with the Gateway.
"""

import json
from typing import Any, Optional

import httpx

from .base import IGatewayClient


class HTTPGatewayClient(IGatewayClient):
    """HTTP-based Gateway client.

    This client communicates with the Gateway via HTTP REST API.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8008",
        timeout: float = 120.0,
    ):
        """Initialize the HTTP Gateway client.

        Args:
            base_url: Gateway base URL
            timeout: Request timeout in seconds
        """
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "HTTPGatewayClient":
        """Async context manager entry."""
        self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        workspace_dir: Optional[str] = None,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a message to the Gateway and get a reply.

        Args:
            message: User message content
            session_id: Optional session ID for conversation continuity
            workspace_dir: Optional workspace directory
            dry_run: If True, don't actually call the LLM
            **kwargs: Additional parameters (ignored)

        Returns:
            Dictionary with session_id, reply, message_count, token_usage
        """
        client = self._get_client()

        payload = {
            "message": message,
            "session_id": session_id,
            "workspace_dir": workspace_dir,
            "dry_run": dry_run,
        }
        # Remove None values
        payload = {k: v for k, v in payload.items() if v is not None}

        response = await client.post(
            f"{self._base_url}/api/chat",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        return response.json()

    async def reset_session(self, session_id: str) -> bool:
        """Reset a session's context.

        Args:
            session_id: Session identifier

        Returns:
            True if reset successful, False otherwise
        """
        client = self._get_client()

        response = await client.post(
            f"{self._base_url}/api/sessions/{session_id}/reset",
        )
        if response.status_code == 200:
            return True
        return False

    async def health_check(self) -> bool:
        """Check if the Gateway is healthy.

        Returns:
            True if healthy, False otherwise
        """
        client = self._get_client()

        try:
            response = await client.get(f"{self._base_url}/api/health")
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
