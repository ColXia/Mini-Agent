from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"


def test_active_source_tree_does_not_import_tools_package_root() -> None:
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        relative = path.relative_to(REPO_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(relative))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "mini_agent.tools":
                        violations.append(
                            f"{relative}:{node.lineno}: forbidden tools package-root import {alias.name}"
                        )
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "") in {"mini_agent.tools", "tools"}:
                    violations.append(
                        f"{relative}:{node.lineno}: forbidden tools package-root import from {node.module}"
                    )

    assert violations == [], (
        "Active source files must import tools directly from owned modules:\n"
        + "\n".join(violations)
    )
