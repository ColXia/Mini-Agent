from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
ALLOWED_PARENT_PREFIXES = (
    Path("src/mini_agent/application/legacy"),
)
ALLOWED_PATHS = {
    Path("src/mini_agent/application/__init__.py"),
    Path("src/mini_agent/application/user_service_assembly.py"),
    Path("src/mini_agent/application/user_services/__init__.py"),
    Path("src/mini_agent/application/user_services/service_assembly.py"),
}
FORBIDDEN_CALL = "assemble_runtime_backed_user_services"
FORBIDDEN_PACKAGE_MODULES = {
    "mini_agent.application",
    "mini_agent.application.user_services",
}


def _is_allowed(path: Path) -> bool:
    relative = path.relative_to(REPO_ROOT)
    if relative in ALLOWED_PATHS:
        return True
    return any(relative.is_relative_to(prefix) for prefix in ALLOWED_PARENT_PREFIXES)


def _read_source(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8")


def _collect_violations(path: Path) -> list[str]:
    if _is_allowed(path):
        return []

    relative = path.relative_to(REPO_ROOT)
    tree = ast.parse(_read_source(path), filename=str(relative))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported_names = {alias.name for alias in node.names}
            if module in FORBIDDEN_PACKAGE_MODULES and FORBIDDEN_CALL in imported_names:
                violations.append(
                    f"{relative}:{node.lineno}: forbidden active package import of {FORBIDDEN_CALL} from {module}"
                )
                continue
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == FORBIDDEN_CALL:
            violations.append(
                f"{relative}:{node.lineno}: forbidden active call to {FORBIDDEN_CALL}()"
            )
            continue
        if isinstance(func, ast.Attribute) and func.attr == FORBIDDEN_CALL:
            violations.append(
                f"{relative}:{node.lineno}: forbidden active call to {FORBIDDEN_CALL}()"
            )
    return violations


def test_active_source_tree_uses_typed_user_service_assembly_instead_of_runtime_backed_shortcut() -> None:
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        violations.extend(_collect_violations(path))

    assert violations == [], (
        "Active source files must resolve typed runtime ports before assembling user services:\n"
        + "\n".join(violations)
    )
