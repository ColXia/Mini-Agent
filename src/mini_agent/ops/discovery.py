"""Operational discovery helpers for subprograms and channels."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DiscoveredModule:
    """Represents a discovered module (subprogram or channel)."""

    name: str
    path: Path
    module_type: str  # "subprogram" or "channel"
    enabled: bool = True
    description: str = ""
    version: str = "0.0.0"
    entry_point: str | None = None
    router_module: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class DiscoveryResult:
    """Result of a discovery scan."""

    modules: list[DiscoveredModule] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def enabled_modules(self) -> list[DiscoveredModule]:
        """Get all enabled modules."""
        return [item for item in self.modules if item.enabled and not item.error]

    @property
    def subprograms(self) -> list[DiscoveredModule]:
        """Get all discovered subprograms."""
        return [item for item in self.modules if item.module_type == "subprogram"]

    @property
    def channels(self) -> list[DiscoveredModule]:
        """Get all discovered channels."""
        return [item for item in self.modules if item.module_type == "channel"]


class BaseScanner:
    """Base scanner class for discovering modules."""

    MANIFEST_FILE = "manifest.json"

    def __init__(self, base_path: Path | None = None):
        if base_path is None:
            current = Path(__file__).resolve()
            for parent in current.parents:
                if (parent / "pyproject.toml").exists():
                    base_path = parent
                    break
            else:
                base_path = Path.cwd()
        self.base_path = base_path

    def _read_manifest(self, manifest_path: Path) -> dict[str, Any]:
        if not manifest_path.exists():
            return {}
        try:
            content = manifest_path.read_text(encoding="utf-8")
            return json.loads(content)
        except (json.JSONDecodeError, OSError) as exc:
            return {"error": str(exc)}

    @staticmethod
    def _check_python_module(path: Path) -> bool:
        return (path / "__init__.py").exists() or (path / "main.py").exists()

    @staticmethod
    def _check_node_module(path: Path) -> bool:
        return (path / "package.json").exists()

    def scan_directory(
        self,
        directory_name: str,
        module_type: str,
    ) -> list[DiscoveredModule]:
        modules: list[DiscoveredModule] = []
        scan_path = self.base_path / directory_name
        if not scan_path.exists():
            return modules

        for item in scan_path.iterdir():
            if not item.is_dir():
                continue
            if item.name.startswith(".") or item.name == "node_modules":
                continue
            module = self._discover_module(item, module_type)
            if module is not None:
                modules.append(module)
        return modules

    def _discover_module(
        self,
        path: Path,
        module_type: str,
    ) -> DiscoveredModule | None:
        manifest_path = path / self.MANIFEST_FILE
        manifest = self._read_manifest(manifest_path)

        is_python = self._check_python_module(path)
        is_node = self._check_node_module(path)
        if not is_python and not is_node:
            is_python = bool(list(path.glob("*.py")))
            is_node = bool(list(path.glob("*.ts"))) or bool(list(path.glob("*.js")))

        if not is_python and not is_node:
            return None

        name = manifest.get("name", path.name)
        description = manifest.get("description", "")
        version = manifest.get("version", "0.0.0")
        enabled = manifest.get("enabled", True)
        entry_point = manifest.get("entry_point")
        router_module = manifest.get("router_module")
        config = manifest.get("config", {})
        error = manifest.get("error")

        if not entry_point:
            if is_python:
                if (path / "main.py").exists():
                    entry_point = f"{path.name}.main:main"
                elif (path / "__init__.py").exists():
                    entry_point = path.name
            elif is_node:
                if (path / "dist" / "index.js").exists():
                    entry_point = "node dist/index.js"
                elif (path / "index.js").exists():
                    entry_point = "node index.js"

        if module_type == "subprogram" and not router_module and (path / "gateway" / "router.py").exists():
            router_module = f"{path.name}.gateway.router:router"

        return DiscoveredModule(
            name=name,
            path=path,
            module_type=module_type,
            enabled=enabled,
            description=description,
            version=version,
            entry_point=entry_point,
            router_module=router_module,
            config=config,
            error=error,
        )


class SubprogramScanner(BaseScanner):
    """Scanner for discovering subprograms."""

    def scan(self) -> DiscoveryResult:
        return DiscoveryResult(modules=self.scan_directory("subprograms", "subprogram"))


class ChannelScanner(BaseScanner):
    """Scanner for discovering channels."""

    def scan(self) -> DiscoveryResult:
        return DiscoveryResult(modules=self.scan_directory("channels", "channel"))


def discover_all(base_path: Path | None = None) -> tuple[DiscoveryResult, DiscoveryResult]:
    """Discover all subprograms and channels from the repo root."""

    subprogram_scanner = SubprogramScanner(base_path)
    channel_scanner = ChannelScanner(base_path)
    return subprogram_scanner.scan(), channel_scanner.scan()


__all__ = [
    "ChannelScanner",
    "DiscoveredModule",
    "DiscoveryResult",
    "SubprogramScanner",
    "discover_all",
]
