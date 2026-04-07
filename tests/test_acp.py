"""Integration tests for the MiniMax ACP adapter."""

from datetime import datetime, timedelta, timezone

import pytest

from mini_agent.acp import ACPSessionStatus, MiniMaxACPAgent
from mini_agent.config import AgentConfig, Config, LLMConfig, ToolsConfig
from mini_agent.schema import FunctionCall, LLMResponse, ToolCall
from mini_agent.tools.base import Tool, ToolResult


class DummyConn:
    def __init__(self):
        self.updates = []

    async def session_update(self, session_id, update):
        self.updates.append((session_id, update))


class DummyLLM:
    def __init__(self):
        self.calls = 0

    async def generate(self, messages, tools):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content="",
                thinking="calling echo",
                tool_calls=[
                    ToolCall(
                        id="tool1",
                        type="function",
                        function=FunctionCall(name="echo", arguments={"text": "ping"}),
                    )
                ],
                finish_reason="tool",
            )
        return LLMResponse(content="done", thinking=None, tool_calls=None, finish_reason="stop")


class EchoTool(Tool):
    @property
    def name(self):
        return "echo"

    @property
    def description(self):
        return "Echo helper"

    @property
    def parameters(self):
        return {"type": "object", "properties": {"text": {"type": "string"}}}

    async def execute(self, text: str):
        return ToolResult(success=True, content=f"tool:{text}")


@pytest.fixture
def acp_agent(tmp_path):
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=3, workspace_dir=str(tmp_path)),
        tools=ToolsConfig(),
    )
    conn = DummyConn()
    agent = MiniMaxACPAgent(config=config, llm=DummyLLM(), base_tools=[EchoTool()], system_prompt="system")
    agent.on_connect(conn)
    return agent, conn


@pytest.mark.asyncio
async def test_acp_turn_executes_tool(acp_agent):
    agent, conn = acp_agent
    session = await agent.new_session(cwd=None)
    assert agent.get_session_status(session.session_id) == ACPSessionStatus.NEW
    response = await agent.prompt(prompt=[{"text": "hello"}], session_id=session.session_id)
    assert response.stopReason == "end_turn"
    assert agent.get_session_status(session.session_id) == ACPSessionStatus.NEW
    assert any("tool:ping" in str(update) for update in conn.updates)
    await agent.cancel(session_id=session.session_id)
    assert agent.get_session_status(session.session_id) == ACPSessionStatus.CANCELLED
    assert agent._sessions[session.session_id].cancel_requested is True


@pytest.mark.asyncio
async def test_acp_invalid_session(acp_agent):
    agent, _ = acp_agent
    response = await agent.prompt(prompt=[{"text": "?"}], session_id="missing")
    assert response.stopReason == "end_turn"
    assert "missing" in agent._sessions
    assert agent.get_session_status("missing") == ACPSessionStatus.NEW


@pytest.mark.asyncio
async def test_acp_session_expires(acp_agent):
    agent, _ = acp_agent
    session = await agent.new_session(cwd=None)
    state = agent._sessions[session.session_id]
    state.last_activity_at = datetime.now(timezone.utc) - timedelta(hours=2)
    agent._session_ttl_seconds = 1
    agent._expire_sessions()
    assert agent.get_session_status(session.session_id) == ACPSessionStatus.EXPIRED
