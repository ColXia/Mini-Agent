from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
DELETED_PATHS = {
    Path("src/mini_agent/application/main_agent_surface_service.py"),
    Path("src/mini_agent/application/surface_service_assembly.py"),
    Path("src/mini_agent/application/facades/main_agent_surface_service.py"),
    Path("src/mini_agent/application/facades/surface_service_assembly.py"),
}
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


def _collect_violations(path: Path) -> list[str]:
    relative = path.relative_to(REPO_ROOT)
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
                violations.append(f"{relative}:{node.lineno}: forbidden deleted surface import from {module}")
                continue
            if module in FORBIDDEN_PACKAGE_MODULES and imported_names & FORBIDDEN_IMPORT_NAMES:
                bad = ", ".join(sorted(imported_names & FORBIDDEN_IMPORT_NAMES))
                violations.append(
                    f"{relative}:{node.lineno}: forbidden deleted surface package import ({bad}) from {module}"
                )
    return violations


def test_deleted_surface_entrypoint_files_are_absent() -> None:
    for relative_path in DELETED_PATHS:
        assert not (REPO_ROOT / relative_path).exists(), f"{relative_path} should be removed"


def test_active_source_tree_does_not_import_deleted_surface_entrypoints() -> None:
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        violations.extend(_collect_violations(path))

    assert violations == [], (
        "Active source files must not depend on deleted surface entrypoints:\n" + "\n".join(violations)
    )
