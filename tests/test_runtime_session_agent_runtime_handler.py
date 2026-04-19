from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from mini_agent.runtime.handlers.session_agent_runtime_handler import RuntimeSessionAgentRuntimeHandler
from tests.runtime_contract_fixtures import (
    RuntimeContractAgentStub,
    runtime_projection_stub,
    runtime_session_stub,
)


def test_runtime_session_agent_runtime_handler_refreshes_projection_diagnostics_after_rebuild() -> None:
    old_agent = RuntimeContractAgentStub(
        messages=[
            SimpleNamespace(role="system", content="system"),
            SimpleNamespace(role="user", content="hello"),
        ],
    )
    rebuilt_agent = RuntimeContractAgentStub(messages=[SimpleNamespace(role="system", content="system")])
    selected_identities: list[tuple[str, str, str] | None] = []
    pending_identities: list[tuple[str, str, str] | None] = []
    refreshed: list[str] = []

    def _capture_prepared_context_state(session) -> None:  # noqa: ANN001
        session.projection.last_prepared_context = {"carried": True}
        session.projection.prepared_context_diagnostics = {"prepared": True}

    def _restore_prepared_context_state(session) -> None:  # noqa: ANN001
        session.runtime.agent.last_prepared_turn_context = dict(session.projection.last_prepared_context)
        session.runtime.agent.prepared_context_diagnostics = dict(session.projection.prepared_context_diagnostics)

    def _restore_agent_messages_payload(raw_messages, agent) -> None:  # noqa: ANN001
        agent.messages = list(raw_messages)

    def _refresh_session_diagnostics(session) -> tuple[dict[str, object], dict[str, object]]:  # noqa: ANN001
        session.projection.memory_diagnostics = {"rebuilt": session.session_id}
        session.projection.sandbox_diagnostics = {"approval_profile": "plan"}
        refreshed.append(session.session_id)
        return session.projection.memory_diagnostics, session.projection.sandbox_diagnostics

    handler = RuntimeSessionAgentRuntimeHandler(
        runtime_policy_overrides_from_diagnostics=lambda _value: (None, None),
        build_agent_for_identity=lambda _workspace_dir, _identity: _return_async(rebuilt_agent),
        load_runtime_config=lambda: object(),
        reconfigure_agent_runtime_policy=lambda **_kwargs: {},
        capture_agent_prepared_context_state=_capture_prepared_context_state,
        restore_agent_prepared_context_state=_restore_prepared_context_state,
        agent_messages=lambda agent: list(agent.messages),
        serialize_agent_messages=lambda messages: [
            {"role": getattr(item, "role", "assistant"), "content": getattr(item, "content", "")}
            for item in messages
        ],
        restore_agent_messages_payload=_restore_agent_messages_payload,
        apply_agent_knowledge_base_enabled=lambda _agent, enabled: enabled,
        route_model_identity=lambda _agent: ("preset", "provider-b", "model-c"),
        set_selected_model_identity=lambda _session, identity: selected_identities.append(identity),
        set_pending_model_identity=lambda _session, identity: pending_identities.append(identity),
        refresh_runtime_projection=_refresh_session_diagnostics,
        same_workspace=lambda left, right: left == right,
        selected_model_identity=lambda _session: ("preset", "provider-a", "model-a"),
        pending_model_identity=lambda _session: None,
    )
    session = runtime_session_stub(
        session_id="sess-runtime",
        workspace_dir=Path(".").resolve(),
        agent=old_agent,
        projection=runtime_projection_stub(
            knowledge_base_enabled=True,
            last_prepared_context={},
            prepared_context_diagnostics={},
            memory_diagnostics={"stale": True},
            sandbox_diagnostics={"stale": True},
            pending_skill_reload=True,
            pending_skill_reload_reason="workspace changed",
        ),
    )

    asyncio.run(handler.rebuild_agent_with_identity(session, ("preset", "provider-a", "model-a")))

    assert session.runtime.agent is rebuilt_agent
    assert rebuilt_agent.messages[-1]["content"] == "hello"
    assert rebuilt_agent.last_prepared_turn_context == {"carried": True}
    assert rebuilt_agent.prepared_context_diagnostics == {"prepared": True}
    assert session.projection.memory_diagnostics == {"rebuilt": "sess-runtime"}
    assert session.projection.sandbox_diagnostics == {"approval_profile": "plan"}
    assert session.projection.pending_skill_reload is False
    assert session.projection.pending_skill_reload_reason == ""
    assert selected_identities == [("preset", "provider-b", "model-c")]
    assert pending_identities == [None]
    assert refreshed == ["sess-runtime"]


async def _return_async(value):  # noqa: ANN001
    return value


