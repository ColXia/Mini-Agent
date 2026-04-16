from __future__ import annotations

import asyncio

from mini_agent.agent import Agent as LegacyAgent
from mini_agent.agent import PlannerExecutorHooks as LegacyPlannerExecutorHooks
from mini_agent.agent import ToolApprovalRequest as LegacyToolApprovalRequest
from mini_agent.agent import TurnStopReason as LegacyTurnStopReason
from mini_agent.agent_core.engine import Agent
from mini_agent.agent_core.engine import PlannerExecutorHooks
from mini_agent.agent_core.engine import TurnStopReason
from mini_agent.agent_core.execution import AgentSubmissionLoop
from mini_agent.agent_core.execution import ApprovalEngine
from mini_agent.agent_core.execution import PermissionPolicy
from mini_agent.agent_core.execution.tool_approval import ToolApprovalRequest
from mini_agent.agent_core.context.context_compaction import LayeredContextCompactor
from mini_agent.agent_core.context.turn_context import RuntimeTurnContext
from mini_agent.agent_core.context.turn_context import SkillCatalogTurnContextProvider
from mini_agent.code_agent import AgentSubmissionLoop as LegacyAgentSubmissionLoop
from mini_agent.code_agent import ApprovalEngine as LegacyApprovalEngine
from mini_agent.code_agent import LayeredContextCompactor as LegacyLayeredContextCompactor
from mini_agent.code_agent import PermissionPolicy as LegacyPermissionPolicy
from mini_agent.schema import LLMCompletionResult
from mini_agent.schema import LLMResponse
from mini_agent.schema import LLMStreamEventType
from mini_agent.turn_context import RuntimeTurnContext as LegacyRuntimeTurnContext
from mini_agent.turn_context import SkillCatalogTurnContextProvider as LegacySkillCatalogTurnContextProvider


class _LegacyBufferedLLM:
    async def generate(self, messages, tools=None):  # noqa: ANN001,ARG002
        _ = messages
        return LLMResponse(
            content="compat-result",
            finish_reason="stop",
        )


def test_legacy_agent_surface_reexports_agent_core_runtime() -> None:
    assert LegacyAgent is Agent
    assert LegacyPlannerExecutorHooks is PlannerExecutorHooks
    assert LegacyTurnStopReason is TurnStopReason
    assert LegacyToolApprovalRequest is ToolApprovalRequest


def test_legacy_turn_context_surface_reexports_agent_core_context() -> None:
    assert LegacyRuntimeTurnContext is RuntimeTurnContext
    assert LegacySkillCatalogTurnContextProvider is SkillCatalogTurnContextProvider


def test_legacy_code_agent_surface_reexports_agent_core_execution() -> None:
    assert LegacyAgentSubmissionLoop is AgentSubmissionLoop
    assert LegacyApprovalEngine is ApprovalEngine
    assert LegacyPermissionPolicy is PermissionPolicy
    assert LegacyLayeredContextCompactor is LayeredContextCompactor


def test_llm_response_remains_backward_compatible_completion_result() -> None:
    response = LLMResponse(
        content="hello",
        thinking="trace",
        finish_reason="stop",
    )

    assert isinstance(response, LLMCompletionResult)
    assert response.events[0].type == LLMStreamEventType.MESSAGE_START
    assert response.events[1].type == LLMStreamEventType.THINKING_DELTA
    assert response.events[2].type == LLMStreamEventType.TEXT_DELTA
    assert response.events[-1].type == LLMStreamEventType.MESSAGE_STOP


def test_agent_core_accepts_legacy_buffered_llm_response(tmp_path) -> None:
    agent = Agent(
        llm_client=_LegacyBufferedLLM(),
        system_prompt="compat prompt",
        tools=[],
        workspace_dir=str(tmp_path),
        console_output=False,
    )
    agent.add_user_message("say hi")

    result = asyncio.run(agent.run_turn(start_new_run=False))

    assert result.message == "compat-result"
    assert result.stop_reason is TurnStopReason.END_TURN
