from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
FORBIDDEN_MODULES = {
    "mini_agent.application.main_agent_surface_service",
    "mini_agent.application.surface_service_assembly",
    "mini_agent.application.facades.main_agent_surface_service",
    "mini_agent.application.facades.surface_service_assembly",
}
FORBIDDEN_ROOT_MODULES = {
    "mini_agent.application",
    "mini_agent.application.facades",
}
FORBIDDEN_IMPORT_NAMES = {
    "MainAgentSurfaceService",
    "MainAgentSurfaceAssembly",
    "assemble_main_agent_surface_service",
    "assemble_runtime_backed_main_agent_surface_service",
    "build_main_agent_surface_service",
    "build_runtime_backed_main_agent_surface_service",
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
        if not isinstance(node, ast.ImportFrom):
            continue
        module = node.module or ""
        imported_names = {alias.name for alias in node.names}
        if module in FORBIDDEN_MODULES:
            violations.append(f"{relative}:{node.lineno}: forbidden deleted surface import from {module}")
            continue
        if module in FORBIDDEN_ROOT_MODULES:
            violations.append(f"{relative}:{node.lineno}: scripts must import concrete application owners, not {module}")
            continue
        if imported_names & FORBIDDEN_IMPORT_NAMES:
            bad = ", ".join(sorted(imported_names & FORBIDDEN_IMPORT_NAMES))
            violations.append(
                f"{relative}:{node.lineno}: forbidden deleted surface package import ({bad}) from {module}"
            )
    return violations


def test_scripts_do_not_import_deleted_surface_entrypoints() -> None:
    violations: list[str] = []
    for path in sorted(SCRIPTS_ROOT.rglob("*.py")):
        violations.extend(_collect_violations(path))

    assert violations == [], (
        "Scripts must not depend on deleted application surface entrypoints:\n" + "\n".join(violations)
    )
