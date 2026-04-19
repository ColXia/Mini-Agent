from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
ALLOWED_PATHS: set[Path] = set()
ALLOWED_PARENT_PREFIXES = (
    Path("src/mini_agent/application/legacy"),
)


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
        if not isinstance(node, ast.ImportFrom):
            continue
        module = node.module or ""
        imported_names = {alias.name for alias in node.names}
        if module.endswith("session_runtime_port") and "SessionRuntimePort" in imported_names:
            violations.append(f"{relative}:{node.lineno}: forbidden active import of SessionRuntimePort from {module}")
            continue
        if module in {"mini_agent.application", "mini_agent.application.ports"} and "SessionRuntimePort" in imported_names:
            violations.append(f"{relative}:{node.lineno}: forbidden active package import of SessionRuntimePort from {module}")
    return violations


def test_active_source_tree_does_not_import_broad_session_runtime_port_outside_compatibility_layers() -> None:
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        violations.extend(_collect_violations(path))

    assert violations == [], (
        "Active source files must resolve narrower runtime support protocols instead of importing "
        "SessionRuntimePort directly:\n" + "\n".join(violations)
    )


def test_stage_hard_cut_deletes_root_session_runtime_wrapper() -> None:
    assert not (REPO_ROOT / "src/mini_agent/application/session_runtime_port.py").exists()
