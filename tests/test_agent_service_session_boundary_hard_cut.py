from __future__ import annotations

from mini_agent.application.use_cases.agent_application_service import AgentApplicationService
from mini_agent.application.user_services.agent_user_service import AgentUserService


FORBIDDEN_AGENT_SESSION_METHODS = (
    "cancel_session_run",
    "interrupt_session_run",
    "approve_session_wait",
    "deny_session_wait",
    "update_session_runtime_policy",
    "control_session",
    "update_session_context",
    "manage_session_memory",
    "manage_session_skills",
)


def test_agent_user_service_does_not_reintroduce_session_scoped_compat_methods() -> None:
    service = AgentUserService()
    for name in FORBIDDEN_AGENT_SESSION_METHODS:
        assert not hasattr(service, name), f"AgentUserService must not expose {name}()"


def test_agent_application_service_does_not_reintroduce_session_scoped_compat_methods() -> None:
    service = AgentApplicationService()
    for name in FORBIDDEN_AGENT_SESSION_METHODS:
        assert not hasattr(service, name), f"AgentApplicationService must not expose {name}()"
