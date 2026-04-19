from __future__ import annotations

import ast
from pathlib import Path

import mini_agent.dev as dev_pkg


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SCRIPT_ROOT = REPO_ROOT / "scripts"


def test_dev_package_root_is_marker_only() -> None:
    assert dev_pkg.__all__ == []


def test_active_source_tree_does_not_import_dev_package_root() -> None:
    violations: list[str] = []
    roots = [SRC_ROOT]
    if SCRIPT_ROOT.exists():
        roots.append(SCRIPT_ROOT)
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            relative = path.relative_to(REPO_ROOT)
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(relative))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "mini_agent.dev":
                            violations.append(
                                f"{relative}:{node.lineno}: forbidden dev package-root import {alias.name}"
                            )
                elif isinstance(node, ast.ImportFrom):
                    if (node.module or "") == "mini_agent.dev":
                        violations.append(
                            f"{relative}:{node.lineno}: forbidden dev package-root import from {node.module}"
                        )
                    elif (
                        relative.parent == Path("src/mini_agent")
                        and node.level == 1
                        and (node.module or "") == "dev"
                    ):
                        violations.append(
                            f"{relative}:{node.lineno}: forbidden dev package-root import from {node.module}"
                        )

    assert violations == [], (
        "Active source and script files must import dev owners directly:\n"
        + "\n".join(violations)
    )
