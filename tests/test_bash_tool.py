"""Test cases for Bash Tool."""

import asyncio
import platform
from pathlib import Path
from types import SimpleNamespace

import pytest

from mini_agent.agent_core.execution.sandbox import SandboxBackend, SandboxManager
from mini_agent.agent_core.execution.sandbox.windows import SandboxTransformResult
from mini_agent.config import AgentConfig, Config, LLMConfig, SecurityConfig, ToolsConfig
from mini_agent.runtime.support.tooling import resolve_runtime_policy
from mini_agent.security.policy import BashCommandPolicyDecision
from mini_agent.tools.bash_tool import BackgroundShellManager, BashKillTool, BashOutputTool, BashTool
from mini_agent.workspace_runtime.adapters import DirectWorkspaceExecutor
from mini_agent.workspace_runtime.mutation_ledger import InMemoryMutationLedger


@pytest.mark.asyncio
async def test_foreground_command():
    """Test executing a simple foreground command."""
    print("\n=== Testing Foreground Command ===")

    bash_tool = BashTool()
    result = await bash_tool.execute(command="echo 'Hello from foreground'")

    assert result.success
    assert "Hello from foreground" in result.stdout
    assert result.exit_code == 0
    print(f"Output: {result.content}")


@pytest.mark.asyncio
async def test_foreground_command_with_stderr():
    """Test command that outputs to both stdout and stderr."""
    print("\n=== Testing Stdout/Stderr Separation ===")

    bash_tool = BashTool()
    if platform.system() == "Windows":
        command = "Write-Output 'stdout message'; [Console]::Error.WriteLine('stderr message')"
    else:
        command = "echo 'stdout message' && echo 'stderr message' >&2"
    result = await bash_tool.execute(command=command)

    assert result.success
    assert "stdout message" in result.stdout
    assert "stderr message" in result.stderr
    print(f"Stdout: {result.stdout}")
    print(f"Stderr: {result.stderr}")


@pytest.mark.asyncio
async def test_command_failure():
    """Test command that fails with non-zero exit code."""
    print("\n=== Testing Command Failure ===")

    bash_tool = BashTool()
    result = await bash_tool.execute(command="ls /nonexistent_directory_12345")

    assert not result.success
    assert result.exit_code != 0
    assert result.error is not None
    print(f"Error: {result.error}")


@pytest.mark.asyncio
async def test_command_timeout():
    """Test command timeout."""
    print("\n=== Testing Command Timeout ===")

    bash_tool = BashTool()
    result = await bash_tool.execute(command="sleep 10", timeout=1)

    assert not result.success
    assert "timed out" in result.error.lower()
    assert result.exit_code == -1
    print(f"Timeout error: {result.error}")


@pytest.mark.asyncio
async def test_cancel_running_interrupts_foreground_process():
    """Test best-effort cancellation for running foreground command."""
    bash_tool = BashTool()
    if platform.system() == "Windows":
        command = "Start-Sleep -Seconds 30"
    else:
        command = "sleep 30"

    run_task = asyncio.create_task(bash_tool.execute(command=command, timeout=120))
    await asyncio.sleep(0.3)

    cancelled = await bash_tool.cancel_running(reason="test_interrupt")
    result = await asyncio.wait_for(run_task, timeout=5)

    assert cancelled is True
    assert result.success is False
    assert result.error is not None
    assert "interrupted" in result.error.lower()


@pytest.mark.asyncio
async def test_background_command():
    """Test running a command in the background."""
    print("\n=== Testing Background Command ===")

    bash_tool = BashTool()
    result = await bash_tool.execute(
        command="for i in 1 2 3; do echo 'Line '$i; sleep 0.5; done", run_in_background=True
    )

    assert result.success
    assert result.bash_id is not None
    assert "Background command started" in result.stdout

    bash_id = result.bash_id
    print(f"Background command started with ID: {bash_id}")

    # Wait a bit for output
    await asyncio.sleep(1)

    # Check output
    bash_output_tool = BashOutputTool()
    output_result = await bash_output_tool.execute(bash_id=bash_id)

    assert output_result.success
    print(f"Output:\n{output_result.content}")

    # Clean up - terminate the background process
    bash_kill_tool = BashKillTool()
    kill_result = await bash_kill_tool.execute(bash_id=bash_id)
    assert kill_result.success
    print("Background process terminated")


