from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from mini_agent.agent import Agent, TurnStopReason
from mini_agent.logger import AgentLogger
from mini_agent.runtime.tooling import build_turn_context_providers, resolve_workspace_skills_dir
from mini_agent.schema import LLMResponse
from mini_agent.tools.mcp.lifecycle import clear_registered_connections, register_connection
from mini_agent.tools.mcp.naming import mcp_tool_alias
from mini_agent.turn_context import (
    ConsolidatedMemoryTurnContextProvider,
    MCPToolCatalogTurnContextProvider,
    RuntimeRecoveryTurnContextProvider,
    RuntimeTurnContext,
    SessionSearchTurnContextProvider,
    SkillCatalogTurnContextProvider,
    TurnContextItem,
    UserProfileTurnContextProvider,
    WorkspaceMemoryContextProvider,
    context_policy_summary_line,
    curate_turn_context_items,
    format_context_policy_details,
    format_prepared_context_diagnostics,
    format_prepared_turn_context_details,
    prepared_context_diagnostics_summary_line,
    prepared_turn_context_summary_line,
    update_prepared_context_diagnostics,
)


@pytest.fixture(autouse=True)
def _global_memory_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINI_AGENT_GLOBAL_MEMORY_ROOT", str((tmp_path / "global").resolve()))


class _CaptureLLM:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = responses
        self.calls = 0
        self.captured_messages = []

    async def generate(self, messages, tools=None):  # noqa: ANN001,ARG002
        self.captured_messages.append([message.model_copy(deep=True) for message in messages])
        response_index = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        return self._responses[response_index]


class _StaticProvider:
    name = "static"

    async def prepare(self, *, turn_context, agent):  # noqa: ANN001
        _ = agent
        return TurnContextItem(
            source="static",
            title="Injected context",
            content=f"ctx for {turn_context.user_input}",
        )


class _FailingProvider:
    name = "broken"

    async def prepare(self, *, turn_context, agent):  # noqa: ANN001
        _ = (turn_context, agent)
        raise RuntimeError("provider boom")


class _DuplicateWorkspaceProvider:
    name = "workspace_memory"

    async def prepare(self, *, turn_context, agent):  # noqa: ANN001
        _ = (turn_context, agent)
        return TurnContextItem(
            source="workspace_memory",
            title="Relevant workspace memory",
            content="Queue restart guardrails preserve pending approvals.",
        )


class _DuplicateKnowledgeProvider:
    name = "knowledge_base"

    async def prepare(self, *, turn_context, agent):  # noqa: ANN001
        _ = (turn_context, agent)
        return TurnContextItem(
            source="knowledge_base",
            title="Relevant knowledge base context",
            content="Queue restart guardrails preserve pending approvals.",
        )


class _StaticBudgetProvider:
    def __init__(self, name: str, title: str, content: str) -> None:
        self.name = name
        self._title = title
        self._content = content

    async def prepare(self, *, turn_context, agent):  # noqa: ANN001
        _ = (turn_context, agent)
        return TurnContextItem(
            source=self.name,
            title=self._title,
            content=self._content,
        )


def _write_consolidated_memory(path: Path, *, items: list[str], last_updated_utc: str) -> None:
    section_lines = [
        "<!-- MINI_AGENT_CONSOLIDATED_MEMORY_BEGIN -->",
        "## Consolidated Memory",
    ]
    section_lines.extend(f"- {item}" for item in items)
    section_lines.append(f"last_updated_utc: {last_updated_utc}")
    section_lines.append("<!-- MINI_AGENT_CONSOLIDATED_MEMORY_END -->")
    path.write_text(
        "# Long-Term Memory\n\n" + "\n".join(section_lines) + "\n",
        encoding="utf-8",
    )


def _write_skill(
    skill_dir: Path,
    *,
    name: str,
    description: str,
    body: str,
) -> Path:
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "\n".join(
            [
                "---",
                f"name: {name}",
                f"description: {description}",
                "---",
                "",
                body,
                "",
            ]
        ),
        encoding="utf-8",
    )
    return skill_file


