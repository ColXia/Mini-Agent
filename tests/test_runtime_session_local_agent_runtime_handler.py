from __future__ import annotations

import asyncio
from types import SimpleNamespace

from mini_agent.runtime.session_local_agent_runtime_handler import LocalSessionAgentRuntimeHandler


def test_local_session_agent_runtime_handler_rebuilds_with_identity_and_clears_pending_state() -> None:
    session = SimpleNamespace(
        title="Session 1",
        runtime=SimpleNamespace(agent=SimpleNamespace(llm_client=SimpleNamespace(model="old-model")), cancel_event=object()),
        projection=SimpleNamespace(running_state="working", pending_approvals=[{"token": "a"}]),
        operator=SimpleNamespace(),
    )
    selected_calls: list[tuple[str, str, str] | None] = []
    pending_calls: list[tuple[str, str, str] | None] = []
    captured: list[str] = []
    shutdown_calls: list[str] = []
    cleared_skill_reload: list[str] = []
    persisted: list[str] = []
    warm_prefixes: list[str] = []

    async def _shutdown(_session) -> None:  # noqa: ANN001
        shutdown_calls.append("stopped")

    async def _warm(_session, prefix: str):  # noqa: ANN001
        warm_prefixes.append(prefix)
        rebuilt = SimpleNamespace(llm=SimpleNamespace(model="gpt-5.3"))
        session.runtime.agent = rebuilt
        return rebuilt

    def _reset_runtime(_session) -> None:  # noqa: ANN001
        session.runtime.agent = None
        session.runtime.cancel_event = None
        session.projection.running_state = ""
        session.projection.pending_approvals = []

    handler = LocalSessionAgentRuntimeHandler(
        selected_model_identity=lambda _session: ("preset", "openai", "gpt-5.3"),
        set_selected_model_identity=lambda _session, identity: selected_calls.append(identity),
        set_pending_model_identity=lambda _session, identity: pending_calls.append(identity),
        clear_pending_skill_reload=lambda _session: cleared_skill_reload.append("cleared"),
        capture_session_agent_snapshot=lambda _session: captured.append("captured"),
        shutdown_submission_loop=_shutdown,
        reset_runtime_execution_state=_reset_runtime,
        warm_session_agent=_warm,
        format_model_identity=lambda identity: f"{identity[1]}/{identity[2]}" if identity else "auto",
        persist_session_state=lambda: persisted.append("persisted"),
    )

    outcome = asyncio.run(
        handler.rebuild_with_identity(
            session,
            identity=("preset", "openai", "gpt-5.3"),
            warm_prefix="Applied openai/gpt-5.3 for Session 1",
            clear_pending_model_identity=True,
            clear_pending_skill_reload_on_success=True,
            persist_before_warm=True,
        )
    )

    assert selected_calls == [("preset", "openai", "gpt-5.3")]
    assert pending_calls == [None]
    assert captured == ["captured"]
    assert shutdown_calls == ["stopped"]
    assert session.runtime.cancel_event is None
    assert session.projection.running_state == ""
    assert session.projection.pending_approvals == []
    assert warm_prefixes == ["Applied openai/gpt-5.3 for Session 1"]
    assert cleared_skill_reload == ["cleared"]
    assert persisted == ["persisted", "persisted"]
    assert outcome.warmed_agent is session.runtime.agent
    assert outcome.selected_identity == ("preset", "openai", "gpt-5.3")
    assert outcome.active_model_label == "openai/gpt-5.3"