@pytest.mark.asyncio
async def test_bash_output_monitoring():
    """Test monitoring background command output."""
    print("\n=== Testing Output Monitoring ===")

    bash_tool = BashTool()

    # Start background command
    result = await bash_tool.execute(
        command="for i in 1 2 3 4 5; do echo 'Line '$i; sleep 0.5; done", run_in_background=True
    )

    assert result.success
    bash_id = result.bash_id
    print(f"Started background command: {bash_id}")

    bash_output_tool = BashOutputTool()

    # Check output multiple times (incremental output)
    for i in range(3):
        await asyncio.sleep(1)
        output_result = await bash_output_tool.execute(bash_id=bash_id)
        assert output_result.success
        print(f"\n--- Check #{i + 1} ---")
        print(f"Output:\n{output_result.content}")

    # Clean up
    bash_kill_tool = BashKillTool()
    await bash_kill_tool.execute(bash_id=bash_id)


@pytest.mark.asyncio
async def test_bash_output_with_filter():
    """Test bash_output with regex filter."""
    print("\n=== Testing Output Filter ===")

    bash_tool = BashTool()

    # Start background command
    result = await bash_tool.execute(
        command="for i in 1 2 3 4 5; do echo 'Line '$i; sleep 0.3; done", run_in_background=True
    )

    assert result.success
    bash_id = result.bash_id

    # Wait for some output
    await asyncio.sleep(2)

    # Get filtered output (only lines with "Line 2" or "Line 4")
    bash_output_tool = BashOutputTool()
    output_result = await bash_output_tool.execute(bash_id=bash_id, filter_str="Line [24]")

    assert output_result.success
    print(f"Filtered output:\n{output_result.content}")

    # Clean up
    bash_kill_tool = BashKillTool()
    await bash_kill_tool.execute(bash_id=bash_id)


@pytest.mark.asyncio
async def test_bash_kill():
    """Test terminating a background command."""
    print("\n=== Testing Bash Kill ===")

    bash_tool = BashTool()

    # Start a long-running background command
    result = await bash_tool.execute(command="sleep 100", run_in_background=True)

    assert result.success
    bash_id = result.bash_id
    print(f"Started long-running command: {bash_id}")

    # Verify it's running
    await asyncio.sleep(0.5)
    bg_shell = BackgroundShellManager.get(bash_id)
    assert bg_shell is not None
    assert bg_shell.status == "running"

    # Kill it
    bash_kill_tool = BashKillTool()
    kill_result = await bash_kill_tool.execute(bash_id=bash_id)

    assert kill_result.success
    # exit_code -15 means terminated by SIGTERM
    assert kill_result.exit_code == -15 or kill_result.bash_id == bash_id
    print(f"Kill result:\n{kill_result.content}")

    # Verify it's removed from manager
    bg_shell = BackgroundShellManager.get(bash_id)
    assert bg_shell is None


@pytest.mark.asyncio
async def test_bash_kill_nonexistent():
    """Test killing a non-existent bash process."""
    print("\n=== Testing Kill Non-existent Process ===")

    bash_kill_tool = BashKillTool()
    result = await bash_kill_tool.execute(bash_id="nonexistent123")

    assert not result.success
    assert "not found" in result.error.lower()
    print(f"Expected error: {result.error}")


@pytest.mark.asyncio
async def test_bash_output_nonexistent():
    """Test getting output from non-existent bash process."""
    print("\n=== Testing Output From Non-existent Process ===")

    bash_output_tool = BashOutputTool()
    result = await bash_output_tool.execute(bash_id="nonexistent123")

    assert not result.success
    assert "not found" in result.error.lower()
    print(f"Expected error: {result.error}")


@pytest.mark.asyncio
async def test_multiple_background_commands():
    """Test running multiple background commands simultaneously."""
    print("\n=== Testing Multiple Background Commands ===")

    bash_tool = BashTool()

    # Start multiple background commands
    bash_ids = []
    for i in range(3):
        result = await bash_tool.execute(
            command=f"for j in 1 2 3; do echo 'Command {i + 1} Line '$j; sleep 0.5; done", run_in_background=True
        )
        assert result.success
        bash_ids.append(result.bash_id)
        print(f"Started command {i + 1}: {result.bash_id}")

    # Wait and check all commands
    await asyncio.sleep(1)

    bash_output_tool = BashOutputTool()
    for bash_id in bash_ids:
        output_result = await bash_output_tool.execute(bash_id=bash_id)
        assert output_result.success
        print(f"\nOutput for {bash_id}:\n{output_result.content[:100]}...")

    # Clean up all
    bash_kill_tool = BashKillTool()
    for bash_id in bash_ids:
        await bash_kill_tool.execute(bash_id=bash_id)

    print("All background processes cleaned up")