@pytest.mark.asyncio
async def test_run_turn_injects_ephemeral_context_without_polluting_history(tmp_path: Path) -> None:
    llm = _CaptureLLM([LLMResponse(content="done", thinking=None, tool_calls=None, finish_reason="stop")])
    logger = AgentLogger(log_dir=tmp_path / "logs")
    agent = Agent(
        llm_client=llm,
        system_prompt="system",
        tools=[],
        max_steps=2,
        workspace_dir=str(tmp_path / "workspace"),
        logger=logger,
        console_output=False,
        turn_context_providers=[_StaticProvider()],
    )
    agent.add_user_message("use the prepared context")

    result = await agent.run_turn(
        turn_context=RuntimeTurnContext(
            session_id="sess-1",
            submission_id="sub-1",
            user_input="use the prepared context",
            metadata={"surface": "cli"},
        )
    )

    assert result.stop_reason == TurnStopReason.END_TURN
    assert len(llm.captured_messages) == 1
    captured = llm.captured_messages[0]
    assert [message.role for message in captured] == ["system", "system", "user"]
    assert captured[1].name.startswith("__mini_agent_turn_context__")
    assert "Injected context" in str(captured[1].content)
    assert "ctx for use the prepared context" in str(captured[1].content)

    assert [message.role for message in agent.messages] == ["system", "user", "assistant"]
    assert all(not str(message.name or "").startswith("__mini_agent_turn_context__") for message in agent.messages)
    assert agent.last_prepared_turn_context is not None
    assert agent.last_prepared_turn_context["item_count"] == 1
    assert agent.last_prepared_turn_context["sources"] == ["static"]


@pytest.mark.asyncio
async def test_failing_turn_context_provider_does_not_break_turn_execution(tmp_path: Path) -> None:
    llm = _CaptureLLM([LLMResponse(content="done", thinking=None, tool_calls=None, finish_reason="stop")])
    logger = AgentLogger(log_dir=tmp_path / "logs")
    agent = Agent(
        llm_client=llm,
        system_prompt="system",
        tools=[],
        max_steps=2,
        workspace_dir=str(tmp_path / "workspace"),
        logger=logger,
        console_output=False,
        turn_context_providers=[_FailingProvider()],
    )
    agent.add_user_message("hello")

    result = await agent.run_turn(
        turn_context=RuntimeTurnContext(
            session_id="sess-2",
            submission_id="sub-2",
            user_input="hello",
        )
    )

    assert result.stop_reason == TurnStopReason.END_TURN
    assert agent.last_prepared_turn_context is not None
    assert agent.last_prepared_turn_context["item_count"] == 0
    assert len(agent.last_prepared_turn_context["provider_failures"]) == 1
    assert agent.last_prepared_turn_context["provider_failures"][0]["provider"] == "broken"

    events = AgentLogger.read_events(logger.get_event_file_path())
    assert any(event["type"] == "turn_context.provider_failed" for event in events)
    assert any(event["type"] == "turn_context.prepared" for event in events)


@pytest.mark.asyncio
async def test_user_profile_turn_context_provider_returns_relevant_global_profile(tmp_path: Path) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    global_root = (tmp_path / "global").resolve()
    user_file = global_root / "USER.md"
    user_file.parent.mkdir(parents=True, exist_ok=True)
    user_file.write_text(
        "\n".join(
            [
                "# User Profile",
                "",
                "<!-- MINI_AGENT_USER_PROFILE_BEGIN -->",
                "## User Facts",
                "- User prefers Chinese replies with concise structure.",
                "- User wants TUI/CLI-first explanations.",
                "last_updated_utc: 2026-04-10T00:00:00+00:00",
                "<!-- MINI_AGENT_USER_PROFILE_END -->",
                "",
            ]
        ),
        encoding="utf-8",
    )

    provider = UserProfileTurnContextProvider(workspace)
    item = await provider.prepare(
        turn_context=RuntimeTurnContext(
            session_id="sess-user-profile",
            submission_id="sub-user-profile",
            user_input="Should you reply in Chinese?",
        ),
        agent=SimpleNamespace(messages=[]),
    )

    assert item is not None
    assert item.source == "user_profile"
    assert item.title == "Relevant user profile"
    assert "Chinese replies" in item.content
    assert item.metadata["scope"] == "global"
    assert item.metadata["user_file"] == str(user_file.resolve())
    assert item.metadata["ranking_score"] > 0.0
    assert item.metadata["ranking_basis"] == "user_profile_match"


