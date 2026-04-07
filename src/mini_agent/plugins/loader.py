"""Enhanced plugin system with dynamic loading and hot reload support."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from mini_agent.plugins.registry import (
    CapabilityDomain,
    PluginCapability,
    PluginCapabilityRegistry,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


@dataclass
class PluginManifest:
    """Plugin manifest for discovery and loading."""

    plugin_id: str
    name: str
    version: str
    description: str = ""
    author: str = ""
    entry_point: str = "main"
    dependencies: list[str] = field(default_factory=list)
    capabilities: list[dict[str, Any]] = field(default_factory=list)
    enabled: bool = True
    priority: int = 100

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PluginManifest":
        return cls(
            plugin_id=data.get("plugin_id", ""),
            name=data.get("name", ""),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            entry_point=data.get("entry_point", "main"),
            dependencies=data.get("dependencies", []),
            capabilities=data.get("capabilities", []),
            enabled=data.get("enabled", True),
            priority=data.get("priority", 100),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "entry_point": self.entry_point,
            "dependencies": self.dependencies,
            "capabilities": self.capabilities,
            "enabled": self.enabled,
            "priority": self.priority,
        }


@dataclass
class LoadedPlugin:
    """A loaded plugin instance."""

    manifest: PluginManifest
    module: Any = None
    loaded_at: str = ""
    status: str = "loaded"  # loaded, error, disabled
    error_message: str | None = None
    file_path: Path | None = None
    file_modified_at: float | None = None


class PluginLoader:
    """Dynamic plugin loader with hot reload support."""

    def __init__(
        self,
        plugin_dirs: list[Path] | None = None,
        registry: PluginCapabilityRegistry | None = None,
    ) -> None:
        self.plugin_dirs = plugin_dirs or [Path("./plugins")]
        self.registry = registry or PluginCapabilityRegistry()
        self._loaded: dict[str, LoadedPlugin] = {}
        self._watchers: dict[str, asyncio.Task] = {}
        self._on_load_hooks: list[Callable[[LoadedPlugin], None]] = []
        self._on_unload_hooks: list[Callable[[LoadedPlugin], None]] = []
        self._on_reload_hooks: list[Callable[[LoadedPlugin, LoadedPlugin], None]] = []

    def add_plugin_dir(self, path: Path) -> None:
        """Add a plugin directory."""
        path = Path(path).resolve()
        if path not in self.plugin_dirs:
            self.plugin_dirs.append(path)

    def on_load(self, hook: Callable[[LoadedPlugin], None]) -> None:
        """Register a hook to be called when a plugin is loaded."""
        self._on_load_hooks.append(hook)

    def on_unload(self, hook: Callable[[LoadedPlugin], None]) -> None:
        """Register a hook to be called when a plugin is unloaded."""
        self._on_unload_hooks.append(hook)

    def on_reload(self, hook: Callable[[LoadedPlugin, LoadedPlugin], None]) -> None:
        """Register a hook to be called when a plugin is reloaded."""
        self._on_reload_hooks.append(hook)

    def discover_plugins(self) -> list[PluginManifest]:
        """Discover all plugins in plugin directories."""
        manifests = []

        for plugin_dir in self.plugin_dirs:
            plugin_dir = Path(plugin_dir).resolve()
            if not plugin_dir.exists():
                continue

            # Look for plugin.json or manifest.json
            for manifest_file in plugin_dir.rglob("plugin.json"):
                try:
                    data = json.loads(manifest_file.read_text(encoding="utf-8"))
                    manifest = PluginManifest.from_dict(data)
                    manifests.append(manifest)
                except Exception:
                    continue

            # Also look for Python packages with __plugin__.py
            for plugin_file in plugin_dir.rglob("__plugin__.py"):
                try:
                    plugin_id = plugin_file.parent.name
                    # Try to load manifest from same directory
                    manifest_file = plugin_file.parent / "plugin.json"
                    if manifest_file.exists():
                        continue  # Already loaded above

                    manifest = PluginManifest(
                        plugin_id=plugin_id,
                        name=plugin_id.replace("_", " ").title(),
                        version="1.0.0",
                    )
                    manifests.append(manifest)
                except Exception:
                    continue

        return sorted(manifests, key=lambda m: m.priority)

    async def load_plugin(
        self,
        manifest: PluginManifest,
        *,
        plugin_path: Path | None = None,
    ) -> LoadedPlugin:
        """Load a plugin from its manifest."""
        if not manifest.enabled:
            return LoadedPlugin(
                manifest=manifest,
                status="disabled",
                loaded_at=_utc_iso(_utc_now()) or "",
            )

        # Find plugin path
        if plugin_path is None:
            for plugin_dir in self.plugin_dirs:
                candidate = Path(plugin_dir) / manifest.plugin_id
                if candidate.exists():
                    plugin_path = candidate
                    break

        if plugin_path is None:
            return LoadedPlugin(
                manifest=manifest,
                status="error",
                error_message="Plugin path not found",
                loaded_at=_utc_iso(_utc_now()) or "",
            )

        try:
            # Load the module
            module_path = plugin_path / f"{manifest.entry_point}.py"
            if not module_path.exists():
                module_path = plugin_path / "__init__.py"

            if not module_path.exists():
                raise ImportError(f"No entry point found for plugin {manifest.plugin_id}")

            # Create unique module name
            module_name = f"mini_agent.plugins.loaded.{manifest.plugin_id}"

            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot load spec for {module_path}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Register capabilities
            for cap in manifest.capabilities:
                self.registry.register(
                    plugin_id=manifest.plugin_id,
                    domain=cap.get("domain", "tool"),
                    name=cap.get("name", ""),
                    description=cap.get("description", ""),
                    metadata=cap.get("metadata", {}),
                    replace=True,
                )

            # Get file modification time
            file_modified_at = module_path.stat().st_mtime if module_path.exists() else None

            loaded = LoadedPlugin(
                manifest=manifest,
                module=module,
                loaded_at=_utc_iso(_utc_now()) or "",
                status="loaded",
                file_path=module_path,
                file_modified_at=file_modified_at,
            )

            self._loaded[manifest.plugin_id] = loaded

            # Call load hooks
            for hook in self._on_load_hooks:
                try:
                    hook(loaded)
                except Exception:
                    pass

            return loaded

        except Exception as e:
            return LoadedPlugin(
                manifest=manifest,
                status="error",
                error_message=str(e),
                loaded_at=_utc_iso(_utc_now()) or "",
                file_path=plugin_path,
            )

    async def unload_plugin(self, plugin_id: str) -> bool:
        """Unload a plugin."""
        if plugin_id not in self._loaded:
            return False

        loaded = self._loaded[plugin_id]

        # Unregister capabilities
        self.registry.unregister(plugin_id)

        # Remove from sys.modules
        module_name = f"mini_agent.plugins.loaded.{plugin_id}"
        if module_name in sys.modules:
            del sys.modules[module_name]

        # Call unload hooks
        for hook in self._on_unload_hooks:
            try:
                hook(loaded)
            except Exception:
                pass

        del self._loaded[plugin_id]
        return True

    async def reload_plugin(self, plugin_id: str) -> LoadedPlugin | None:
        """Reload a plugin (hot reload)."""
        if plugin_id not in self._loaded:
            return None

        old_plugin = self._loaded[plugin_id]

        # Unload
        await self.unload_plugin(plugin_id)

        # Reload
        new_plugin = await self.load_plugin(
            old_plugin.manifest,
            plugin_path=old_plugin.file_path.parent if old_plugin.file_path else None,
        )

        # Call reload hooks
        for hook in self._on_reload_hooks:
            try:
                hook(old_plugin, new_plugin)
            except Exception:
                pass

        return new_plugin

    async def check_for_updates(self) -> list[str]:
        """Check for plugins that need reloading due to file changes."""
        updated = []

        for plugin_id, loaded in self._loaded.items():
            if loaded.file_path is None:
                continue

            try:
                current_mtime = loaded.file_path.stat().st_mtime
                if loaded.file_modified_at is not None and current_mtime > loaded.file_modified_at:
                    updated.append(plugin_id)
            except Exception:
                pass

        return updated

    async def start_hot_reload_watcher(self, interval: float = 5.0) -> None:
        """Start watching for plugin file changes."""
        async def watcher() -> None:
            while True:
                await asyncio.sleep(interval)
                updated = await self.check_for_updates()
                for plugin_id in updated:
                    print(f"Hot reloading plugin: {plugin_id}")
                    await self.reload_plugin(plugin_id)

        task = asyncio.create_task(watcher())
        self._watchers["main"] = task

    def stop_hot_reload_watcher(self) -> None:
        """Stop the hot reload watcher."""
        for task in self._watchers.values():
            task.cancel()
        self._watchers.clear()

    def get_loaded_plugins(self) -> list[LoadedPlugin]:
        """Get all loaded plugins."""
        return list(self._loaded.values())

    def get_plugin(self, plugin_id: str) -> LoadedPlugin | None:
        """Get a loaded plugin by ID."""
        return self._loaded.get(plugin_id)

    def is_loaded(self, plugin_id: str) -> bool:
        """Check if a plugin is loaded."""
        return plugin_id in self._loaded


class DynamicToolRegistry:
    """Registry for dynamically registered tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Callable] = {}
        self._schemas: dict[str, dict[str, Any]] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    def register(
        self,
        name: str,
        handler: Callable,
        schema: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register a tool dynamically."""
        self._tools[name] = handler
        if schema:
            self._schemas[name] = schema
        if metadata:
            self._metadata[name] = metadata

    def unregister(self, name: str) -> bool:
        """Unregister a tool."""
        if name in self._tools:
            del self._tools[name]
            self._schemas.pop(name, None)
            self._metadata.pop(name, None)
            return True
        return False

    def get_handler(self, name: str) -> Callable | None:
        """Get a tool handler."""
        return self._tools.get(name)

    def get_schema(self, name: str) -> dict[str, Any] | None:
        """Get a tool schema."""
        return self._schemas.get(name)

    def get_metadata(self, name: str) -> dict[str, Any] | None:
        """Get tool metadata."""
        return self._metadata.get(name)

    def list_tools(self) -> list[str]:
        """List all registered tools."""
        return list(self._tools.keys())

    def list_with_schemas(self) -> dict[str, dict[str, Any]]:
        """List all tools with their schemas."""
        return {
            name: {
                "schema": self._schemas.get(name, {}),
                "metadata": self._metadata.get(name, {}),
            }
            for name in self._tools
        }


# Global instances
_plugin_loader: PluginLoader | None = None
_dynamic_tool_registry: DynamicToolRegistry | None = None


def get_plugin_loader() -> PluginLoader:
    """Get the global plugin loader."""
    global _plugin_loader
    if _plugin_loader is None:
        _plugin_loader = PluginLoader()
    return _plugin_loader


def get_dynamic_tool_registry() -> DynamicToolRegistry:
    """Get the global dynamic tool registry."""
    global _dynamic_tool_registry
    if _dynamic_tool_registry is None:
        _dynamic_tool_registry = DynamicToolRegistry()
    return _dynamic_tool_registry
