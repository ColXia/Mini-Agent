from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"


def test_active_source_tree_does_not_import_command_package_root() -> None:
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        relative = path.relative_to(REPO_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(relative))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "mini_agent.commands":
                        violations.append(
                            f"{relative}:{node.lineno}: forbidden command package-root import {alias.name}"
                        )
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "") in {"mini_agent.commands", "commands"}:
                    violations.append(
                        f"{relative}:{node.lineno}: forbidden command package-root import from {node.module}"
                    )

    assert violations == [], (
        "Active source files must import command owners directly:\n"
        + "\n".join(violations)
    )
