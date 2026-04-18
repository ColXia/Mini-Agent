from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
ALLOWED_PATHS = {
    Path("src/mini_agent/application/ports/session_agent_runtime_port.py"),
}
ALLOWED_PARENT_PREFIXES = (
    Path("src/mini_agent/application/legacy"),
)
FORBIDDEN_MODULES = {
    "legacy.session_agent_runtime_port",
    "mini_agent.application.legacy.session_agent_runtime_port",
}


def _is_allowed(path: Path) -> bool:
    relative = path.relative_to(REPO_ROOT)
    if relative in ALLOWED_PATHS:
        return True
    return any(relative.is_relative_to(prefix) for prefix in ALLOWED_PARENT_PREFIXES)


def _collect_violations(path: Path) -> list[str]:
    if _is_allowed(path):
        return []

    relative = path.relative_to(REPO_ROOT)
    try:
        source = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        source = path.read_text(encoding="utf-8")

    tree = ast.parse(source, filename=str(relative))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "") in FORBIDDEN_MODULES:
            violations.append(
                f"{relative}:{node.lineno}: forbidden active import from {node.module}"
            )
    return violations


def test_active_source_tree_does_not_import_legacy_session_agent_runtime_port() -> None:
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        violations.extend(_collect_violations(path))

    assert violations == [], (
        "Active source files must not depend on the legacy session agent runtime port module:\n"
        + "\n".join(violations)
    )
