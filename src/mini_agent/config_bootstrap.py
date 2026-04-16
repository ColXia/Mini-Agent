"""Bootstrap helpers for local env loading and first-launch preset-key setup."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from typing import TYPE_CHECKING

from dotenv import load_dotenv

if TYPE_CHECKING:
    from mini_agent.config import Config


OFFICIAL_PRESET_ENV_KEYS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "MINIMAX_API_KEY",
)

_PRESET_KEY_PLACEHOLDERS = {
    "YOUR_API_KEY_HERE",
    "YOUR_OPENAI_API_KEY_HERE",
    "YOUR_ANTHROPIC_API_KEY_HERE",
    "YOUR_MINIMAX_API_KEY_HERE",
    "your_api_key",
    "your-api-key",
    "sk-...",
    "sk-ant-...",
    "sk-cp-xxxxx",
}


def _is_unresolved_env_reference(value: str | None) -> bool:
    if not isinstance(value, str):
        return False
    trimmed = value.strip()
    return (trimmed.startswith("${") and trimmed.endswith("}")) or (
        trimmed.startswith("$") and len(trimmed) > 1
    )


def load_local_env_files(config_path: str | Path | None = None) -> None:
    """Load repository-local env files without overriding existing environment."""

    candidates: list[Path] = []
    seen: set[Path] = set()

    if config_path is not None:
        config_dir = Path(config_path).resolve().parent
        candidates.append(config_dir / ".env.local")

    cwd = Path.cwd().resolve()
    candidates.append(cwd / ".env.local")

    for candidate in candidates:
        if candidate in seen or not candidate.exists():
            continue
        load_dotenv(candidate, override=False)
        seen.add(candidate)


def load_entry_config(allow_interactive_setup: bool = True) -> "Config":
    """Load config at an entry/composition seam with explicit setup intent."""

    from mini_agent.config import Config

    if allow_interactive_setup:
        return Config.load()
    return Config.load(allow_interactive_setup=False)


def load_noninteractive_config() -> "Config":
    """Load config without first-launch interactive bootstrap."""

    return load_entry_config(False)


def _preset_bootstrap_marker() -> Path:
    return Path.home() / ".mini-agent" / "state" / "preset_key_bootstrap.done"


def _has_any_preset_key() -> bool:
    for env_key in OFFICIAL_PRESET_ENV_KEYS:
        value = os.getenv(env_key)
        if not value:
            continue
        trimmed = value.strip()
        if (
            trimmed
            and trimmed not in _PRESET_KEY_PLACEHOLDERS
            and not _is_unresolved_env_reference(trimmed)
        ):
            return True
    return False


def _write_env_local_key(env_key: str, api_key: str) -> None:
    env_local = Path.cwd().resolve() / ".env.local"
    existing_lines: list[str] = []
    if env_local.exists():
        existing_lines = env_local.read_text(encoding="utf-8").splitlines()

    replaced = False
    updated_lines: list[str] = []
    for line in existing_lines:
        if line.strip().startswith(f"{env_key}="):
            updated_lines.append(f"{env_key}={api_key}")
            replaced = True
        else:
            updated_lines.append(line)
    if not replaced:
        if updated_lines and updated_lines[-1].strip():
            updated_lines.append("")
        updated_lines.append(f"{env_key}={api_key}")

    content = "\n".join(updated_lines).rstrip() + "\n"
    env_local.write_text(content, encoding="utf-8")


def run_first_launch_preset_key_setup() -> None:
    """Prompt once for preset-provider keys when none are configured."""

    marker = _preset_bootstrap_marker()
    if marker.exists():
        return

    if _has_any_preset_key():
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("done\n", encoding="utf-8")
        return

    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return

    print("\nNo preset provider API keys were found.")
    print("First-run setup (only shown once):")
    print("  1. Input a key and set it as system environment variable")
    print("  2. Input a key and save it to .env.local")
    print("  3. Skip")
    choice = input("Select [1/2/3]: ").strip()
    if choice not in {"1", "2", "3"}:
        choice = "3"

    if choice in {"1", "2"}:
        print("Providers:")
        print("  openai -> OPENAI_API_KEY")
        print("  anthropic -> ANTHROPIC_API_KEY")
        print("  minimax -> MINIMAX_API_KEY")
        provider_choice = input("Provider [openai/anthropic/minimax]: ").strip().lower()
        env_key_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "minimax": "MINIMAX_API_KEY",
        }
        env_key = env_key_map.get(provider_choice)
        if env_key:
            api_key = input(f"Enter {env_key}: ").strip()
            if api_key:
                if choice == "1":
                    os.environ[env_key] = api_key
                    if os.name == "nt":
                        try:
                            subprocess.run(
                                ["setx", env_key, api_key],
                                check=False,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                            )
                        except Exception:
                            pass
                else:
                    _write_env_local_key(env_key, api_key)

    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("done\n", encoding="utf-8")


__all__ = [
    "OFFICIAL_PRESET_ENV_KEYS",
    "load_entry_config",
    "load_local_env_files",
    "load_noninteractive_config",
    "run_first_launch_preset_key_setup",
]
