from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
ALLOWED_PARENT_PREFIXES = (
    Path("src/mini_agent/application/legacy"),
)
FORBIDDEN_AGENT_METHODS = {
    "control_session",
    "update_session_context",
    "manage_session_memory",
    "manage_session_skills",
    "update_session_runtime_policy",
}
FORBIDDEN_MODEL_METHODS = {
    "update_session_model_selection",
}
AGENT_SERVICE_ATTRS = {"agent_service", "_agent_service"}
MODEL_SERVICE_ATTRS = {"model_service", "_model_service"}
AGENT_SERVICE_FACTORIES = {"_require_agent_service", "get_agent_service"}
MODEL_SERVICE_FACTORIES = {"_require_model_service", "get_model_service"}


def _is_allowed(path: Path) -> bool:
    relative = path.relative_to(REPO_ROOT)
    return any(relative.is_relative_to(prefix) for prefix in ALLOWED_PARENT_PREFIXES)


def _read_source(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8")


def _matches_service_reference(
    node: ast.expr,
    *,
    attr_names: set[str],
    factory_names: set[str],
) -> bool:
    if isinstance(node, ast.Name):
        return node.id in attr_names
    if isinstance(node, ast.Attribute):
        return node.attr in attr_names
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name):
            return func.id in factory_names
        if isinstance(func, ast.Attribute):
            return func.attr in factory_names
    return False


def _collect_violations(path: Path) -> list[str]:
    if _is_allowed(path):
        return []

    relative = path.relative_to(REPO_ROOT)
    tree = ast.parse(_read_source(path), filename=str(relative))
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue

        method_name = node.func.attr
        target = node.func.value

        if method_name in FORBIDDEN_AGENT_METHODS and _matches_service_reference(
            target,
            attr_names=AGENT_SERVICE_ATTRS,
            factory_names=AGENT_SERVICE_FACTORIES,
        ):
            violations.append(
                f"{relative}:{node.lineno}: forbidden active call to AgentUserService.{method_name}()"
            )
            continue

        if method_name in FORBIDDEN_MODEL_METHODS and _matches_service_reference(
            target,
            attr_names=MODEL_SERVICE_ATTRS,
            factory_names=MODEL_SERVICE_FACTORIES,
        ):
            violations.append(
                f"{relative}:{node.lineno}: forbidden active call to ModelUserService.{method_name}()"
            )

    return violations


def test_active_source_tree_does_not_route_session_compat_actions_through_agent_or_model_user_services() -> None:
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        violations.extend(_collect_violations(path))

    assert violations == [], (
        "Active source files must route session-scoped actions through SessionTaskService instead of "
        "AgentUserService/ModelUserService compatibility shims:\n" + "\n".join(violations)
    )