def test_runtime_session_agent_runtime_handler_reconfigure_runtime_policy_refreshes_projection() -> None:
    refreshed: list[str] = []
    reconfigure_calls: list[dict[str, object]] = []
    session = runtime_session_stub(
        session_id="sess-policy",
        workspace_dir=Path(".").resolve(),
        agent=RuntimeContractAgentStub(),
        projection=runtime_projection_stub(
            knowledge_base_enabled=True,
            sandbox_diagnostics={"stale": True},
            memory_diagnostics={"stale": True},
        ),
    )

    handler = RuntimeSessionAgentRuntimeHandler(
        runtime_policy_overrides_from_diagnostics=lambda _value: (None, None),
        build_agent_for_identity=lambda _workspace_dir, _identity: _return_async(None),
        load_runtime_config=lambda: "cfg",
        reconfigure_agent_runtime_policy=lambda **kwargs: reconfigure_calls.append(kwargs) or {"ignored": True},
        capture_agent_prepared_context_state=lambda _session: None,
        restore_agent_prepared_context_state=lambda _session: None,
        agent_messages=lambda _agent: [],
        serialize_agent_messages=lambda _messages: [],
        restore_agent_messages_payload=lambda _raw, _agent: None,
        apply_agent_knowledge_base_enabled=lambda _agent, enabled: enabled,
        route_model_identity=lambda _agent: None,
        set_selected_model_identity=lambda _session, _identity: None,
        set_pending_model_identity=lambda _session, _identity: None,
        refresh_runtime_projection=lambda target: refreshed.append(target.session_id)
        or (
            target.projection.memory_diagnostics.update({"memory": "ok"}) or target.projection.memory_diagnostics,
            target.projection.sandbox_diagnostics.update({"approval_profile": "plan"})
            or target.projection.sandbox_diagnostics,
        ),
        same_workspace=lambda left, right: left == right,
        selected_model_identity=lambda _session: None,
        pending_model_identity=lambda _session: None,
    )

    diagnostics = handler.reconfigure_runtime_policy(
        session,
        approval_profile="plan",
        access_level="full-access",
    )

    assert len(reconfigure_calls) == 1
    assert reconfigure_calls[0]["config"] == "cfg"
    assert reconfigure_calls[0]["workspace_dir"] == session.workspace_dir
    assert refreshed == ["sess-policy"]
    assert diagnostics == {"stale": True, "approval_profile": "plan"}
    assert session.projection.memory_diagnostics == {"stale": True, "memory": "ok"}


def test_runtime_session_agent_runtime_handler_preserves_legacy_manager_wiring() -> None:
    old_agent = RuntimeContractAgentStub(
        messages=[
            SimpleNamespace(role="system", content="system"),
            SimpleNamespace(role="user", content="legacy hello"),
        ],
        knowledge_base_enabled=True,
    )
    rebuilt_agent = RuntimeContractAgentStub(messages=[SimpleNamespace(role="system", content="system")])
    reconfigure_calls: list[dict[str, object]] = []
    selected_identities: list[tuple[str, str, str] | None] = []
    pending_identities: list[tuple[str, str, str] | None] = []

    handler = RuntimeSessionAgentRuntimeHandler(
        runtime_policy_overrides_from_diagnostics=lambda _value: ("plan", "full-access"),
        build_agent_for_identity=lambda _workspace_dir, _identity: _return_async(rebuilt_agent),
        load_runtime_config=lambda: "cfg",
        reconfigure_agent_runtime_policy=lambda **kwargs: reconfigure_calls.append(kwargs) or {},
        capture_agent_prepared_context_state=lambda _session: None,
        restore_agent_prepared_context_state=lambda _session: None,
        serialize_agent_messages=lambda messages: [
            {"role": getattr(item, "role", "assistant"), "content": getattr(item, "content", "")}
            for item in messages
        ],
        restore_agent_messages_payload=lambda raw_messages, agent: setattr(agent, "messages", list(raw_messages)),
        apply_agent_knowledge_base_enabled=lambda agent, enabled: agent.set_knowledge_base_enabled(enabled),
        route_model_identity=lambda _agent: ("preset", "provider-next", "model-next"),
        set_selected_model_identity=lambda _session, identity: selected_identities.append(identity),
        set_pending_model_identity=lambda _session, identity: pending_identities.append(identity),
        build_sandbox_diagnostics_for_session=lambda target: target.projection.sandbox_diagnostics.update(
            {"approval_profile": "build"}
        )
        or target.projection.sandbox_diagnostics,
        same_workspace=lambda left, right: left == right,
        selected_model_identity=lambda _session: ("preset", "provider-old", "model-old"),
        pending_model_identity=lambda _session: None,
    )
    session = runtime_session_stub(
        session_id="sess-legacy",
        workspace_dir=Path(".").resolve(),
        agent=old_agent,
        projection=runtime_projection_stub(
            knowledge_base_enabled=True,
            sandbox_diagnostics={"stale": True},
            pending_skill_reload=True,
            pending_skill_reload_reason="workspace changed",
        ),
    )

    asyncio.run(handler.rebuild_agent_with_identity(session, ("preset", "provider-old", "model-old")))

    assert len(reconfigure_calls) == 1
    assert reconfigure_calls[0]["config"] == "cfg"
    assert rebuilt_agent.messages[-1]["content"] == "legacy hello"
    assert session.projection.knowledge_base_enabled is True
    assert session.projection.sandbox_diagnostics == {"stale": True, "approval_profile": "build"}
    assert session.projection.pending_skill_reload is False
    assert session.projection.pending_skill_reload_reason == ""
    assert selected_identities == [("preset", "provider-next", "model-next")]
    assert pending_identities == [None]


