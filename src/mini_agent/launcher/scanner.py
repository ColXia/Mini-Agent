"""Auto-discovery scanner for subprograms and channels.

This module provides automatic scanning and discovery of:
- Subprograms in the `subprograms/` directory
- Channels in the `channels/` directory

Each subprogram/channel can expose a manifest file describing its capabilities.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class DiscoveredModule:
    """Represents a discovered module (subprogram or channel)."""

    name: str
    path: Path
    module_type: str  # "subprogram" or "channel"
    enabled: bool = True
    description: str = ""
    version: str = "0.0.0"
    entry_point: Optional[str] = None
    router_module: Optional[str] = None
    config: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class DiscoveryResult:
    """Result of a discovery scan."""

    modules: list[DiscoveredModule] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def enabled_modules(self) -> list[DiscoveredModule]:
        """Get all enabled modules."""
        return [m for m in self.modules if m.enabled and not m.error]

    @property
    def subprograms(self) -> list[DiscoveredModule]:
        """Get all subprograms."""
        return [m for m in self.modules if m.module_type == "subprogram"]

    @property
    def channels(self) -> list[DiscoveredModule]:
        """Get all channels."""
        return [m for m in self.modules if m.module_type == "channel"]


class BaseScanner:
    """Base scanner class for discovering modules."""

    MANIFEST_FILE = "manifest.json"

    def __init__(self, base_path: Optional[Path] = None):
        """Initialize the scanner.

        Args:
            base_path: Base path to scan from. Defaults to repo root.
        """
        if base_path is None:
            # Find repo root by looking for pyproject.toml
            current = Path(__file__).resolve()
            for parent in current.parents:
                if (parent / "pyproject.toml").exists():
                    base_path = parent
                    break
            else:
                base_path = Path.cwd()
        self.base_path = base_path

    def _read_manifest(self, manifest_path: Path) -> dict[str, Any]:
        """Read a manifest file.

        Args:
            manifest_path: Path to the manifest file

        Returns:
            Manifest data as dictionary
        """
        if not manifest_path.exists():
            return {}

        try:
            content = manifest_path.read_text(encoding="utf-8")
            return json.loads(content)
        except (json.JSONDecodeError, OSError) as e:
            return {"error": str(e)}

    def _check_python_module(self, path: Path) -> bool:
        """Check if a path contains a valid Python module.

        Args:
            path: Directory path to check

        Returns:
            True if it's a valid Python module
        """
        return (path / "__init__.py").exists() or (path / "main.py").exists()

    def _check_node_module(self, path: Path) -> bool:
        """Check if a path contains a valid Node.js module.

        Args:
            path: Directory path to check

        Returns:
            True if it's a valid Node.js module
        """
        return (path / "package.json").exists()

    def scan_directory(
        self,
        directory_name: str,
        module_type: str,
    ) -> list[DiscoveredModule]:
        """Scan a directory for modules.

        Args:
            directory_name: Name of the directory to scan (e.g., "subprograms")
            module_type: Type of module (e.g., "subprogram", "channel")

        Returns:
            List of discovered modules
        """
        modules = []
        scan_path = self.base_path / directory_name

        if not scan_path.exists():
            return modules

        for item in scan_path.iterdir():
            if not item.is_dir():
                continue

            # Skip hidden directories and node_modules
            if item.name.startswith(".") or item.name == "node_modules":
                continue

            module = self._discover_module(item, module_type)
            if module:
                modules.append(module)

        return modules

    def _discover_module(
        self,
        path: Path,
        module_type: str,
    ) -> Optional[DiscoveredModule]:
        """Discover a module at the given path.

        Args:
            path: Path to the module directory
            module_type: Type of module

        Returns:
            DiscoveredModule if valid, None otherwise
        """
        manifest_path = path / self.MANIFEST_FILE
        manifest = self._read_manifest(manifest_path)

        # Determine module type (Python or Node.js)
        is_python = self._check_python_module(path)
        is_node = self._check_node_module(path)

        if not is_python and not is_node:
            # Try to infer from structure
            is_python = bool(list(path.glob("*.py")))
            is_node = bool(list(path.glob("*.ts"))) or bool(list(path.glob("*.js")))

        # Build module info
        name = manifest.get("name", path.name)
        description = manifest.get("description", "")
        version = manifest.get("version", "0.0.0")
        enabled = manifest.get("enabled", True)
        entry_point = manifest.get("entry_point")
        router_module = manifest.get("router_module")
        config = manifest.get("config", {})
        error = manifest.get("error")

        # Auto-detect entry point if not specified
        if not entry_point:
            if is_python:
                if (path / "main.py").exists():
                    entry_point = f"{path.name}.main:main"
                elif (path / "__init__.py").exists():
                    entry_point = f"{path.name}"
            elif is_node:
                if (path / "dist" / "index.js").exists():
                    entry_point = "node dist/index.js"
                elif (path / "index.js").exists():
                    entry_point = "node index.js"

        # Auto-detect router module for subprograms
        if module_type == "subprogram" and not router_module:
            if (path / "gateway" / "router.py").exists():
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
        """Scan for subprograms.

        Returns:
            DiscoveryResult with discovered subprograms
        """
        modules = self.scan_directory("subprograms", "subprogram")
        return DiscoveryResult(modules=modules)


class ChannelScanner(BaseScanner):
    """Scanner for discovering channels."""

    def scan(self) -> DiscoveryResult:
        """Scan for channels.

        Returns:
            DiscoveryResult with discovered channels
        """
        modules = self.scan_directory("channels", "channel")
        return DiscoveryResult(modules=modules)


def discover_all(base_path: Optional[Path] = None) -> tuple[DiscoveryResult, DiscoveryResult]:
    """Discover all subprograms and channels.

    Args:
        base_path: Base path to scan from

    Returns:
        Tuple of (subprograms_result, channels_result)
    """
    subprogram_scanner = SubprogramScanner(base_path)
    channel_scanner = ChannelScanner(base_path)

    return subprogram_scanner.scan(), channel_scanner.scan()
