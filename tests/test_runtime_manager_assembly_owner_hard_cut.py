from __future__ import annotations

import ast
from pathlib import Path

from mini_agent.runtime.main_agent_runtime_manager import MainAgentRuntimeManager
from mini_agent.runtime.orchestration.main_agent_runtime_assembly_mixin import (
    MainAgentRuntimeAssemblyMixin,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
MANAGER_PATH = REPO_ROOT / "src/mini_agent/runtime/main_agent_runtime_manager.py"
MIXIN_PATH = REPO_ROOT / "src/mini_agent/runtime/orchestration/main_agent_runtime_assembly_mixin.py"
EXTRACTED_ASSEMBLY_METHODS = {
    "_initialize_runtime_core",
    "_initialize_runtime_support_services",
    "_initialize_session_model_services",
    "_initialize_session_runtime_services",
    "_initialize_session_boundary_services",
    "_resolve_default_session_workspace",
    "_billable_session_count",
}


def _class_method_names(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            names: set[str] = set()
            for body_item in node.body:
                if isinstance(body_item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.add(body_item.name)
            return names
    raise AssertionError(f"class {class_name} not found in {path}")


def test_runtime_manager_assembly_owner_is_extracted_to_orchestration_module() -> None:
    assert MainAgentRuntimeAssemblyMixin.__module__ == (
        "mini_agent.runtime.orchestration.main_agent_runtime_assembly_mixin"
    )
    assert MainAgentRuntimeManager.__mro__[2] is MainAgentRuntimeAssemblyMixin


def test_runtime_manager_root_shell_no_longer_physically_owns_extracted_assembly_methods() -> None:
    manager_methods = _class_method_names(MANAGER_PATH, "MainAgentRuntimeManager")
    leaked = sorted(EXTRACTED_ASSEMBLY_METHODS & manager_methods)
    assert leaked == [], (
        "Runtime manager root shell must not re-own extracted assembly methods:\n"
        + "\n".join(leaked)
    )


def test_runtime_manager_assembly_mixin_owns_extracted_method_surface() -> None:
    mixin_methods = _class_method_names(MIXIN_PATH, "MainAgentRuntimeAssemblyMixin")
    missing = sorted(EXTRACTED_ASSEMBLY_METHODS - mixin_methods)
    assert missing == [], (
        "Runtime assembly mixin must own the extracted method surface:\n"
        + "\n".join(missing)
    )