@pytest.mark.asyncio
async def test_timeout_validation():
    """Test timeout parameter validation."""
    print("\n=== Testing Timeout Validation ===")

    bash_tool = BashTool()

    # Test with timeout > 600 (should be capped to 600)
    result = await bash_tool.execute(command="echo 'test'", timeout=1000)
    assert result.success
    print("Timeout > 600 handled correctly")

    # Test with timeout < 1 (should be set to 120)
    result = await bash_tool.execute(command="echo 'test'", timeout=0)
    assert result.success
    print("Timeout < 1 handled correctly")


@pytest.mark.asyncio
async def test_bash_tool_applies_sandbox_transform(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    class _Sandbox:
        def transform(self, command: str, *, cwd=None):  # noqa: ANN001
            captured["incoming_command"] = command
            captured["incoming_cwd"] = cwd
            return SandboxTransformResult(
                command="echo transformed-command",
                cwd=str(tmp_path / "sandbox-cwd"),
                env_overrides={"MINI_AGENT_SANDBOX_BACKEND": "fake", "CUSTOM_FLAG": "1"},
                metadata={"backend": "fake"},
            )

    class _FakeProcess:
        def __init__(self) -> None:
            self.returncode = 0

        async def communicate(self):
            return (b"ok", b"")

        def kill(self) -> None:
            self.returncode = -9

        async def wait(self) -> int:
            return self.returncode

    async def _fake_create_subprocess_shell(command, **kwargs):  # noqa: ANN001
        captured["shell_command"] = command
        captured["kwargs"] = kwargs
        return _FakeProcess()

    async def _fake_create_subprocess_exec(*command, **kwargs):  # noqa: ANN001
        captured["shell_command"] = list(command)
        captured["kwargs"] = kwargs
        return _FakeProcess()

    if platform.system() == "Windows":
        monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)
    else:
        monkeypatch.setattr(asyncio, "create_subprocess_shell", _fake_create_subprocess_shell)

    bash_tool = BashTool(
        workspace_dir=str(tmp_path),
        sandbox_manager=_Sandbox(),
    )
    result = await bash_tool.execute(command="echo original-command")

    assert result.success is True
    assert captured["incoming_command"] == "echo original-command"
    assert captured["incoming_cwd"] == str(tmp_path)
    kwargs = captured["kwargs"]
    assert kwargs["cwd"] == str((tmp_path / "sandbox-cwd"))
    assert kwargs["env"]["MINI_AGENT_SANDBOX_BACKEND"] == "fake"
    assert kwargs["env"]["CUSTOM_FLAG"] == "1"
    if platform.system() == "Windows":
        assert captured["shell_command"][-1] == "echo transformed-command"
    else:
        assert captured["shell_command"] == "echo transformed-command"


@pytest.mark.asyncio
async def test_bash_tool_uses_workspace_runtime_execution_root(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}
    ledger = InMemoryMutationLedger()
    workspace_executor = DirectWorkspaceExecutor(tmp_path, mutation_ledger=ledger)

    class _FakeProcess:
        def __init__(self) -> None:
            self.returncode = 0

        async def communicate(self):
            return (b"runtime-ok", b"")

        def kill(self) -> None:
            self.returncode = -9

        async def wait(self) -> int:
            return self.returncode

    async def _fake_create_subprocess_shell(command, **kwargs):  # noqa: ANN001
        captured["shell_command"] = command
        captured["kwargs"] = kwargs
        return _FakeProcess()

    async def _fake_create_subprocess_exec(*command, **kwargs):  # noqa: ANN001
        captured["shell_command"] = list(command)
        captured["kwargs"] = kwargs
        return _FakeProcess()

    if platform.system() == "Windows":
        monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)
    else:
        monkeypatch.setattr(asyncio, "create_subprocess_shell", _fake_create_subprocess_shell)

    bash_tool = BashTool(workspace_executor=workspace_executor)
    result = await bash_tool.execute(command="echo runtime-owned")

    assert result.success is True
    kwargs = captured["kwargs"]
    assert kwargs["cwd"] == str(tmp_path.resolve())
    records = ledger.snapshot()
    assert len(records) == 1
    assert records[0].kind.value == "execute"
    assert records[0].path == tmp_path.resolve()


