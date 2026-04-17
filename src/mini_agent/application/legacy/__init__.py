"""Legacy/transitional application entrypoints."""

from .session_runtime_compat import (
    SessionAgentCompatibilityAdapter,
    SessionModelSelectionCompatibilityAdapter,
    SessionTaskCompatibilityAdapter,
    UnavailableRunRuntimeAdapter,
)
from .session_service import SessionApplicationService
from .session_service_assembly import (
    RuntimeBackedSessionApplicationAssembly,
    assemble_runtime_backed_session_application,
    assemble_typed_session_application,
    build_runtime_backed_session_service,
    build_typed_session_service,
)

__all__ = [
    "RuntimeBackedSessionApplicationAssembly",
    "SessionAgentCompatibilityAdapter",
    "SessionApplicationService",
    "SessionModelSelectionCompatibilityAdapter",
    "SessionTaskCompatibilityAdapter",
    "UnavailableRunRuntimeAdapter",
    "assemble_runtime_backed_session_application",
    "assemble_typed_session_application",
    "build_runtime_backed_session_service",
    "build_typed_session_service",
]
