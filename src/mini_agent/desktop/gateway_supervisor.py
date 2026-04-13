"""DesktopUI gateway attach/start supervision."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mini_agent.dev import RuntimeStackManager, RuntimeStackStatus
from mini_agent.dev.studio_dev_manager import is_port_listening


@dataclass(slots=True)
class DesktopGatewayConnection:
    """Resolved local gateway connection for DesktopUI."""

    host: str
    port: int
    base_url: str
    workspace: Path
    managed: bool
    started_here: bool
    qqbot_enabled: bool = False
    qqbot_running: bool = False
    note: str = ""


class DesktopGatewaySupervisor:
    """Attach to or start the local gateway for DesktopUI."""

    def __init__(
        self,
        *,
        source_root: Path,
        repo_root: Path | None = None,
        stack_manager: RuntimeStackManager | None = None,
    ) -> None:
        self.source_root = source_root.resolve()
        self.repo_root = (repo_root or self.source_root.parent).resolve()
        self._stack_manager = stack_manager or RuntimeStackManager(
            source_root=self.source_root,
            repo_root=self.repo_root,
        )
        self._started_managed_gateway = False

    def ensure_gateway_running(
        self,
        *,
        host: str,
        port: int,
        workspace: Path,
        approval_profile: str | None,
        access_level: str | None,
        startup_timeout: float = 20.0,
        attach_only: bool = False,
    ) -> DesktopGatewayConnection:
        """Attach to an existing gateway or start a managed one."""
        requested_workspace = workspace.resolve()
        requested_workspace.mkdir(parents=True, exist_ok=True)

        managed_status = self._stack_manager.status()
        if managed_status.gateway_running:
            if not is_port_listening(managed_status.host, managed_status.gateway_port):
                raise RuntimeError(
                    "Managed runtime stack reports a live gateway process, but the HTTP endpoint "
                    "is not reachable. Run `mini-agent stack status` / `mini-agent stack down` "
                    "to recover it before launching DesktopUI."
                )
            return self._from_runtime_status(
                managed_status,
                started_here=False,
                note=self._build_attach_note(
                    managed_status=managed_status,
                    requested_host=host,
                    requested_port=port,
                ),
            )

        if is_port_listening(host, port):
            return DesktopGatewayConnection(
                host=host,
                port=port,
                base_url=f"http://{host}:{port}",
                workspace=requested_workspace,
                managed=False,
                started_here=False,
                note="Attached to an already running local gateway.",
            )

        if attach_only:
            raise RuntimeError(
                f"No running gateway was found at http://{host}:{port}, and attach-only mode was requested."
            )

        started = self._stack_manager.up(
            host=host,
            gateway_port=port,
            workspace=requested_workspace,
            qqbot=False,
            approval_profile=approval_profile,
            access_level=access_level,
            startup_timeout=startup_timeout,
        )
        self._started_managed_gateway = True
        note = "Started a managed local gateway for DesktopUI."
        if started.message:
            note = f"{note} {started.message}".strip()
        return self._from_runtime_status(started, started_here=True, note=note)

    def managed_log_tail(self, *, lines: int = 80) -> str:
        """Read managed gateway log tail for diagnostics panes."""
        payload = self._stack_manager.read_logs(target="gateway", lines=max(1, int(lines)))
        return str(payload.get("gateway") or "")

    def shutdown_managed_gateway(self, *, force: bool = False) -> RuntimeStackStatus | None:
        """Stop the gateway only if this supervisor started it."""
        if not self._started_managed_gateway:
            return None
        status = self._stack_manager.down(force=force)
        self._started_managed_gateway = False
        return status

    @staticmethod
    def _from_runtime_status(
        status: RuntimeStackStatus,
        *,
        started_here: bool,
        note: str,
    ) -> DesktopGatewayConnection:
        return DesktopGatewayConnection(
            host=status.host,
            port=status.gateway_port,
            base_url=f"http://{status.host}:{status.gateway_port}",
            workspace=status.workspace,
            managed=True,
            started_here=started_here,
            qqbot_enabled=status.qqbot_enabled,
            qqbot_running=status.qqbot_running,
            note=note,
        )

    @staticmethod
    def _build_attach_note(
        *,
        managed_status: RuntimeStackStatus,
        requested_host: str,
        requested_port: int,
    ) -> str:
        actual = f"{managed_status.host}:{managed_status.gateway_port}"
        requested = f"{requested_host}:{requested_port}"
        if actual == requested:
            return "Attached to the managed local gateway from the runtime stack."
        return (
            "Attached to the managed local gateway from the runtime stack "
            f"at {actual}; requested {requested} was ignored."
        )