@pytest.mark.asyncio
async def test_bash_tool_reports_approval_requirement_for_host_access_command(tmp_path: Path):
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(),
        tools=ToolsConfig(enable_mcp=False, enable_skills=False),
        security=SecurityConfig(
            approval_profile="build",
            access_level="default",
            sandbox_mode="workspace",
        ),
    )
    policy_engine = resolve_runtime_policy(config)
    bash_tool = BashTool(workspace_dir=str(tmp_path), policy_engine=policy_engine)

    command = r"Remove-Item ..\outside\victim.txt -Force" if platform.system() == "Windows" else "rm ../outside/victim.txt"
    result = await bash_tool.execute(command=command)

    assert result.success is False
    assert "approval" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_bash_tool_skips_workspace_sandbox_when_host_access_already_approved(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    class _Policy:
        def inspect_bash_command(self, command: str, run_in_background: bool = False):  # noqa: ANN001
            captured["policy_command"] = command
            captured["policy_background"] = run_in_background
            return BashCommandPolicyDecision(
                allowed=True,
                reason="Shell command requires full-access approval.",
                requires_approval=True,
                host_access_required=True,
            )

    class _Sandbox:
        def transform(self, command: str, *, cwd=None):  # noqa: ANN001,ARG002
            raise AssertionError("workspace sandbox should be bypassed after host access approval")

    class _FakeProcess:
        def __init__(self) -> None:
            self.returncode = 0

        async def communicate(self):
            return (b"host-access-ok", b"")

        def kill(self) -> None:
            self.returncode = -9

        async def wait(self) -> int:
            return self.returncode

    async def _fake_create_subprocess_shell(command, **kwargs):  # noqa: ANN001
        captured["shell_command"] = command
        captured["kwargs"] = kwargs
        return _FakeProcess()

    async def _fake_create_subprocess_exec(*command, **kwargs):  # noqa: ANN001
        captured["shell_command"] = list(command)
        captured["kwargs"] = kwargs
        return _FakeProcess()

    if platform.system() == "Windows":
        monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)
    else:
        monkeypatch.setattr(asyncio, "create_subprocess_shell", _fake_create_subprocess_shell)

    bash_tool = BashTool(
        workspace_dir=str(tmp_path),
        policy_engine=_Policy(),
        sandbox_manager=_Sandbox(),
    )
    result = await bash_tool.execute(
        command="echo host-access",
        _mini_agent_host_access_approved=True,
    )

    assert result.success is True
    kwargs = captured["kwargs"]
    assert kwargs["cwd"] == str(tmp_path)
    assert kwargs["env"]["MINI_AGENT_HOST_ACCESS_APPROVED"] == "1"
    if platform.system() == "Windows":
        assert captured["shell_command"][-1] == "echo host-access"
    else:
        assert captured["shell_command"] == "echo host-access"


@pytest.mark.asyncio
async def test_bash_tool_uses_native_windows_sandbox_launch(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    class _FakeProcess:
        def __init__(self) -> None:
            self.returncode = 0

        async def communicate(self):
            return (b"native-ok", b"")

        def kill(self) -> None:
            self.returncode = 9

        def terminate(self) -> None:
            self.returncode = 1

        async def wait(self) -> int:
            return self.returncode

    class _Sandbox:
        def transform(self, command: str, *, cwd=None):  # noqa: ANN001
            captured["incoming_command"] = command
            captured["incoming_cwd"] = cwd
            return SandboxTransformResult(
                command="Write-Output native-path",
                cwd=str(tmp_path),
                env_overrides={"MINI_AGENT_SANDBOX_BACKEND": "windows_restricted_token"},
                metadata={"backend": "windows_restricted_token"},
            )

        def select_initial(self):
            return SimpleNamespace(backend=SandboxBackend.WINDOWS_RESTRICTED_TOKEN)

        def launch_process(self, argv, *, cwd=None, env=None, merge_stderr=False):  # noqa: ANN001
            captured["argv"] = list(argv)
            captured["cwd"] = cwd
            captured["env"] = dict(env or {})
            captured["merge_stderr"] = merge_stderr
            return _FakeProcess()

    async def _boom(*args, **kwargs):  # noqa: ANN001,ARG001
        raise AssertionError("asyncio subprocess path should not be used")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _boom)

    bash_tool = BashTool(
        workspace_dir=str(tmp_path),
        sandbox_manager=_Sandbox(),
    )
    bash_tool.is_windows = True
    result = await bash_tool.execute(command="Write-Output original")

    assert result.success is True
    assert result.stdout == "native-ok"
    assert captured["incoming_command"] == "Write-Output original"
    assert captured["cwd"] == str(tmp_path)
    assert captured["merge_stderr"] is False
    assert captured["argv"][-1] == "Write-Output native-path"


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows-only native sandbox integration")
@pytest.mark.asyncio
async def test_bash_tool_executes_via_windows_restricted_sandbox_manager(tmp_path: Path):
    manager = SandboxManager(
        workspace_dir=tmp_path,
        sandbox_mode="workspace",
        runtime_platform="Windows",
    )
    bash_tool = BashTool(
        workspace_dir=str(tmp_path),
        sandbox_manager=manager,
    )

    result = await bash_tool.execute(command="Write-Output manager-native-ok")

    assert result.success is True
    assert "manager-native-ok" in result.stdout
