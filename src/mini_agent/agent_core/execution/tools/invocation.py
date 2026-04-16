"""Declarative tool invocation model and schema validation helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
import inspect
from typing import Any, Awaitable, Callable, Mapping

from mini_agent.agent_core.execution.tools.attributes import DeclarativeToolAttributes, ToolKind
from mini_agent.tools.base import ToolResult


InvocationExecutor = Callable[[dict[str, Any]], ToolResult | Awaitable[ToolResult]]
_INTERNAL_ARGUMENT_PREFIX = "_mini_agent_"


def _is_instance_of_type(value: Any, schema_type: str) -> bool:
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return (isinstance(value, int) and not isinstance(value, bool)) or isinstance(value, float)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "object":
        return isinstance(value, Mapping)
    if schema_type == "null":
        return value is None
    return True


def _validate_schema_value(schema: Mapping[str, Any], value: Any, path: str) -> None:
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        if not any(_is_instance_of_type(value, candidate) for candidate in schema_type):
            raise ValueError(f"{path} must match one of types {schema_type}.")
        first_match = next((item for item in schema_type if _is_instance_of_type(value, item)), None)
        if isinstance(first_match, str):
            schema_type = first_match
    elif isinstance(schema_type, str) and not _is_instance_of_type(value, schema_type):
        raise ValueError(f"{path} must be '{schema_type}'.")

    if schema_type == "object":
        if not isinstance(value, Mapping):
            raise ValueError(f"{path} must be an object.")
        properties = schema.get("properties") if isinstance(schema.get("properties"), Mapping) else {}
        required = schema.get("required") if isinstance(schema.get("required"), list) else []
        for key in required:
            if key not in value:
                raise ValueError(f"{path}.{key} is required.")
        additional_properties = schema.get("additionalProperties", True)
        if additional_properties is False:
            unknown = [key for key in value.keys() if key not in properties]
            if unknown:
                raise ValueError(f"{path} has unknown fields: {', '.join(sorted(map(str, unknown)))}.")
        for key, prop_schema in properties.items():
            if key in value and isinstance(prop_schema, Mapping):
                _validate_schema_value(prop_schema, value[key], f"{path}.{key}")
        return

    if schema_type == "array":
        if not isinstance(value, list):
            raise ValueError(f"{path} must be an array.")
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(value):
                _validate_schema_value(item_schema, item, f"{path}[{index}]")
        return

    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values and value not in enum_values:
        raise ValueError(f"{path} must be one of {enum_values}.")


def _default_tool_locations(arguments: Mapping[str, Any]) -> list[str]:
    candidates = (
        "path",
        "paths",
        "file_path",
        "target_path",
        "cwd",
        "directory",
        "dir",
        "workspace",
    )
    locations: list[str] = []
    for key in candidates:
        raw_value = arguments.get(key)
        if isinstance(raw_value, str) and raw_value.strip():
            locations.append(raw_value.strip())
        elif isinstance(raw_value, list):
            for item in raw_value:
                if isinstance(item, str) and item.strip():
                    locations.append(item.strip())
    dedup: list[str] = []
    seen: set[str] = set()
    for value in locations:
        if value not in seen:
            seen.add(value)
            dedup.append(value)
    return dedup


@dataclass
class ToolInvocation:
    """A concrete invocation of a declarative tool."""

    tool_name: str
    schema: Mapping[str, Any]
    arguments: dict[str, Any]
    executor: InvocationExecutor
    attributes: DeclarativeToolAttributes = field(default_factory=DeclarativeToolAttributes)

    def validate(self) -> bool:
        public_arguments = {
            key: value
            for key, value in self.arguments.items()
            if not str(key).startswith(_INTERNAL_ARGUMENT_PREFIX)
        }
        _validate_schema_value(self.schema, public_arguments, self.tool_name)
        return True

    def should_confirm_execute(self) -> bool:
        attrs = self.attributes.normalized()
        if attrs.is_read_only:
            return False
        if attrs.is_destructive():
            return True
        return attrs.kind in {
            ToolKind.WRITE,
            ToolKind.EDIT,
            ToolKind.DELETE,
            ToolKind.EXECUTE,
            ToolKind.DELEGATE,
        }

    def tool_locations(self) -> list[str]:
        attrs = self.attributes.normalized()
        extractor = attrs.location_extractor or _default_tool_locations
        return extractor(self.arguments)

    def _apply_result_limit(self, result: ToolResult) -> ToolResult:
        attrs = self.attributes.normalized()
        limit = attrs.max_result_size_chars
        if limit is None or limit <= 0 or len(result.content) <= limit:
            return result
        truncated_content = (
            result.content[:limit]
            + f"\n...[truncated to {limit} chars by declarative tool contract]"
        )
        return ToolResult(success=result.success, content=truncated_content, error=result.error)

    async def execute(self) -> ToolResult:
        self.validate()
        raw_result = self.executor(dict(self.arguments))
        result = await raw_result if inspect.isawaitable(raw_result) else raw_result
        if not isinstance(result, ToolResult):
            raise TypeError(f"{self.tool_name} executor must return ToolResult.")
        return self._apply_result_limit(result)
