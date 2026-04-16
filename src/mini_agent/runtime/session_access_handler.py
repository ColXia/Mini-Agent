"""Session acquisition / restore selection extracted from the runtime manager."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from mini_agent.session import DEFAULT_SESSION_ID, is_default_session_id

if TYPE_CHECKING:
    from datetime import datetime

    from mini_agent.runtime.session_state import MainAgentSessionState


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(frozen=True, slots=True)
class RuntimeSessionAccessCommand:
    session_id: str | None
    workspace_dir: Path
    surface: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None
    session_title_hint: str | None = None


@dataclass(slots=True)
class RuntimeSessionAccessPlan:
    action: str
    workspace_dir: Path
    session_id: str | None = None
    is_default_session: bool = False
    active_session: "MainAgentSessionState | None" = None
    persisted_record: dict[str, Any] | None = None
    surface_provided: bool = False
    normalized_surface: str = ""
    normalized_channel_type: str | None = None
    normalized_conversation_id: str | None = None
    normalized_sender_id: str | None = None
    normalized_title_hint: str = ""
    apply_title_hint_if_missing: bool = False


@dataclass(slots=True)
class RuntimeSessionAccessHandler:
    normalize_surface: Callable[[str | None], str]
    normalize_channel_type: Callable[[str | None], str | None]
    same_workspace: Callable[[Path, Path], bool]
    resolve_main_workspace: Callable[[Path], Path] | None = None

    def build_plan(
        self,
        command: RuntimeSessionAccessCommand,
        *,
        now_utc: "datetime",
        team_mode: bool,
        prepare_environment: Callable[[Path, "datetime"], None],
        load_active_session: Callable[[str], "MainAgentSessionState | None"],
        find_latest_active_session: Callable[[Path], "MainAgentSessionState | None"],
        load_persisted_record: Callable[[str], dict[str, Any] | None],
        find_latest_persisted_record: Callable[[Path], dict[str, Any] | None],
        raise_workspace_mismatch: Callable[[], None],
        enforce_capacity: Callable[[], None],
        allocate_session_id: Callable[[], str],
    ) -> RuntimeSessionAccessPlan:
        if self.resolve_main_workspace is None:
            return self._build_legacy_plan(
                command,
                now_utc=now_utc,
                team_mode=team_mode,
                prepare_environment=prepare_environment,
                load_active_session=load_active_session,
                find_latest_active_session=find_latest_active_session,
                load_persisted_record=load_persisted_record,
                find_latest_persisted_record=find_latest_persisted_record,
                raise_workspace_mismatch=raise_workspace_mismatch,
                enforce_capacity=enforce_capacity,
                allocate_session_id=allocate_session_id,
            )

        requested_session_id = _safe_text(command.session_id) or None
        access_default_session = requested_session_id is None or is_default_session_id(requested_session_id)
        target_workspace = (
            self.resolve_main_workspace(command.workspace_dir)
            if access_default_session
            else command.workspace_dir
        )
        prepare_environment(target_workspace, now_utc)

        surface_provided = command.surface is not None
        normalized_surface = self.normalize_surface(command.surface) if surface_provided else ""
        normalized_channel_type = self.normalize_channel_type(command.channel_type)
        normalized_conversation_id = _safe_text(command.conversation_id) or None
        normalized_sender_id = _safe_text(command.sender_id) or None
        normalized_title_hint = _safe_text(command.session_title_hint)

        if requested_session_id:
            existing = load_active_session(requested_session_id)
            if existing is not None:
                if not self.same_workspace(existing.workspace_dir, target_workspace):
                    raise_workspace_mismatch()
                return RuntimeSessionAccessPlan(
                    action="reuse_active",
                    workspace_dir=target_workspace,
                    session_id=requested_session_id,
                    is_default_session=access_default_session,
                    active_session=existing,
                    surface_provided=surface_provided,
                    normalized_surface=normalized_surface,
                    normalized_channel_type=normalized_channel_type,
                    normalized_conversation_id=normalized_conversation_id,
                    normalized_sender_id=normalized_sender_id,
                    normalized_title_hint=normalized_title_hint,
                )

        if requested_session_id:
            persisted = load_persisted_record(requested_session_id)
            if persisted is not None:
                persisted_workspace = Path(str(persisted.get("workspace_dir", "."))).expanduser().resolve()
                if not self.same_workspace(persisted_workspace, target_workspace):
                    raise_workspace_mismatch()
                return RuntimeSessionAccessPlan(
                    action="restore_persisted",
                    workspace_dir=target_workspace,
                    session_id=requested_session_id,
                    is_default_session=access_default_session,
                    persisted_record=persisted,
                    surface_provided=surface_provided,
                    normalized_surface=normalized_surface,
                    normalized_channel_type=normalized_channel_type,
                    normalized_conversation_id=normalized_conversation_id,
                    normalized_sender_id=normalized_sender_id,
                    normalized_title_hint=normalized_title_hint,
                )

        if requested_session_id is None:
            default_session_id = DEFAULT_SESSION_ID
            default_active = load_active_session(default_session_id)
            if default_active is not None:
                if not self.same_workspace(default_active.workspace_dir, target_workspace):
                    raise_workspace_mismatch()
                return RuntimeSessionAccessPlan(
                    action="reuse_active",
                    workspace_dir=target_workspace,
                    session_id=default_session_id,
                    is_default_session=True,
                    active_session=default_active,
                    surface_provided=surface_provided,
                    normalized_surface=normalized_surface,
                    normalized_channel_type=normalized_channel_type,
                    normalized_conversation_id=normalized_conversation_id,
                    normalized_sender_id=normalized_sender_id,
                    normalized_title_hint="",
                )
            persisted_default = load_persisted_record(default_session_id)
            if persisted_default is not None:
                persisted_workspace = Path(str(persisted_default.get("workspace_dir", "."))).expanduser().resolve()
                if not self.same_workspace(persisted_workspace, target_workspace):
                    raise_workspace_mismatch()
                return RuntimeSessionAccessPlan(
                    action="restore_persisted",
                    workspace_dir=target_workspace,
                    session_id=default_session_id,
                    is_default_session=True,
                    persisted_record=persisted_default,
                    surface_provided=surface_provided,
                    normalized_surface=normalized_surface,
                    normalized_channel_type=normalized_channel_type,
                    normalized_conversation_id=normalized_conversation_id,
                    normalized_sender_id=normalized_sender_id,
                    normalized_title_hint="",
                )

        if team_mode and requested_session_id and not access_default_session:
            enforce_capacity()

        return RuntimeSessionAccessPlan(
            action="create_new",
            workspace_dir=target_workspace,
            session_id=(
                DEFAULT_SESSION_ID
                if access_default_session
                else (requested_session_id or allocate_session_id())
            ),
            is_default_session=access_default_session,
            surface_provided=surface_provided,
            normalized_surface=normalized_surface,
            normalized_channel_type=normalized_channel_type,
            normalized_conversation_id=normalized_conversation_id,
            normalized_sender_id=normalized_sender_id,
            normalized_title_hint="" if access_default_session else normalized_title_hint,
        )

    def _build_legacy_plan(
        self,
        command: RuntimeSessionAccessCommand,
        *,
        now_utc: "datetime",
        team_mode: bool,
        prepare_environment: Callable[[Path, "datetime"], None],
        load_active_session: Callable[[str], "MainAgentSessionState | None"],
        find_latest_active_session: Callable[[Path], "MainAgentSessionState | None"],
        load_persisted_record: Callable[[str], dict[str, Any] | None],
        find_latest_persisted_record: Callable[[Path], dict[str, Any] | None],
        raise_workspace_mismatch: Callable[[], None],
        enforce_capacity: Callable[[], None],
        allocate_session_id: Callable[[], str],
    ) -> RuntimeSessionAccessPlan:
        prepare_environment(command.workspace_dir, now_utc)

        requested_session_id = _safe_text(command.session_id) or None
        surface_provided = command.surface is not None
        normalized_surface = self.normalize_surface(command.surface) if surface_provided else ""
        normalized_channel_type = self.normalize_channel_type(command.channel_type)
        normalized_conversation_id = _safe_text(command.conversation_id) or None
        normalized_sender_id = _safe_text(command.sender_id) or None
        normalized_title_hint = _safe_text(command.session_title_hint)

        if requested_session_id:
            existing = load_active_session(requested_session_id)
            if existing is not None:
                if not self.same_workspace(existing.workspace_dir, command.workspace_dir):
                    raise_workspace_mismatch()
                return RuntimeSessionAccessPlan(
                    action="reuse_active",
                    workspace_dir=command.workspace_dir,
                    session_id=requested_session_id,
                    active_session=existing,
                    surface_provided=surface_provided,
                    normalized_surface=normalized_surface,
                    normalized_channel_type=normalized_channel_type,
                    normalized_conversation_id=normalized_conversation_id,
                    normalized_sender_id=normalized_sender_id,
                    normalized_title_hint=normalized_title_hint,
                )

        if team_mode and not requested_session_id:
            workspace_existing = find_latest_active_session(command.workspace_dir)
            if workspace_existing is not None:
                return RuntimeSessionAccessPlan(
                    action="reuse_active",
                    workspace_dir=command.workspace_dir,
                    session_id=workspace_existing.session_id,
                    active_session=workspace_existing,
                    surface_provided=surface_provided,
                    normalized_surface=normalized_surface,
                    normalized_channel_type=normalized_channel_type,
                    normalized_conversation_id=normalized_conversation_id,
                    normalized_sender_id=normalized_sender_id,
                    normalized_title_hint=normalized_title_hint,
                )

        if requested_session_id:
            persisted = load_persisted_record(requested_session_id)
            if persisted is not None:
                persisted_workspace = Path(str(persisted.get("workspace_dir", "."))).expanduser().resolve()
                if not self.same_workspace(persisted_workspace, command.workspace_dir):
                    raise_workspace_mismatch()
                return RuntimeSessionAccessPlan(
                    action="restore_persisted",
                    workspace_dir=command.workspace_dir,
                    session_id=requested_session_id,
                    persisted_record=persisted,
                    surface_provided=surface_provided,
                    normalized_surface=normalized_surface,
                    normalized_channel_type=normalized_channel_type,
                    normalized_conversation_id=normalized_conversation_id,
                    normalized_sender_id=normalized_sender_id,
                    normalized_title_hint=normalized_title_hint,
                )

        if not requested_session_id:
            persisted_latest = find_latest_persisted_record(command.workspace_dir)
            if persisted_latest is not None:
                return RuntimeSessionAccessPlan(
                    action="restore_persisted",
                    workspace_dir=command.workspace_dir,
                    session_id=_safe_text(persisted_latest.get("session_id")) or None,
                    persisted_record=persisted_latest,
                    surface_provided=surface_provided,
                    normalized_surface=normalized_surface,
                    normalized_channel_type=normalized_channel_type,
                    normalized_conversation_id=normalized_conversation_id,
                    normalized_sender_id=normalized_sender_id,
                    normalized_title_hint=normalized_title_hint,
                    apply_title_hint_if_missing=bool(normalized_title_hint),
                )

        if team_mode:
            enforce_capacity()

        return RuntimeSessionAccessPlan(
            action="create_new",
            workspace_dir=command.workspace_dir,
            session_id=requested_session_id or allocate_session_id(),
            surface_provided=surface_provided,
            normalized_surface=normalized_surface,
            normalized_channel_type=normalized_channel_type,
            normalized_conversation_id=normalized_conversation_id,
            normalized_sender_id=normalized_sender_id,
            normalized_title_hint=normalized_title_hint,
        )


__all__ = [
    "RuntimeSessionAccessCommand",
    "RuntimeSessionAccessHandler",
    "RuntimeSessionAccessPlan",
]
