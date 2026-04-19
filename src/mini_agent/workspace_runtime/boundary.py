"""Workspace-root boundary helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from mini_agent.runtime.support.workspace_path_utils import (
    same_workspace_path,
    workspace_path_key,
)
from mini_agent.workspace.domain import WorkspaceKind, WorkspaceManifest, WorkspaceRecord


def _normalize_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve(strict=False)


def _is_relative_to(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _item_value(item: Any, field: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(field, default)
    return getattr(item, field, default)


@dataclass(frozen=True, slots=True)
class WorkspaceBoundary:
    """Normalized workspace root and containment checks."""

    root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", _normalize_path(self.root))

    def resolve_path(self, value: str | Path) -> Path:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = self.root / candidate
        return candidate.resolve(strict=False)

    def contains_path(self, value: str | Path) -> bool:
        return _is_relative_to(self.resolve_path(value), self.root)

    def relative_path(self, value: str | Path) -> Path | None:
        resolved = self.resolve_path(value)
        if not _is_relative_to(resolved, self.root):
            return None
        return resolved.relative_to(self.root)


@dataclass(slots=True)
class MainAgentWorkspaceRuntimeAdapter:
    """Expose workspace-oriented runtime facts above the session host runtime."""

    runtime_manager: Any
    config_loader: Callable[[], Any]
    repo_root: Path
    _selected_workspace_dir: Path | None = field(default=None, init=False, repr=False)

    async def list_workspaces(self) -> list[dict[str, Any]]:
        workspaces = await self._collect_workspaces()
        return sorted(
            workspaces,
            key=lambda item: (
                not bool(item.get("active")),
                not bool(item.get("default")),
                str(item.get("workspace_dir", "")).lower(),
            ),
        )

    async def get_workspace(self, workspace_id: str) -> dict[str, Any]:
        descriptor = await self._resolve_workspace_descriptor(workspace_id)
        if descriptor is None:
            raise LookupError(f"Workspace not found: {workspace_id}")
        return descriptor

    async def get_active_workspace(self) -> dict[str, Any]:
        return await self._resolve_active_workspace_descriptor()

    async def switch_workspace(self, workspace_id: str) -> dict[str, Any]:
        target = await self._resolve_workspace_path(workspace_id)
        validator = getattr(self.runtime_manager, "validate_workspace", None)
        if callable(validator):
            validator(target)
        self._selected_workspace_dir = target
        return await self._descriptor_for_path(target)

    async def get_workspace_runtime_summary(self, workspace_id: str | None = None) -> dict[str, Any]:
        descriptor = (
            await self._resolve_workspace_descriptor(workspace_id)
            if workspace_id is not None
            else await self._resolve_active_workspace_descriptor()
        )
        if descriptor is None:
            raise LookupError(f"Workspace not found: {workspace_id}")

        runtime_diagnostics = await self.runtime_manager.get_runtime_diagnostics()
        payload: dict[str, Any] = dict(descriptor)
        payload["runtime_policy"] = {
            "mode": _item_value(runtime_diagnostics, "mode"),
            "workspace_application_required": bool(
                _item_value(runtime_diagnostics, "workspace_application_required", True)
            ),
            "main_workspace_dir": _item_value(runtime_diagnostics, "main_workspace_dir"),
        }
        try:
            from mini_agent.workspace_runtime.workspace_executor import (
                build_direct_workspace_runtime_bundle,
            )

            bundle = build_direct_workspace_runtime_bundle(
                self.config_loader(),
                Path(descriptor["workspace_dir"]),
            )
            payload["runtime"] = bundle.to_summary()
        except Exception as exc:
            payload["runtime"] = None
            payload["runtime_error"] = f"{type(exc).__name__}: {exc}"
        return payload

    async def _resolve_workspace_descriptor(self, workspace_id: str | None) -> dict[str, Any] | None:
        if workspace_id is None:
            return await self._resolve_active_workspace_descriptor()
        target = await self._resolve_workspace_path(workspace_id)
        return await self._descriptor_for_path(target)

    async def _resolve_active_workspace_descriptor(self) -> dict[str, Any]:
        active_workspace = await self._resolve_active_workspace_path()
        return await self._descriptor_for_path(active_workspace)

    async def _resolve_active_workspace_path(self) -> Path:
        if self._selected_workspace_dir is not None:
            return self._selected_workspace_dir

        sessions = await self.runtime_manager.list_sessions(workspace_dir=None, shared_only=False)
        busy_candidate: Path | None = None
        latest_candidate: tuple[str, Path] | None = None
        for summary in sessions:
            workspace_dir = self._summary_workspace_path(summary)
            if workspace_dir is None:
                continue
            updated_at = _safe_text(_item_value(summary, "updated_at"))
            if bool(_item_value(summary, "busy", False)) and busy_candidate is None:
                busy_candidate = workspace_dir
            if latest_candidate is None or updated_at > latest_candidate[0]:
                latest_candidate = (updated_at, workspace_dir)

        if busy_candidate is not None:
            return busy_candidate
        if latest_candidate is not None:
            return latest_candidate[1]
        return await self._main_workspace_dir()

    async def _resolve_workspace_path(self, workspace_id: str) -> Path:
        normalized_input = _safe_text(workspace_id)
        if not normalized_input:
            return await self._main_workspace_dir()

        known = await self._collect_workspaces()
        for item in known:
            if normalized_input in {
                str(item.get("workspace_id", "")),
                str(item.get("workspace_dir", "")),
            }:
                return Path(str(item["workspace_dir"])).expanduser().resolve()

        candidate = Path(normalized_input).expanduser()
        if not candidate.is_absolute():
            candidate = (self.repo_root / candidate).resolve()
        else:
            candidate = candidate.resolve()
        return candidate

    async def _collect_workspaces(self) -> list[dict[str, Any]]:
        main_workspace = await self._main_workspace_dir()
        active_workspace = await self._resolve_active_workspace_path()
        sessions = await self.runtime_manager.list_sessions(workspace_dir=None, shared_only=False)

        grouped: dict[str, WorkspaceRecord] = {}

        def ensure(path: Path) -> WorkspaceRecord:
            key = workspace_path_key(path)
            record = grouped.get(key)
            if record is None:
                record = self._build_workspace_record(
                    path=path,
                    main_workspace=main_workspace,
                    active_workspace=active_workspace,
                )
                grouped[key] = record
            return record

        ensure(main_workspace)

        for summary in sessions:
            workspace_dir = self._summary_workspace_path(summary)
            if workspace_dir is None:
                continue
            grouped[workspace_path_key(workspace_dir)] = ensure(workspace_dir).observe_session(
                shared=bool(_item_value(summary, "shared", False)),
                busy=bool(_item_value(summary, "busy", False)),
                is_default=bool(_item_value(summary, "is_default", False)),
                updated_at=_safe_text(_item_value(summary, "updated_at")),
            )

        return [record.to_summary_dict() for record in grouped.values()]

    async def _descriptor_for_path(self, path: Path) -> dict[str, Any]:
        for item in await self._collect_workspaces():
            candidate = Path(str(item["workspace_dir"])).expanduser().resolve()
            if same_workspace_path(candidate, path):
                return dict(item)

        main_workspace = await self._main_workspace_dir()
        active_workspace = await self._resolve_active_workspace_path()
        return self._build_workspace_record(
            path=path,
            main_workspace=main_workspace,
            active_workspace=active_workspace,
        ).to_summary_dict()

    async def _main_workspace_dir(self) -> Path:
        diagnostics = await self.runtime_manager.get_runtime_diagnostics()
        raw_main_workspace = _safe_text(_item_value(diagnostics, "main_workspace_dir"))
        if raw_main_workspace:
            return Path(raw_main_workspace).expanduser().resolve()
        return self.repo_root.resolve()

    def _build_workspace_record(
        self,
        *,
        path: Path,
        main_workspace: Path,
        active_workspace: Path,
    ) -> WorkspaceRecord:
        manifest = self._build_workspace_manifest(path=path, main_workspace=main_workspace)
        record = WorkspaceRecord.from_manifest(
            manifest,
            default=manifest.kind is WorkspaceKind.DEFAULT,
        )
        if same_workspace_path(path, active_workspace):
            record = record.mark_active(switched=self._is_switched_workspace(path, main_workspace))
        return record

    @staticmethod
    def _build_workspace_manifest(*, path: Path, main_workspace: Path) -> WorkspaceManifest:
        if same_workspace_path(path, main_workspace):
            return WorkspaceManifest.default_workspace(path)
        return WorkspaceManifest.project_workspace(path)

    def _is_switched_workspace(self, path: Path, main_workspace: Path) -> bool:
        if self._selected_workspace_dir is None:
            return False
        return same_workspace_path(path, self._selected_workspace_dir) and not same_workspace_path(
            path,
            main_workspace,
        )

    @staticmethod
    def _summary_workspace_path(summary: Any) -> Path | None:
        raw_workspace = _safe_text(_item_value(summary, "workspace_dir"))
        if not raw_workspace:
            return None
        try:
            return Path(raw_workspace).expanduser().resolve()
        except Exception:
            return None


__all__ = ["MainAgentWorkspaceRuntimeAdapter", "WorkspaceBoundary"]
