from __future__ import annotations

import asyncio
from types import SimpleNamespace

from mini_agent.runtime.handlers.session_skill_handler import RuntimeSessionSkillHandler
from tests.runtime_contract_fixtures import runtime_projection_stub, runtime_session_stub


def _build_skill_handler(**overrides):
    async def _queue_workspace_skill_reload(*args, **kwargs):  # noqa: ARG001
        return ()

    defaults = dict(
        normalize_surface=lambda value: str(value or "tui"),
        session_commands=SimpleNamespace(
            execute_locked=lambda session, **kwargs: kwargs["operation"](),  # noqa: ARG005
        ),
        session_skill_commands=SimpleNamespace(),
        session_agent_runtime=SimpleNamespace(
            rebuild_agent_with_identity=lambda *args, **kwargs: None,  # noqa: ARG005
        ),
        load_runtime_config=lambda: None,
        selected_model_identity=lambda _session: None,
        queue_workspace_skill_reload=_queue_workspace_skill_reload,
    )
    defaults.update(overrides)
    return RuntimeSessionSkillHandler(**defaults)


def test_runtime_session_skill_handler_returns_read_only_skill_results_without_mutation() -> None:
    handler = _build_skill_handler(
        session_skill_commands=SimpleNamespace(
            validate_action=lambda action: None,  # noqa: ARG005
            prepare=lambda **kwargs: SimpleNamespace(
                mutation=None,
                status="ok",
                result={"summary": "1 skill found", "match_count": 1},
            ),
        ),
    )
    session = runtime_session_stub(
        session_id="sess-skill",
        projection=runtime_projection_stub(active_surface="desktop", origin_surface="desktop"),
    )

    response = asyncio.run(handler.manage_skills(session, action="search", query="repo"))

    assert response.status == "ok"
    assert response.action == "search"
    assert response.result["match_count"] == 1


def test_runtime_session_skill_handler_busy_mutations_return_busy_projection() -> None:
    queue_calls: list[dict[str, object]] = []

    async def _queue_workspace_skill_reload(workspace_dir, **kwargs):  # noqa: ANN001
        queue_calls.append({"workspace_dir": workspace_dir, **kwargs})
        return ("sess-a", "sess-b")

    mutation = SimpleNamespace(reload_reason="workspace skill updated", command_name="skill install")
    handler = _build_skill_handler(
        session_skill_commands=SimpleNamespace(
            validate_action=lambda action: None,  # noqa: ARG005
            prepare=lambda **kwargs: SimpleNamespace(
                mutation=mutation,
                status="prepared",
                result=None,
            ),
            build_busy_result=lambda **kwargs: {
                "summary": "skill queued",
                "queued_ids": list(kwargs["queued_ids"]),
            },
        ),
        queue_workspace_skill_reload=_queue_workspace_skill_reload,
    )
    session = runtime_session_stub(
        session_id="sess-skill-busy",
        workspace_dir="workspace-root",
        projection=runtime_projection_stub(
            busy=True,
            active_surface="desktop",
            origin_surface="desktop",
        ),
    )

    response = asyncio.run(handler.manage_skills(session, action="install", path="C:/skills/repo-helper"))

    assert response.status == "busy"
    assert response.result["queued_ids"] == ["sess-a", "sess-b"]
    assert queue_calls == [
        {
            "workspace_dir": "workspace-root",
            "current_session_id": "sess-skill-busy",
            "reason": "workspace skill updated",
            "include_current": True,
        }
    ]