@pytest.mark.asyncio
async def test_workspace_memory_context_provider_returns_relevant_workspace_note(tmp_path: Path) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    memory_file = workspace / "MEMORY.md"
    memory_file.write_text(
        "\n".join(
            [
                "# Long-Term Memory",
                "",
                "- [2026-04-09T09:00:00+00:00] [config] API keys load from system env first, then .env.local.",
                "- [2026-04-09T10:00:00+00:00] [ui] TUI models panel follows the active selection.",
            ]
        ),
        encoding="utf-8",
    )

    provider = WorkspaceMemoryContextProvider(workspace)
    item = await provider.prepare(
        turn_context=RuntimeTurnContext(
            session_id="sess-memory",
            submission_id="sub-memory",
            user_input="How do API keys load?",
        ),
        agent=type("AgentStub", (), {"messages": []})(),
    )

    assert item is not None
    assert item.source == "workspace_memory"
    assert item.title == "Relevant workspace memory"
    assert "API keys load from system env first" in item.content
    assert item.metadata["ranking_score"] > 0.0
    assert item.metadata["ranking_basis"] == "workspace_memory_text_match"


@pytest.mark.asyncio
async def test_runtime_recovery_turn_context_provider_surfaces_restart_hint() -> None:
    provider = RuntimeRecoveryTurnContextProvider()
    item = await provider.prepare(
        turn_context=RuntimeTurnContext(
            session_id="sess-recovery",
            submission_id="sub-recovery",
            user_input="continue previous task",
            metadata={
                "recovery": {
                    "state": "interrupted",
                    "summary": "interrupted after restart: approval pending for shell",
                    "last_activity": "shell ok | pytest -q | 32 passed",
                    "last_user_message": "inspect tests",
                    "last_assistant_message": "working on it",
                    "pending_approvals": [
                        {
                            "token": "approval-1",
                            "tool_name": "shell",
                        }
                    ],
                }
            },
        ),
        agent=SimpleNamespace(messages=[]),
    )

    assert item is not None
    assert item.source == "runtime"
    assert item.title == "Shared-session recovery"
    assert "approval pending for shell" in item.content
    assert "Pending approvals were lost after restart" in item.content
    assert item.metadata["ranking_basis"] == "runtime_recovery"


@pytest.mark.asyncio
async def test_consolidated_memory_turn_context_provider_returns_relevant_hit(tmp_path: Path) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    memory_file = workspace / "MEMORY.md"
    _write_consolidated_memory(
        memory_file,
        items=[
            "queue backpressure guardrails must preserve pending approvals during restart",
            "models view follows the active provider selection in TUI",
        ],
        last_updated_utc="2026-04-09T10:00:00+00:00",
    )

    provider = ConsolidatedMemoryTurnContextProvider(workspace)
    item = await provider.prepare(
        turn_context=RuntimeTurnContext(
            session_id="sess-rel-memory",
            submission_id="sub-rel-memory",
            user_input="How do restart guardrails preserve approvals?",
        ),
        agent=SimpleNamespace(messages=[]),
    )

    assert item is not None
    assert item.source == "consolidated_memory"
    assert item.title == "Relevant consolidated memory"
    assert "pending approvals during restart" in item.content
    assert item.metadata["returned"] >= 1
    assert item.metadata["memory_file"] == str(memory_file.resolve())
    assert item.metadata["drift_summary"]["unverified"] >= 1
    assert item.metadata["ranking_score"] > 0.0
    assert item.metadata["ranking_basis"] == "consolidated_memory_relevance"


