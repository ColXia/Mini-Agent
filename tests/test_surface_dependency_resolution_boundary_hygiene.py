from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
DELETED_PATH = Path("src/mini_agent/application/facades/surface_dependency_resolution.py")
FORBIDDEN_MODULES = {
    "mini_agent.application.facades.surface_dependency_resolution",
    "surface_dependency_resolution",
}
FORBIDDEN_IMPORT_NAMES = {
    "LegacySurfaceRunControlAdapter",
    "resolve_surface_agent_entry_service",
    "resolve_surface_model_entry_service",
    "resolve_surface_run_control_service",
    "resolve_surface_session_task_service",
    "resolve_surface_workspace_entry_service",
}
FORBIDDEN_PACKAGE_MODULES = {
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
                violations.append(
                    f"{relative}:{node.lineno}: forbidden deleted surface dependency-resolution import from {module}"
                )
                continue
            if module in FORBIDDEN_PACKAGE_MODULES and imported_names & FORBIDDEN_IMPORT_NAMES:
                bad = ", ".join(sorted(imported_names & FORBIDDEN_IMPORT_NAMES))
                violations.append(
                    f"{relative}:{node.lineno}: forbidden deleted surface dependency-resolution package import ({bad}) from {module}"
                )
    return violations


def test_deleted_surface_dependency_resolution_wrapper_is_absent() -> None:
    assert not (REPO_ROOT / DELETED_PATH).exists()


def test_active_source_tree_does_not_import_deleted_surface_dependency_resolution_wrapper() -> None:
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        violations.extend(_collect_violations(path))

    assert violations == [], (
        "Active source files must not depend on the deleted surface dependency-resolution wrapper:\n"
        + "\n".join(violations)
    )
