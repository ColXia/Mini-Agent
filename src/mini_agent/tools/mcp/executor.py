"""MCP tool wrappers and resource access adapters."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp import ClientSession

from mini_agent.tools.base import Tool, ToolResult


def _content_to_text(item: Any) -> str:
    text = getattr(item, "text", None)
    if text is not None:
        return str(text)
    if isinstance(item, dict) and "text" in item:
        return str(item.get("text", ""))
    return str(item)


def _resource_name(resource: Any) -> str:
    name = getattr(resource, "name", None)
    if name:
        return str(name)
    if isinstance(resource, dict) and resource.get("name"):
        return str(resource["name"])
    return ""


def _resource_uri(resource: Any) -> str:
    uri = getattr(resource, "uri", None)
    if uri:
        return str(uri)
    if isinstance(resource, dict) and resource.get("uri"):
        return str(resource["uri"])
    return ""


def _resource_description(resource: Any) -> str:
    description = getattr(resource, "description", None)
    if description:
        return str(description)
    if isinstance(resource, dict) and resource.get("description"):
        return str(resource["description"])
    return ""


def _resource_mime_type(resource: Any) -> str:
    mime_type = getattr(resource, "mimeType", None)
    if mime_type:
        return str(mime_type)
    if isinstance(resource, dict) and resource.get("mimeType"):
        return str(resource["mimeType"])
    return ""


class MCPTool(Tool):
    """Wrapper for MCP tools with timeout handling."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        session: ClientSession,
        execute_timeout: float,
    ):
        self._name = name
        self._description = description
        self._parameters = parameters
        self._session = session
        self._execute_timeout = execute_timeout

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def execute(self, **kwargs) -> ToolResult:
        try:
            async with asyncio.timeout(self._execute_timeout):
                result = await self._session.call_tool(self._name, arguments=kwargs)

            content_parts = [_content_to_text(item) for item in getattr(result, "content", [])]
            content_str = "\n".join(content_parts)
            is_error = bool(getattr(result, "isError", False))

            return ToolResult(
                success=not is_error,
                content=content_str,
                error=None if not is_error else "Tool returned error",
            )
        except TimeoutError:
            return ToolResult(
                success=False,
                content="",
                error=f"MCP tool execution timed out after {self._execute_timeout}s.",
            )
        except Exception as exc:
            return ToolResult(success=False, content="", error=f"MCP tool execution failed: {exc}")


class MCPResourceListTool(Tool):
    """Expose MCP `list_resources` as a regular tool."""

    def __init__(self, server_name: str, session: ClientSession, execute_timeout: float):
        self._server_name = server_name
        self._session = session
        self._execute_timeout = execute_timeout
        normalized = server_name.replace("-", "_").replace(" ", "_")
        self._name = f"{normalized}_list_resources"

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"List resources exposed by MCP server '{self._server_name}'."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                "uri_prefix": {"type": "string"},
            },
        }

    async def execute(self, **kwargs) -> ToolResult:
        try:
            limit = kwargs.get("limit")
            uri_prefix = str(kwargs.get("uri_prefix", "")).strip()
            async with asyncio.timeout(self._execute_timeout):
                result = await self._session.list_resources()

            resources = getattr(result, "resources", []) or []
            normalized = []
            for item in resources:
                uri = _resource_uri(item)
                if uri_prefix and not uri.startswith(uri_prefix):
                    continue
                normalized.append(
                    {
                        "name": _resource_name(item),
                        "uri": uri,
                        "description": _resource_description(item),
                        "mime_type": _resource_mime_type(item),
                    }
                )

            if isinstance(limit, int) and limit > 0:
                normalized = normalized[:limit]

            return ToolResult(
                success=True,
                content=json.dumps(
                    {
                        "server": self._server_name,
                        "count": len(normalized),
                        "resources": normalized,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )
        except TimeoutError:
            return ToolResult(
                success=False,
                content="",
                error=f"MCP list_resources timed out after {self._execute_timeout}s.",
            )
        except Exception as exc:
            return ToolResult(success=False, content="", error=f"MCP list_resources failed: {exc}")


class MCPResourceReadTool(Tool):
    """Expose MCP `read_resource` as a regular tool."""

    def __init__(self, server_name: str, session: ClientSession, execute_timeout: float):
        self._server_name = server_name
        self._session = session
        self._execute_timeout = execute_timeout
        normalized = server_name.replace("-", "_").replace(" ", "_")
        self._name = f"{normalized}_read_resource"

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"Read one MCP resource by URI from server '{self._server_name}'."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "uri": {"type": "string"},
            },
            "required": ["uri"],
        }

    async def execute(self, **kwargs) -> ToolResult:
        uri = kwargs.get("uri")
        if not isinstance(uri, str) or not uri.strip():
            return ToolResult(success=False, content="", error="`uri` is required.")

        try:
            async with asyncio.timeout(self._execute_timeout):
                result = await self._session.read_resource(uri=uri)

            parts = []
            for item in getattr(result, "contents", []) or []:
                parts.append(_content_to_text(item))

            return ToolResult(success=True, content="\n".join(parts))
        except TimeoutError:
            return ToolResult(
                success=False,
                content="",
                error=f"MCP read_resource timed out after {self._execute_timeout}s.",
            )
        except Exception as exc:
            return ToolResult(success=False, content="", error=f"MCP read_resource failed: {exc}")

