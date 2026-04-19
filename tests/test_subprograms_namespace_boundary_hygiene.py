from __future__ import annotations

import ast
from pathlib import Path

import subprograms.document_parser
import subprograms.document_parser.gateway
import subprograms.knowledge_base
import subprograms.knowledge_base.gateway
import subprograms.memory_manager
import subprograms.memory_manager.gateway


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SCRIPT_ROOT = REPO_ROOT / "scripts"


def test_subprogram_package_roots_are_marker_only() -> None:
    assert subprograms.document_parser.__all__ == []
    assert subprograms.document_parser.gateway.__all__ == []
    assert subprograms.knowledge_base.__all__ == []
    assert subprograms.knowledge_base.gateway.__all__ == []
    assert subprograms.memory_manager.__all__ == []
    assert subprograms.memory_manager.gateway.__all__ == []


def test_active_source_tree_does_not_import_subprogram_package_roots() -> None:
    violations: list[str] = []
    disallowed = {
        "subprograms.document_parser",
        "subprograms.document_parser.gateway",
        "subprograms.knowledge_base",
        "subprograms.knowledge_base.gateway",
        "subprograms.memory_manager",
        "subprograms.memory_manager.gateway",
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
                                f"{relative}:{node.lineno}: forbidden subprogram package-root import {alias.name}"
                            )
                elif isinstance(node, ast.ImportFrom):
                    if (node.module or "") in disallowed:
                        violations.append(
                            f"{relative}:{node.lineno}: forbidden subprogram package-root import from {node.module}"
                        )

    assert violations == [], (
        "Active source and script files must import subprogram owners directly:\n"
        + "\n".join(violations)
    )
