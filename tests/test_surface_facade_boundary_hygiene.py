from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
ALLOWED_PATHS = {
    Path("src/mini_agent/application/__init__.py"),
    Path("src/mini_agent/application/main_agent_surface_service.py"),
    Path("src/mini_agent/application/surface_service_assembly.py"),
    Path("src/mini_agent/application/facades/__init__.py"),
    Path("src/mini_agent/application/facades/main_agent_surface_service.py"),
    Path("src/mini_agent/application/facades/surface_service_assembly.py"),
}
ALLOWED_PARENT_PREFIXES = (
    Path("src/mini_agent/application/legacy"),
)
FORBIDDEN_MODULES = {
    "mini_agent.application.main_agent_surface_service",
    "mini_agent.application.surface_service_assembly",
    "mini_agent.application.facades.main_agent_surface_service",
    "mini_agent.application.facades.surface_service_assembly",
}
FORBIDDEN_IMPORT_NAMES = {
    "MainAgentSurfaceService",
    "MainAgentSurfaceAssembly",
    "assemble_main_agent_surface_service",
    "assemble_runtime_backed_main_agent_surface_service",
    "build_main_agent_surface_service",
    "build_runtime_backed_main_agent_surface_service",
}
FORBIDDEN_PACKAGE_MODULES = {
    "mini_agent.application",
    "mini_agent.application.facades",
}


def _is_allowed(path: Path) -> bool:
    relative = path.relative_to(REPO_ROOT)
    if relative in ALLOWED_PATHS:
        return True
    return any(relative.is_relative_to(prefix) for prefix in ALLOWED_PARENT_PREFIXES)


def _collect_violations(path: Path) -> list[str]:
    relative = path.relative_to(REPO_ROOT)
    if _is_allowed(path):
        return []

    try:
        source = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        source = path.read_text(encoding="utf-8")

    tree = ast.parse(source, filename=str(relative))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported_names = {alias.name for alias in node.names}
            if module in FORBIDDEN_MODULES:
                violations.append(
                    f"{relative}:{node.lineno}: forbidden legacy surface import from {module}"
                )
                continue
            if module in FORBIDDEN_PACKAGE_MODULES and imported_names & FORBIDDEN_IMPORT_NAMES:
                bad = ", ".join(sorted(imported_names & FORBIDDEN_IMPORT_NAMES))
                violations.append(
                    f"{relative}:{node.lineno}: forbidden legacy surface package import ({bad}) from {module}"
                )
    return violations


def test_active_source_tree_does_not_import_legacy_surface_facade_entrypoints() -> None:
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        violations.extend(_collect_violations(path))

    assert violations == [], (
        "Active source files must not depend on legacy surface facade entrypoints:\n"
        + "\n".join(violations)
    )
