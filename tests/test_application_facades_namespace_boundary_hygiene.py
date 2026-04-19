from __future__ import annotations

import ast
import mini_agent.application.facades as application_facades_pkg
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SCRIPT_ROOT = REPO_ROOT / "scripts"


def test_application_facades_package_root_is_marker_only() -> None:
    assert application_facades_pkg.__all__ == []


def test_active_source_tree_does_not_import_application_facades_package_root() -> None:
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
                        if alias.name == "mini_agent.application.facades":
                            violations.append(
                                f"{relative}:{node.lineno}: forbidden application.facades package-root import {alias.name}"
                            )
                elif isinstance(node, ast.ImportFrom):
                    if (node.module or "") in {"mini_agent.application.facades", "facades"}:
                        violations.append(
                            f"{relative}:{node.lineno}: forbidden application.facades package-root import from {node.module}"
                        )

    assert violations == [], (
        "Active source and script files must import application facade owners directly:\n"
        + "\n".join(violations)
    )
