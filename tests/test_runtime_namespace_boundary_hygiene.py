from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
RUNTIME_ROOT = SRC_ROOT / "mini_agent" / "runtime"


def _runtime_wrapper_stems() -> set[str]:
    wrapper_stems: set[str] = set()
    for path in sorted(RUNTIME_ROOT.glob("*.py")):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "Compatibility re-export for" in text:
            wrapper_stems.add(path.stem)
    return wrapper_stems


FORBIDDEN_WRAPPER_STEMS = _runtime_wrapper_stems()
FORBIDDEN_MODULES = {
    f"mini_agent.runtime.{stem}"
    for stem in FORBIDDEN_WRAPPER_STEMS
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
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "mini_agent.runtime":
                    violations.append(
                        f"{relative}:{node.lineno}: forbidden runtime package-root import {alias.name}"
                    )
                if alias.name in FORBIDDEN_MODULES:
                    violations.append(
                        f"{relative}:{node.lineno}: forbidden runtime compatibility import {alias.name}"
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported_names = {alias.name for alias in node.names}
            if module == "mini_agent.runtime":
                violations.append(
                    f"{relative}:{node.lineno}: forbidden runtime package-root import from {module}"
                )
                continue
            if module in FORBIDDEN_MODULES:
                violations.append(
                    f"{relative}:{node.lineno}: forbidden runtime compatibility import from {module}"
                )
                continue
    return violations


def test_active_source_tree_does_not_import_root_runtime_compatibility_wrappers() -> None:
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        violations.extend(_collect_violations(path))

    assert violations == [], (
        "Active source files must not depend on root runtime compatibility wrappers:\n"
        + "\n".join(violations)
    )
