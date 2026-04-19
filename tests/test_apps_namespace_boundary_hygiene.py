from __future__ import annotations

import ast
from pathlib import Path

import apps
import apps.agent_studio_gateway
import apps.desktop_ui


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SCRIPT_ROOT = REPO_ROOT / "scripts"


def test_apps_package_roots_are_marker_only() -> None:
    assert apps.__all__ == []
    assert apps.agent_studio_gateway.__all__ == []
    assert apps.desktop_ui.__all__ == []


def test_active_source_tree_does_not_import_apps_package_roots() -> None:
    violations: list[str] = []
    disallowed = {
        "apps",
        "apps.agent_studio_gateway",
        "apps.desktop_ui",
    }
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
                        if alias.name in disallowed:
                            violations.append(
                                f"{relative}:{node.lineno}: forbidden apps package-root import {alias.name}"
                            )
                elif isinstance(node, ast.ImportFrom):
                    if (node.module or "") in disallowed:
                        violations.append(
                            f"{relative}:{node.lineno}: forbidden apps package-root import from {node.module}"
                        )

    assert violations == [], (
        "Active source and script files must import apps owners directly:\n"
        + "\n".join(violations)
    )