@pytest.mark.asyncio
async def test_consolidated_memory_turn_context_provider_auto_refreshes_missing_section(tmp_path: Path) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    session_store_dir = (tmp_path / "sessions").resolve()
    now_utc = "2026-04-10T08:00:00+00:00"

    provider = ConsolidatedMemoryTurnContextProvider(
        workspace,
        session_store_dir=session_store_dir,
    )
    provider.memory_service._session_store().save_session(
        session_id="sess-auto-refresh",
        workspace_dir=str(workspace),
        created_at=now_utc,
        updated_at=now_utc,
        messages=[
            {"role": "user", "content": "keep remote recovery visible in TUI threads"},
            {"role": "assistant", "content": "remote recovery stays visible in TUI threads after restart"},
        ],
    )

    item = await provider.prepare(
        turn_context=RuntimeTurnContext(
            session_id="sess-current",
            submission_id="sub-current",
            user_input="How should remote recovery show up in TUI threads?",
        ),
        agent=SimpleNamespace(messages=[]),
    )

    assert item is not None
    assert item.source == "consolidated_memory"
    assert "remote recovery stays visible in TUI threads" in item.content
    assert item.metadata["refresh_triggered"] is True


@pytest.mark.asyncio
async def test_session_search_turn_context_provider_returns_same_workspace_history(tmp_path: Path) -> None:
    workspace_root = (tmp_path / "repo").resolve()
    nested_workspace = (workspace_root / "src" / "feature").resolve()
    nested_workspace.mkdir(parents=True, exist_ok=True)
    (workspace_root / "MEMORY.md").write_text("# Long-Term Memory\n", encoding="utf-8")

    other_workspace = (tmp_path / "other-repo").resolve()
    other_workspace.mkdir(parents=True, exist_ok=True)
    (other_workspace / "MEMORY.md").write_text("# Long-Term Memory\n", encoding="utf-8")

    session_store_dir = (tmp_path / "sessions").resolve()
    provider = SessionSearchTurnContextProvider(
        nested_workspace,
        session_store_dir=session_store_dir,
        top_k=2,
    )
    provider.memory_service._session_store().save_session(
        session_id="sess-related",
        workspace_dir=str(nested_workspace),
        created_at="2026-04-10T10:00:00+00:00",
        updated_at="2026-04-10T10:00:00+00:00",
        messages=[
            {"role": "assistant", "content": "Use an opencode-style sidebar and keep the chat area dominant."},
        ],
    )
    provider.memory_service._session_store().save_session(
        session_id="sess-other-workspace",
        workspace_dir=str(other_workspace),
        created_at="2026-04-10T10:05:00+00:00",
        updated_at="2026-04-10T10:05:00+00:00",
        messages=[
            {"role": "assistant", "content": "Use an opencode-style sidebar and keep the chat area dominant."},
        ],
    )
    provider.memory_service._session_store().save_session(
        session_id="sess-current",
        workspace_dir=str(nested_workspace),
        created_at="2026-04-10T10:10:00+00:00",
        updated_at="2026-04-10T10:10:00+00:00",
        messages=[
            {"role": "assistant", "content": "Use an opencode-style sidebar and keep the chat area dominant."},
        ],
    )

    item = await provider.prepare(
        turn_context=RuntimeTurnContext(
            session_id="sess-current",
            submission_id="sub-session-search",
            user_input="What sidebar layout should we keep?",
        ),
        agent=SimpleNamespace(messages=[]),
    )

    assert item is not None
    assert item.source == "session_search"
    assert item.title == "Relevant workspace session history"
    assert "sess-related" in item.content
    assert "sess-current" not in item.content
    assert "sess-other-workspace" not in item.content
    assert item.metadata["workspace_anchor_dir"] == str(nested_workspace)
    assert item.metadata["excluded_session_id"] == "sess-current"
    assert item.metadata["ranking_basis"] == "session_search_match"


