from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from mini_agent.agent_core.engine import Agent
from mini_agent.agent_core.execution.tools import ToolBuilder, ToolKind
from mini_agent.config import AgentConfig, Config, LLMConfig, SecurityConfig, ToolsConfig
from mini_agent.rag import HybridSearchStore
from mini_agent.runtime.tooling import add_workspace_tools, resolve_runtime_policy
from mini_agent.tools.knowledge_base import KnowledgeBaseQueryTool


def _make_config(security: SecurityConfig | None = None) -> Config:
    return Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(),
        tools=ToolsConfig(enable_mcp=False, enable_skills=False),
        security=security or SecurityConfig(),
    )


@pytest.mark.asyncio
async def test_knowledge_base_query_tool_returns_ranked_hits(tmp_path: Path) -> None:
    store_path = tmp_path / "rag" / "light_hybrid_store.json"
    store = HybridSearchStore(store_path)
    store.ingest_text(
        document_name="routing.md",
        content="Runtime routing falls back cleanly and records provider health.",
        knowledge_base_id="docs",
    )

    tool = KnowledgeBaseQueryTool(
        workspace_dir=tmp_path,
        store_path=store_path,
    )
    result = await tool.execute(query="provider health fallback", knowledge_base_id="docs", top_k=3)

    assert result.success is True
    assert "Knowledge base results:" in result.content
    assert "routing.md" in result.content
    assert "provider health" in result.content
    assert "knowledge_base_id: docs" in result.content


@pytest.mark.asyncio
async def test_knowledge_base_query_tool_reports_missing_store(tmp_path: Path) -> None:
    store_path = tmp_path / "rag" / "missing.json"
    tool = KnowledgeBaseQueryTool(
        workspace_dir=tmp_path,
        store_path=store_path,
    )

    result = await tool.execute(query="anything")

    assert result.success is True
    assert "Knowledge base is not available yet." in result.content
    assert str(store_path.resolve()) in result.content


def test_knowledge_base_query_tool_is_registered_as_read_only_search(tmp_path: Path) -> None:
    declarative = ToolBuilder.from_tool(KnowledgeBaseQueryTool(workspace_dir=tmp_path))

    assert declarative.name == "knowledge_base_query"
    assert declarative.attributes.kind == ToolKind.SEARCH
    assert declarative.attributes.is_read_only is True
    assert declarative.attributes.concurrency_safe is True


def test_workspace_tooling_includes_knowledge_base_query_tool(tmp_path: Path) -> None:
    config = _make_config()
    engine = resolve_runtime_policy(config)

    tools: list[object] = []
    add_workspace_tools(
        tools,
        config,
        tmp_path,
        policy_engine=engine,
    )

    assert any(getattr(tool, "name", None) == "knowledge_base_query" for tool in tools)


def test_knowledge_base_query_tool_description_emphasizes_doc_grounding(tmp_path: Path) -> None:
    tool = KnowledgeBaseQueryTool(workspace_dir=tmp_path)

    assert "README" in tool.description
    assert "API" in tool.description
    assert "concrete query terms" in tool.description
    assert "concrete nouns" in tool.parameters["properties"]["query"]["description"]


def test_workspace_tooling_skips_knowledge_base_query_when_disabled(tmp_path: Path) -> None:
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(),
        tools=ToolsConfig(
            enable_mcp=False,
            enable_skills=False,
            enable_knowledge_base=False,
        ),
        security=SecurityConfig(),
    )
    engine = resolve_runtime_policy(config)

    tools: list[object] = []
    add_workspace_tools(
        tools,
        config,
        tmp_path,
        policy_engine=engine,
    )

    assert all(getattr(tool, "name", None) != "knowledge_base_query" for tool in tools)


def test_agent_can_toggle_knowledge_base_tool_at_runtime(tmp_path: Path) -> None:
    tool = KnowledgeBaseQueryTool(workspace_dir=tmp_path)
    agent = Agent(
        llm_client=SimpleNamespace(model="gpt-test"),
        system_prompt="sys",
        tools=[tool],
        workspace_dir=str(tmp_path),
        console_output=False,
    )

    assert agent.knowledge_base_enabled() is True
    assert "knowledge_base_query" in agent.declarative_tools

    assert agent.set_knowledge_base_enabled(False) is False
    assert agent.knowledge_base_enabled() is False
    assert "knowledge_base_query" not in agent.tools
    assert "knowledge_base_query" not in agent.declarative_tools

    assert agent.set_knowledge_base_enabled(True) is True
    assert agent.knowledge_base_enabled() is True
    assert "knowledge_base_query" in agent.tools
    assert "knowledge_base_query" in agent.declarative_tools


def test_agent_can_lazily_enable_knowledge_base_tool_when_not_preloaded(tmp_path: Path) -> None:
    agent = Agent(
        llm_client=SimpleNamespace(model="gpt-test"),
        system_prompt="sys",
        tools=[],
        workspace_dir=str(tmp_path),
        console_output=False,
    )

    assert agent.knowledge_base_enabled() is False
    assert agent.set_knowledge_base_enabled(True) is True
    assert "knowledge_base_query" in agent.tools
