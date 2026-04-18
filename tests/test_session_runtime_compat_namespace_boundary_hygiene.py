from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
ALLOWED_PATHS = {
    Path("src/mini_agent/application/session_runtime_compat.py"),
}
ALLOWED_PARENT_PREFIXES = (
    Path("src/mini_agent/application/legacy"),
)
FORBIDDEN_MODULE = "mini_agent.application.session_runtime_compat"


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
        if isinstance(node, ast.ImportFrom) and (node.module or "") == FORBIDDEN_MODULE:
            violations.append(
                f"{relative}:{node.lineno}: forbidden active import from {FORBIDDEN_MODULE}"
            )
    return violations


def test_active_source_tree_does_not_import_root_session_runtime_compat_wrapper() -> None:
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        violations.extend(_collect_violations(path))

    assert violations == [], (
        "Active source files must not depend on the root session_runtime_compat wrapper:\n"
        + "\n".join(violations)
    )