@pytest.mark.asyncio
async def test_skill_catalog_turn_context_provider_returns_matching_skills(tmp_path: Path) -> None:
    builtin_root = tmp_path / "skills"
    _write_skill(
        builtin_root / "doc-coauthoring",
        name="doc-coauthoring",
        description="Draft proposals, technical specs, and other structured documentation with the user.",
        body="Use this skill for proposal writing.",
    )
    _write_skill(
        builtin_root / "capacity",
        name="capacity",
        description="Analyze model quota and deployment regions.",
        body="Use this skill for quota work.",
    )

    provider = SkillCatalogTurnContextProvider(
        builtin_dir=builtin_root,
        top_k=2,
    )
    item = await provider.prepare(
        turn_context=RuntimeTurnContext(
            session_id="sess-skill",
            submission_id="sub-skill",
            user_input="Help me draft a technical proposal for this feature.",
        ),
        agent=SimpleNamespace(messages=[]),
    )

    assert item is not None
    assert item.source == "skill_catalog"
    assert item.title == "Relevant skills"
    assert "call `get_skill(skill_name)` before relying on it" in item.content
    assert "Do not merely mention a skill name from metadata" in item.content
    assert "`doc-coauthoring`" in item.content
    assert item.metadata["skills"] == ["doc-coauthoring"]
    assert item.metadata["ranking_score"] > 0.0
    assert item.metadata["ranking_basis"] == "skill_catalog_match"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("prompt", "expected_skill"),
    [
        ("给这个项目做一个前后端打通的设置页和保存接口", "fullstack-dev"),
        ("生成一段轻柔钢琴背景音乐", "minimax-music-gen"),
        ("看这张界面截图，帮我分析哪里布局错了", "vision-analysis"),
        ("给 nyonyo 做一段简短的欢迎歌曲", "buddy-sings"),
        ("给这个 demo 设计一个三首曲子的背景音乐播放列表", "minimax-music-playlist"),
    ],
)
async def test_repo_builtin_skill_catalog_matches_key_chinese_prompts(
    prompt: str,
    expected_skill: str,
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    provider = SkillCatalogTurnContextProvider(
        builtin_dir=repo_root / "src" / "mini_agent" / "skills",
        top_k=3,
    )

    item = await provider.prepare(
        turn_context=RuntimeTurnContext(
            session_id="sess-skill-real",
            submission_id="sub-skill-real",
            user_input=prompt,
        ),
        agent=SimpleNamespace(messages=[]),
    )

    assert item is not None
    assert item.metadata["skills"][0] == expected_skill


@pytest.mark.asyncio
async def test_mcp_tool_catalog_turn_context_provider_returns_relevant_server() -> None:
    clear_registered_connections()
    register_connection(
        SimpleNamespace(
            name="search-hub",
            connection_type="stdio",
            tools=[
                SimpleNamespace(
                    name=mcp_tool_alias("search-hub", "search_docs"),
                    remote_name="search_docs",
                    description="Search API and engineering docs.",
                ),
                SimpleNamespace(
                    name=mcp_tool_alias("search-hub", "fetch_page"),
                    remote_name="fetch_page",
                    description="Fetch one documentation page.",
                ),
            ],
        )
    )
    register_connection(
        SimpleNamespace(
            name="calendar",
            connection_type="streamable_http",
            tools=[
                SimpleNamespace(
                    name=mcp_tool_alias("calendar", "list_events"),
                    remote_name="list_events",
                    description="List today's events.",
                )
            ],
        )
    )

    try:
        provider = MCPToolCatalogTurnContextProvider(top_k_servers=1, top_k_tools=2)
        item = await provider.prepare(
            turn_context=RuntimeTurnContext(
                session_id="sess-mcp",
                submission_id="sub-mcp",
                user_input="Search docs for the auth API flow.",
            ),
            agent=SimpleNamespace(messages=[]),
        )
    finally:
        clear_registered_connections()

    assert item is not None
    assert item.source == "mcp_catalog"
    assert item.title == "Relevant MCP capabilities"
    assert "`search-hub`" in item.content
    assert mcp_tool_alias("search-hub", "search_docs") in item.content
    assert "<- search_docs" in item.content
    assert item.metadata["servers"] == ["search-hub"]
    assert item.metadata["ranking_score"] > 0.0
    assert item.metadata["ranking_basis"] == "mcp_catalog_match"


def test_build_turn_context_providers_wires_additional_provider_types(tmp_path: Path) -> None:
    config = SimpleNamespace(
        tools=SimpleNamespace(
            enable_note=True,
            enable_knowledge_base=True,
            enable_skills=True,
            enable_mcp=True,
            skills_dir=str(tmp_path / "skills"),
        )
    )
    providers = build_turn_context_providers(config, tmp_path / "workspace")

    assert [provider.name for provider in providers] == [
        "runtime_recovery",
        "runtime_task_memory",
        "session_search",
        "user_profile",
        "workspace_memory",
        "consolidated_memory",
        "skill_catalog",
        "mcp_catalog",
    ]


def test_resolve_workspace_skills_dir_prefers_workspace_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "workspace"
    local_dir = workspace / ".mini-agent" / "skills"
    fallback_dir = workspace / "skills"
    local_dir.mkdir(parents=True)
    fallback_dir.mkdir(parents=True)

    monkeypatch.delenv("MINI_AGENT_WORKSPACE_SKILLS_DIR", raising=False)

    assert resolve_workspace_skills_dir(workspace) == local_dir.resolve()

    extra_dir = tmp_path / "custom-skills"
    extra_dir.mkdir()
    monkeypatch.setenv("MINI_AGENT_WORKSPACE_SKILLS_DIR", str(extra_dir))

    assert resolve_workspace_skills_dir(workspace) == extra_dir.resolve()


@pytest.mark.asyncio
async def test_run_turn_deduplicates_lower_priority_turn_context_items(tmp_path: Path) -> None:
    llm = _CaptureLLM([LLMResponse(content="done", thinking=None, tool_calls=None, finish_reason="stop")])
    logger = AgentLogger(log_dir=tmp_path / "logs")
    agent = Agent(
        llm_client=llm,
        system_prompt="system",
        tools=[],
        max_steps=2,
        workspace_dir=str(tmp_path / "workspace"),
        logger=logger,
        console_output=False,
        turn_context_providers=[_DuplicateWorkspaceProvider(), _DuplicateKnowledgeProvider()],
    )
    agent.add_user_message("how do restart guardrails work?")

    await agent.run_turn(
        turn_context=RuntimeTurnContext(
            session_id="sess-curate-dup",
            submission_id="sub-curate-dup",
            user_input="how do restart guardrails work?",
        )
    )

    assert agent.last_prepared_turn_context is not None
    assert agent.last_prepared_turn_context["item_count"] == 1
    assert agent.last_prepared_turn_context["raw_item_count"] == 2
    assert agent.last_prepared_turn_context["dropped_duplicate_count"] == 1
    assert agent.last_prepared_turn_context["sources"] == ["knowledge_base"]
    captured = llm.captured_messages[0]
    assert "Relevant knowledge base context" in str(captured[1].content)
    assert "Relevant workspace memory" not in str(captured[1].content)


@pytest.mark.asyncio
async def test_run_turn_applies_turn_context_budget_and_reports_curation(tmp_path: Path) -> None:
    llm = _CaptureLLM([LLMResponse(content="done", thinking=None, tool_calls=None, finish_reason="stop")])
    logger = AgentLogger(log_dir=tmp_path / "logs")
    agent = Agent(
        llm_client=llm,
        system_prompt="system",
        tools=[],
        max_steps=2,
        workspace_dir=str(tmp_path / "workspace"),
        logger=logger,
        console_output=False,
        turn_context_providers=[
            _StaticBudgetProvider("knowledge_base", "KB", "Documented runtime architecture."),
            _StaticBudgetProvider("consolidated_memory", "Memory", "Long-lived runtime guardrail."),
            _StaticBudgetProvider("skill_catalog", "Skills", "Use doc-coauthoring when drafting specs."),
        ],
        turn_context_max_items=2,
        turn_context_max_total_chars=400,
    )
    agent.add_user_message("summarize the runtime architecture")

    await agent.run_turn(
        turn_context=RuntimeTurnContext(
            session_id="sess-curate-budget",
            submission_id="sub-curate-budget",
            user_input="summarize the runtime architecture",
        )
    )

    assert agent.last_prepared_turn_context is not None
    summary = agent.last_prepared_turn_context
    assert summary["item_count"] == 2
    assert summary["raw_item_count"] == 3
    assert summary["dropped_item_count"] == 1
    assert summary["dropped_budget_count"] == 1
    summary_line = prepared_turn_context_summary_line(summary)
    assert "dropped 1 item(s)" in summary_line
    details = format_prepared_turn_context_details(summary, include_header=False)
    assert "Curated: kept 2/3 | budget 1" in details


def test_curate_turn_context_items_uses_provider_relevance_weighting_for_budget() -> None:
    curated, summary = curate_turn_context_items(
        [
            TurnContextItem(
                source="knowledge_base",
                title="KB",
                content="Barely-related knowledge-base hit.",
                metadata={"ranking_score": 0.05},
            ),
            TurnContextItem(
                source="skill_catalog",
                title="Skills",
                content="Highly-relevant skill suggestion.",
                metadata={"ranking_score": 0.95},
            ),
            TurnContextItem(
                source="mcp_catalog",
                title="MCP",
                content="Moderately relevant MCP tool.",
                metadata={"ranking_score": 0.60},
            ),
        ],
        max_items=1,
        max_items_per_source=1,
        max_total_chars=400,
    )

    assert [item.source for item in curated] == ["skill_catalog"]
    assert summary["dropped_budget_count"] == 2


def test_curate_turn_context_items_prefers_higher_ranking_score_for_same_priority_duplicate() -> None:
    curated, summary = curate_turn_context_items(
        [
            TurnContextItem(
                source="skill_catalog",
                title="Lower score",
                content="Use doc-coauthoring for proposal drafting.",
                metadata={"ranking_score": 0.25},
            ),
            TurnContextItem(
                source="skill_catalog",
                title="Higher score",
                content="Use doc-coauthoring for proposal drafting.",
                metadata={"ranking_score": 0.90},
            ),
        ],
        max_items=2,
        max_items_per_source=1,
        max_total_chars=400,
    )

    assert len(curated) == 1
    assert curated[0].title == "Higher score"
    assert summary["dropped_duplicate_count"] == 1


@pytest.mark.asyncio
async def test_run_turn_context_policy_filters_provider_and_reports_statuses(tmp_path: Path) -> None:
    llm = _CaptureLLM([LLMResponse(content="done", thinking=None, tool_calls=None, finish_reason="stop")])
    logger = AgentLogger(log_dir=tmp_path / "logs")
    agent = Agent(
        llm_client=llm,
        system_prompt="system",
        tools=[],
        max_steps=2,
        workspace_dir=str(tmp_path / "workspace"),
        logger=logger,
        console_output=False,
        turn_context_providers=[
            _StaticBudgetProvider("knowledge_base", "KB", "Knowledge-base context."),
            _StaticBudgetProvider("mcp_catalog", "MCP", "MCP capability context."),
        ],
    )
    agent.add_user_message("use only knowledge base")

    await agent.run_turn(
        turn_context=RuntimeTurnContext(
            session_id="sess-policy",
            submission_id="sub-policy",
            user_input="use only knowledge base",
            metadata={"prepared_context_policy": {"include_sources": ["knowledge_base"]}},
        )
    )

    assert agent.last_prepared_turn_context is not None
    summary = agent.last_prepared_turn_context
    assert summary["item_count"] == 1
    assert summary["sources"] == ["knowledge_base"]
    assert summary["policy"]["active"] is True
    filtered = next(item for item in summary["provider_statuses"] if item["provider"] == "mcp_catalog")
    assert filtered["status"] == "filtered"
    assert "not included" in filtered["reason"]


def test_prepared_context_detail_formatting_renders_policy_and_provider_statuses() -> None:
    payload = {
        "item_count": 1,
        "sources": ["knowledge_base"],
        "items": [
            {
                "source": "knowledge_base",
                "title": "Relevant knowledge base context",
                "preview": "Runtime routing falls back cleanly.",
                "metadata": {
                    "ranking_score": 0.87321,
                    "ranking_basis": "knowledge_base_rrf",
                    "ranking_score_raw": 0.03125,
                },
            }
        ],
        "provider_failures": [],
        "provider_statuses": [
            {"provider": "knowledge_base", "status": "used", "item_count": 1, "reason": "store ready for kb=default"},
            {"provider": "mcp_catalog", "status": "filtered", "item_count": 0, "reason": "excluded by prepared-context policy"},
        ],
        "policy": {
            "include_sources": ["knowledge_base"],
            "exclude_sources": ["mcp_catalog"],
            "max_items": 2,
            "max_items_per_source": 1,
            "max_total_chars": 1200,
        },
    }

    assert "include=knowledge_base" in context_policy_summary_line(payload["policy"], include_default=True)
    assert "budget=2 item(s)/1200 chars/1 per-source" in format_context_policy_details(payload["policy"], include_header=False)
    details = format_prepared_turn_context_details(payload, include_header=False)
    assert "Policy: include=knowledge_base | exclude=mcp_catalog | budget=2 item(s)/1200 chars/1 per-source" in details
    assert "ranking: basis knowledge_base_rrf | raw 0.0312 | item-relevance 0.873" in details
    assert "selection: provider-weight 1.000 | priority 100 | final-selection 1.873" in details
    assert "Providers:" in details
    assert "- knowledge_base: used (1 item(s)) | store ready for kb=default" in details
    assert "- mcp_catalog: filtered | excluded by prepared-context policy" in details


def test_prepared_context_detail_formatting_brief_mode_hides_ranking_and_provider_statuses() -> None:
    payload = {
        "item_count": 1,
        "sources": ["knowledge_base"],
        "items": [
            {
                "source": "knowledge_base",
                "title": "Relevant knowledge base context",
                "preview": "Runtime routing falls back cleanly.",
                "metadata": {
                    "ranking_score": 0.87321,
                    "ranking_basis": "knowledge_base_rrf",
                    "ranking_score_raw": 0.03125,
                },
            }
        ],
        "provider_failures": [
            {"provider": "broken_provider", "error": "RuntimeError: synthetic failure"}
        ],
        "provider_statuses": [
            {"provider": "knowledge_base", "status": "used", "item_count": 1, "reason": "store ready"}
        ],
        "policy": {
            "max_items": 2,
            "max_items_per_source": 1,
            "max_total_chars": 1200,
        },
    }

    details = format_prepared_turn_context_details(
        payload,
        include_header=False,
        detail_mode="brief",
    )

    assert "1. [knowledge_base] Relevant knowledge base context -> Runtime routing falls back cleanly." in details
    assert "ranking:" not in details
    assert "Providers:" not in details
    assert "broken_provider" in details


def test_prepared_context_diagnostics_accumulates_turns_and_formats_details() -> None:
    diagnostics = update_prepared_context_diagnostics(
        {},
        {
            "item_count": 1,
            "sources": ["knowledge_base"],
            "items": [
                {
                    "source": "knowledge_base",
                    "title": "Relevant knowledge base context",
                    "preview": "Runtime routing falls back cleanly.",
                }
            ],
            "provider_statuses": [
                {"provider": "knowledge_base", "status": "used", "item_count": 1, "reason": "store ready"},
                {"provider": "mcp_catalog", "status": "unavailable", "item_count": 0, "reason": "no connections"},
            ],
            "dropped_item_count": 1,
            "curated": True,
        },
    )
    diagnostics = update_prepared_context_diagnostics(
        diagnostics,
        {
            "item_count": 0,
            "sources": [],
            "items": [],
            "provider_statuses": [
                {"provider": "knowledge_base", "status": "no_match", "item_count": 0, "reason": "no relevant context"},
                {"provider": "mcp_catalog", "status": "filtered", "item_count": 0, "reason": "excluded"},
            ],
            "dropped_item_count": 0,
            "curated": False,
        },
    )

    summary_line = prepared_context_diagnostics_summary_line(diagnostics)
    assert summary_line == "2 turn(s) | 1 with context | 1 item(s) | curated 1 | dropped 1"

    details = format_prepared_context_diagnostics(diagnostics, include_header=True)
    assert "Context diagnostics: 2 turn(s) | 1 with context | 1 item(s) | curated 1 | dropped 1" in details
    assert "Last turn: 0 item(s)" in details
    assert "- knowledge_base: 1 turn(s) | 1 item(s)" in details
    assert "Provider totals: filtered 1, no_match 1, unavailable 1, used 1" in details
    assert "- knowledge_base: no_match 1, used 1" in details
