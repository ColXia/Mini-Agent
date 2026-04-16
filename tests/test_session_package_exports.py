"""Session package public-surface regression tests."""

from __future__ import annotations

import mini_agent.session as session_pkg


def test_session_package_exports_only_live_owners() -> None:
    expected_exports = {
        "ConversationBindingPort",
        "ConversationBindingService",
        "ConversationBindingStore",
        "SessionDetailProjection",
        "SessionMessageProjection",
        "SessionPendingApprovalProjection",
        "SessionPersistence",
        "SessionRecoveryFeedbackService",
        "SessionRecoveryProjection",
        "SessionSummaryProjection",
        "conversation_binding_store",
    }

    assert expected_exports.issubset(set(session_pkg.__all__))
    assert "SessionState" not in session_pkg.__all__
    assert "SessionStore" not in session_pkg.__all__
    assert "session_store" not in session_pkg.__all__


def test_session_package_no_longer_exposes_legacy_store_surface() -> None:
    assert not hasattr(session_pkg, "SessionState")
    assert not hasattr(session_pkg, "SessionStore")
    assert not hasattr(session_pkg, "session_store")
