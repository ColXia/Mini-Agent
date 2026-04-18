from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
DELETED_PATH = Path("src/mini_agent/application/session_runtime_compat.py")
FORBIDDEN_MODULES = {
    "mini_agent.application.session_runtime_compat",
    "session_runtime_compat",
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
        if isinstance(node, ast.ImportFrom) and (node.module or "") in FORBIDDEN_MODULES:
            violations.append(f"{relative}:{node.lineno}: forbidden deleted compat import from {node.module}")
    return violations


def test_deleted_root_session_runtime_compat_wrapper_is_absent() -> None:
    assert not (REPO_ROOT / DELETED_PATH).exists()


def test_active_source_tree_does_not_import_deleted_root_session_runtime_compat_wrapper() -> None:
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        violations.extend(_collect_violations(path))

    assert violations == [], (
        "Active source files must not depend on the deleted root session_runtime_compat wrapper:\n"
        + "\n".join(violations)
    )
