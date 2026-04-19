from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO_ROOT / "src/mini_agent/commands/catalog.py"
METADATA_PATH = REPO_ROOT / "src/mini_agent/commands/metadata.py"
COMPLETIONS_PATH = REPO_ROOT / "src/mini_agent/commands/completions.py"
MOVED_OUT_OF_CATALOG_FUNCTIONS = {
    "build_command_usage_text",
    "build_command_example_text",
    "build_command_help_text",
    "build_unknown_action_text",
    "command_action_candidates",
    "suggest_command_action",
    "command_completion_tokens",
}
METADATA_OWNER_FUNCTIONS = {
    "build_command_usage_text",
    "build_command_example_text",
    "build_command_help_text",
    "build_unknown_action_text",
    "command_action_candidates",
    "suggest_command_action",
}
COMPLETIONS_OWNER_FUNCTIONS = {
    "command_completion_tokens",
    "suggest_command_name",
}


def _module_function_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            names.add(node.name)
    return names


def test_commands_catalog_no_longer_physically_owns_moved_metadata_or_completion_functions() -> None:
    catalog_functions = _module_function_names(CATALOG_PATH)
    leaked = sorted(MOVED_OUT_OF_CATALOG_FUNCTIONS & catalog_functions)
    assert leaked == [], (
        "commands/catalog.py must not re-own moved metadata/completion helpers:\n"
        + "\n".join(leaked)
    )


def test_commands_metadata_module_owns_metadata_surface() -> None:
    metadata_functions = _module_function_names(METADATA_PATH)
    missing = sorted(METADATA_OWNER_FUNCTIONS - metadata_functions)
    assert missing == [], (
        "commands/metadata.py must own the moved metadata helpers:\n"
        + "\n".join(missing)
    )


def test_commands_completions_module_owns_completion_surface() -> None:
    completion_functions = _module_function_names(COMPLETIONS_PATH)
    missing = sorted(COMPLETIONS_OWNER_FUNCTIONS - completion_functions)
    assert missing == [], (
        "commands/completions.py must own the moved completion helpers:\n"
        + "\n".join(missing)
    )
