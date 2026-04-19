from __future__ import annotations

from types import SimpleNamespace

from mini_agent.agent_core.engine import Agent
from mini_agent.agent_core.execution.permissions.approval import ApprovalEngine
from mini_agent.agent_core.execution.permissions.policy import PermissionPolicy
from mini_agent.agent_core.runtime_bindings import (
    AgentRuntimeServices,
    get_agent_runtime_services,
    override_agent_tool_approval_handler,
    set_agent_runtime_services,
    set_agent_tool_approval_handler,
)


class _UnusedLLM:
    async def generate(self, messages, tools=None):  # noqa: ANN001,ARG002
        raise AssertionError("LLM should not be called during runtime binding tests.")


class _RuntimeServicesOnlyCarrier:
    __slots__ = ("runtime_services",)

    def __init__(self) -> None:
        self.runtime_services = AgentRuntimeServices()


class _LegacyCarrier:
    pass


def test_get_agent_runtime_services_reads_contract_only_carrier() -> None:
    policy_engine = SimpleNamespace(name="policy")
    carrier = _RuntimeServicesOnlyCarrier()
    carrier.runtime_services = AgentRuntimeServices(runtime_policy_engine=policy_engine)

    services = get_agent_runtime_services(carrier)

    assert services.runtime_policy_engine is policy_engine


def test_set_agent_runtime_services_updates_contract_only_carrier() -> None:
    carrier = _RuntimeServicesOnlyCarrier()
    policy_engine = SimpleNamespace(name="policy")
    approval_engine = ApprovalEngine(PermissionPolicy.strict_policy())
    sandbox_manager = SimpleNamespace(name="sandbox")

    updated = set_agent_runtime_services(
        carrier,
        runtime_policy_engine=policy_engine,
        approval_engine=approval_engine,
        sandbox_manager=sandbox_manager,
    )

    assert updated == AgentRuntimeServices(
        runtime_policy_engine=policy_engine,
        approval_engine=approval_engine,
        sandbox_manager=sandbox_manager,
        tool_approval_handler=None,
    )
    assert carrier.runtime_services == updated


def test_set_agent_runtime_services_preserves_legacy_attrs_and_installs_contract() -> None:
    carrier = _LegacyCarrier()
    policy_engine = SimpleNamespace(name="policy")
    approval_engine = ApprovalEngine(PermissionPolicy.strict_policy())
    sandbox_manager = SimpleNamespace(name="sandbox")

    updated = set_agent_runtime_services(
        carrier,
        runtime_policy_engine=policy_engine,
        approval_engine=approval_engine,
        sandbox_manager=sandbox_manager,
    )

    assert carrier.runtime_policy_engine is policy_engine
    assert carrier.approval_engine is approval_engine
    assert carrier.sandbox_manager is sandbox_manager
    assert carrier.runtime_services == updated


def test_override_agent_tool_approval_handler_restores_contract_handler() -> None:
    carrier = _RuntimeServicesOnlyCarrier()

    def first_handler(_request):  # noqa: ANN001
        return True

    def second_handler(_request):  # noqa: ANN001
        return False

    set_agent_tool_approval_handler(carrier, first_handler)

    with override_agent_tool_approval_handler(carrier, second_handler) as previous:
        assert previous is first_handler
        assert carrier.runtime_services.tool_approval_handler is second_handler

    assert carrier.runtime_services.tool_approval_handler is first_handler


def test_agent_runtime_services_property_keeps_engine_runtime_state_in_sync(tmp_path) -> None:
    approval_engine = ApprovalEngine(PermissionPolicy.strict_policy())
    policy_engine = SimpleNamespace(name="policy")
    sandbox_manager = SimpleNamespace(name="sandbox")

    def initial_handler(_request):  # noqa: ANN001
        return True

    agent = Agent(
        llm_client=_UnusedLLM(),
        system_prompt="System prompt",
        tools=[],
        workspace_dir=str(tmp_path),
        console_output=False,
        approval_engine=approval_engine,
        tool_approval_handler=initial_handler,
        runtime_policy_engine=policy_engine,
        sandbox_manager=sandbox_manager,
    )

    assert agent.runtime_services == AgentRuntimeServices(
        runtime_policy_engine=policy_engine,
        approval_engine=approval_engine,
        sandbox_manager=sandbox_manager,
        tool_approval_handler=initial_handler,
    )
    assert agent.runtime_policy_engine is policy_engine
    assert agent.approval_engine is approval_engine
    assert agent.sandbox_manager is sandbox_manager
    assert agent.tool_approval_handler is initial_handler

    def updated_handler(_request):  # noqa: ANN001
        return False

    replacement = AgentRuntimeServices(
        runtime_policy_engine=SimpleNamespace(name="replacement-policy"),
        approval_engine=None,
        sandbox_manager=SimpleNamespace(name="replacement-sandbox"),
        tool_approval_handler=updated_handler,
    )
    agent.runtime_services = replacement

    assert agent.runtime_services is replacement
    assert agent.runtime_policy_engine is replacement.runtime_policy_engine
    assert agent.approval_engine is None
    assert agent.sandbox_manager is replacement.sandbox_manager
    assert agent.tool_approval_handler is updated_handler