def test_local_session_agent_runtime_handler_rebuild_current_identity_preserves_pending_reload_on_warm_failure() -> None:
    session = SimpleNamespace(
        title="Session 2",
        runtime=SimpleNamespace(agent=SimpleNamespace(llm_client=SimpleNamespace(model="old-model")), cancel_event=object()),
        projection=SimpleNamespace(running_state="working", pending_approvals=[{"token": "a"}]),
        operator=SimpleNamespace(),
    )
    selected_calls: list[tuple[str, str, str] | None] = []
    cleared_skill_reload: list[str] = []
    persisted: list[str] = []

    async def _shutdown(_session) -> None:  # noqa: ANN001
        return None

    async def _warm(_session, prefix: str):  # noqa: ANN001
        _ = prefix
        return None

    def _reset_runtime(_session) -> None:  # noqa: ANN001
        session.runtime.agent = None
        session.runtime.cancel_event = None
        session.projection.running_state = ""
        session.projection.pending_approvals = []

    handler = LocalSessionAgentRuntimeHandler(
        selected_model_identity=lambda _session: ("preset", "anthropic", "claude-3-7-sonnet"),
        set_selected_model_identity=lambda _session, identity: selected_calls.append(identity),
        set_pending_model_identity=lambda _session, identity: None,
        clear_pending_skill_reload=lambda _session: cleared_skill_reload.append("cleared"),
        capture_session_agent_snapshot=lambda _session: None,
        shutdown_submission_loop=_shutdown,
        reset_runtime_execution_state=_reset_runtime,
        warm_session_agent=_warm,
        format_model_identity=lambda identity: f"{identity[1]}/{identity[2]}" if identity else "auto",
        persist_session_state=lambda: persisted.append("persisted"),
    )

    outcome = asyncio.run(
        handler.rebuild_current_identity(
            session,
            warm_prefix="Reloaded skills for Session 2",
            clear_pending_skill_reload_on_success=True,
        )
    )

    assert selected_calls == [("preset", "anthropic", "claude-3-7-sonnet")]
    assert cleared_skill_reload == []
    assert persisted == []
    assert outcome.warmed_agent is None
    assert outcome.selected_identity == ("preset", "anthropic", "claude-3-7-sonnet")
    assert outcome.active_model_label == "anthropic/claude-3-7-sonnet"


def test_local_session_agent_runtime_handler_passes_warm_prefix_by_keyword() -> None:
    session = SimpleNamespace(
        title="Session 3",
        runtime=SimpleNamespace(agent=None, cancel_event=object()),
        projection=SimpleNamespace(running_state="working", pending_approvals=[{"token": "a"}]),
        operator=SimpleNamespace(),
    )
    warm_prefixes: list[str] = []

    async def _shutdown(_session) -> None:  # noqa: ANN001
        return None

    async def _warm(_session, *, prefix: str):  # noqa: ANN001
        warm_prefixes.append(prefix)
        rebuilt = SimpleNamespace(llm_client=SimpleNamespace(model="qwen3.5:9b"))
        session.runtime.agent = rebuilt
        return rebuilt

    def _reset_runtime(_session) -> None:  # noqa: ANN001
        session.runtime.agent = None
        session.runtime.cancel_event = None
        session.projection.running_state = ""
        session.projection.pending_approvals = []

    handler = LocalSessionAgentRuntimeHandler(
        selected_model_identity=lambda _session: ("custom", "ollama", "qwen3.5:9b"),
        set_selected_model_identity=lambda _session, identity: None,
        set_pending_model_identity=lambda _session, identity: None,
        clear_pending_skill_reload=lambda _session: None,
        capture_session_agent_snapshot=lambda _session: None,
        shutdown_submission_loop=_shutdown,
        reset_runtime_execution_state=_reset_runtime,
        warm_session_agent=_warm,
        format_model_identity=lambda identity: f"{identity[1]}/{identity[2]}" if identity else "auto",
        persist_session_state=lambda: None,
    )

    outcome = asyncio.run(
        handler.rebuild_current_identity(
            session,
            warm_prefix="Reloaded local runtime for Session 3",
        )
    )

    assert warm_prefixes == ["Reloaded local runtime for Session 3"]
    assert outcome.warmed_agent is session.runtime.agent
    assert outcome.active_model_label == "ollama/qwen3.5:9b"
