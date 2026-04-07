"""Single instance management for Mini-Agent.

This module provides functionality to ensure only one instance
of Mini-Agent is running at a time.
"""

import os
import sys
from pathlib import Path
from typing import Optional


class SingleInstanceManager:
    """Manages single instance enforcement using PID file."""

    def __init__(self, name: str = "mini-agent"):
        """Initialize single instance manager.

        Args:
            name: Instance name for PID file
        """
        self.name = name
        self.pid_file = Path.home() / ".mini-agent" / f"{name}.pid"
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)

    def check_and_lock(self) -> tuple[bool, Optional[int]]:
        """Check if another instance is running and create lock.

        Returns:
            Tuple of (is_first_instance, existing_pid)
        """
        # Check if PID file exists
        if not self.pid_file.exists():
            # No existing instance, create lock
            self._create_lock()
            return True, None

        # Read existing PID
        try:
            existing_pid = int(self.pid_file.read_text().strip())
        except (ValueError, OSError):
            # Invalid PID file, create new lock
            self._create_lock()
            return True, None

        # Check if process is still running
        if self._is_process_running(existing_pid):
            # Another instance is running
            return False, existing_pid
        else:
            # Process is dead, create new lock
            self._create_lock()
            return True, None

    def release_lock(self) -> None:
        """Release the instance lock."""
        try:
            if self.pid_file.exists():
                current_pid = os.getpid()
                try:
                    locked_pid = int(self.pid_file.read_text().strip())
                    if locked_pid == current_pid:
                        self.pid_file.unlink()
                except (ValueError, OSError):
                    # Invalid PID file, remove it
                    self.pid_file.unlink()
        except Exception:
            pass

    def _create_lock(self) -> None:
        """Create PID file lock."""
        try:
            self.pid_file.write_text(str(os.getpid()))
        except Exception as e:
            print(f"Warning: Failed to create PID file: {e}")

    def _is_process_running(self, pid: int) -> bool:
        """Check if a process with given PID is running.

        Args:
            pid: Process ID to check

        Returns:
            True if process is running
        """
        try:
            if sys.platform == "win32":
                # Windows: use tasklist
                import subprocess

                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                # Check if PID appears in output
                return str(pid) in result.stdout
            else:
                # Unix/Linux: use os.kill with signal 0
                os.kill(pid, 0)
                return True
        except (OSError, subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def get_running_instance_info(self, pid: int) -> dict:
        """Get information about running instance.

        Args:
            pid: Process ID

        Returns:
            Dict with instance information
        """
        info = {
            "pid": pid,
            "running": self._is_process_running(pid),
            "pid_file": str(self.pid_file),
        }

        if sys.platform == "win32" and info["running"]:
            try:
                import subprocess

                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                # Parse CSV output
                lines = result.stdout.strip().split("\n")
                if len(lines) >= 2:
                    # Second line has the process info
                    parts = lines[1].split(",")
                    if len(parts) >= 1:
                        info["process_name"] = parts[0].strip('"')
            except Exception:
                pass

        return info


def check_single_instance() -> tuple[bool, Optional[int]]:
    """Check if this is the only instance running.

    Returns:
        Tuple of (is_first_instance, existing_pid)
    """
    manager = SingleInstanceManager()
    return manager.check_and_lock()


def format_instance_error(pid: int, pid_file: str) -> str:
    """Format error message for running instance.

    Args:
        pid: Process ID of running instance
        pid_file: Path to PID file

    Returns:
        Formatted error message
    """
    msg = f"Another Mini-Agent instance is already running (PID: {pid})\n\n"
    msg += "Options:\n"
    msg += f"  1. Stop the running instance (kill {pid})\n"
    msg += f"  2. Remove stale lock file: {pid_file}\n"
    msg += "\n"
    msg += "If you're sure no other instance is running, remove the lock file:\n"
    msg += f"  rm {pid_file}"
    return msg
