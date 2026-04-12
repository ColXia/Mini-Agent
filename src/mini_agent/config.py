"""Configuration management module

Provides unified configuration loading and management functionality
"""

import os
from pathlib import Path
import subprocess
import sys

from dotenv import load_dotenv
import yaml
from pydantic import BaseModel, Field


def _resolve_env_reference(value: str | None) -> str | None:
    """Resolve simple environment-variable references in config values."""
    if not isinstance(value, str):
        return value

    trimmed = value.strip()
    if trimmed.startswith("${") and trimmed.endswith("}"):
        return os.getenv(trimmed[2:-1].strip(), value)
    if trimmed.startswith("$") and len(trimmed) > 1:
        return os.getenv(trimmed[1:].strip(), value)
    return value


def _is_unresolved_env_reference(value: str | None) -> bool:
    """Check whether a string still looks like an unresolved env reference."""
    if not isinstance(value, str):
        return False
    trimmed = value.strip()
    return (trimmed.startswith("${") and trimmed.endswith("}")) or (
        trimmed.startswith("$") and len(trimmed) > 1
    )


OFFICIAL_PRESET_ENV_KEYS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "MINIMAX_API_KEY",
)


class RetryConfig(BaseModel):
    """Retry configuration"""

    enabled: bool = True
    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0


class LLMConfig(BaseModel):
    """LLM configuration"""

    api_key: str
    api_base: str = "https://api.minimax.io"
    model: str = "MiniMax-M2.5"
    provider: str = "anthropic"  # "anthropic" or "openai"
    retry: RetryConfig = Field(default_factory=RetryConfig)


class AgentConfig(BaseModel):
    """Agent configuration"""

    max_steps: int = 50
    max_tool_calls_per_step: int | None = None
    workspace_dir: str = "./workspace"
    system_prompt_path: str = "system_prompt.md"


class MCPConfig(BaseModel):
    """MCP (Model Context Protocol) timeout configuration"""

    connect_timeout: float = 10.0  # Connection timeout (seconds)
    execute_timeout: float = 60.0  # Tool execution timeout (seconds)
    sse_read_timeout: float = 120.0  # SSE read timeout (seconds)


class ToolsConfig(BaseModel):
    """Tools configuration"""

    # Basic tools (file operations, bash)
    enable_file_tools: bool = True
    enable_bash: bool = True
    enable_note: bool = True
    enable_knowledge_base: bool = True

    # Skills
    enable_skills: bool = True
    skills_dir: str = "./skills"

    # MCP tools
    enable_mcp: bool = True
    mcp_config_path: str = "mcp.json"
    mcp: MCPConfig = Field(default_factory=MCPConfig)


class SecurityConfig(BaseModel):
    """Runtime safety policy configuration."""

    approval_profile: str = "build"  # plan | build
    access_level: str = "default"  # default | full-access
    sandbox_mode: str | None = None  # workspace | unrestricted
    elevated_exec: str | None = None  # deny | require_approval | allow
    network_mode: str | None = None  # allow_all | deny_all | allowlist | blocklist
    network_allow_domains: list[str] = Field(default_factory=list)
    network_block_domains: list[str] = Field(default_factory=list)
    sandbox_max_processes: int | None = 32
    sandbox_max_process_memory_mb: int | None = 2048
    tool_allow: list[str] = Field(default_factory=list)
    tool_exclude: list[str] = Field(default_factory=list)


class ObservabilityConfig(BaseModel):
    """Observability and run-log retention configuration."""

    log_dir: str = "~/.mini-agent/log"
    event_log_retention_enabled: bool = True
    event_log_prune_on_start: bool = True
    event_log_max_runs: int = 200
    event_log_max_age_days: int = 14
    event_log_max_total_mb: float = 512.0


class Config(BaseModel):
    """Main configuration class"""

    llm: LLMConfig
    agent: AgentConfig
    tools: ToolsConfig
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)

    @classmethod
    def load(cls, *, allow_interactive_setup: bool = True) -> "Config":
        """Load configuration from the default search path."""
        config_path = cls.get_default_config_path()
        if not config_path.exists():
            raise FileNotFoundError(
                "Configuration file not found. Run scripts/setup-config.sh or place config.yaml in mini_agent/config/."
            )
        return cls.from_yaml(config_path, allow_interactive_setup=allow_interactive_setup)

    @staticmethod
    def load_local_env_files(config_path: str | Path | None = None) -> None:
        """Load repository-local env files without overriding existing environment.

        Supported local file is .env.local for development-only secrets such as
        API keys that should not be committed. Priority remains:
        system environment variables > .env.local.
        """
        candidates: list[Path] = []
        seen: set[Path] = set()

        if config_path is not None:
            config_dir = Path(config_path).resolve().parent
            for name in (".env.local",):
                candidates.append(config_dir / name)

        cwd = Path.cwd().resolve()
        for name in (".env.local",):
            candidates.append(cwd / name)

        for candidate in candidates:
            if candidate in seen or not candidate.exists():
                continue
            load_dotenv(candidate, override=False)
            seen.add(candidate)

    @staticmethod
    def _preset_bootstrap_marker() -> Path:
        return Path.home() / ".mini-agent" / "state" / "preset_key_bootstrap.done"

    @staticmethod
    def _has_any_preset_key() -> bool:
        placeholders = {
            "YOUR_API_KEY_HERE",
            "YOUR_OPENAI_API_KEY_HERE",
            "YOUR_ANTHROPIC_API_KEY_HERE",
            "YOUR_GEMINI_API_KEY_HERE",
            "YOUR_MINIMAX_API_KEY_HERE",
            "your_api_key",
            "your-api-key",
            "sk-...",
            "sk-ant-...",
            "sk-cp-xxxxx",
        }
        for env_key in OFFICIAL_PRESET_ENV_KEYS:
            value = os.getenv(env_key)
            if not value:
                continue
            trimmed = value.strip()
            if (
                trimmed
                and trimmed not in placeholders
                and not _is_unresolved_env_reference(trimmed)
            ):
                return True
        return False

    @staticmethod
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

    @classmethod
    def _run_first_launch_preset_key_setup(cls) -> None:
        marker = cls._preset_bootstrap_marker()
        if marker.exists():
            return

        if cls._has_any_preset_key():
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
            print("  gemini -> GEMINI_API_KEY")
            print("  minimax -> MINIMAX_API_KEY")
            provider_choice = input("Provider [openai/anthropic/gemini/minimax]: ").strip().lower()
            env_key_map = {
                "openai": "OPENAI_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY",
                "gemini": "GEMINI_API_KEY",
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
                        cls._write_env_local_key(env_key, api_key)

        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("done\n", encoding="utf-8")

    @classmethod
    def from_yaml(
        cls,
        config_path: str | Path,
        *,
        allow_interactive_setup: bool = True,
    ) -> "Config":
        """Load configuration from YAML file

        Args:
            config_path: Configuration file path

        Returns:
            Config instance

        Raises:
            FileNotFoundError: Configuration file does not exist
            ValueError: Invalid configuration format or missing required fields
        """
        config_path = Path(config_path)

        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file does not exist: {config_path}")

        cls.load_local_env_files(config_path)

        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            raise ValueError("Configuration file is empty")

        # Parse LLM configuration
        # Priority: config.yaml > preset environment variables > error
        configured_api_key = _resolve_env_reference(data.get("api_key"))
        configured_api_base = _resolve_env_reference(data.get("api_base"))
        configured_model = _resolve_env_reference(data.get("model"))
        configured_provider = _resolve_env_reference(data.get("provider"))

        placeholder_api_keys = {
            "YOUR_API_KEY_HERE",
            "sk-cp-xxxxx",
            "your_api_key",
            "your-api-key",
        }

        # Check if config.yaml has valid LLM configuration
        has_valid_config = (
            configured_api_key
            and configured_api_key not in placeholder_api_keys
            and not _is_unresolved_env_reference(configured_api_key)
            and configured_model
        )

        if has_valid_config:
            # Use config.yaml values (backward compatibility)
            api_key = configured_api_key
            api_base = configured_api_base or "https://api.minimax.io"
            model = configured_model
            provider = configured_provider or "anthropic"
        else:
            # Try preset environment variables
            from mini_agent.model_manager.preset_providers import (
                get_first_available_preset,
            )

            preset = get_first_available_preset()
            if not preset and allow_interactive_setup:
                cls._run_first_launch_preset_key_setup()
                cls.load_local_env_files(config_path)
                preset = get_first_available_preset()
            if preset:
                api_key = preset["api_key"]
                api_base = preset["api_base"]
                model = preset.get("model") or preset["models"][0]
                provider = preset["api_type"]
            else:
                # No valid configuration found
                raise ValueError(
                    "No available API keys found. Please either:\n"
                    "  1. Set environment variable: OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, or MINIMAX_API_KEY\n"
                    "  2. Add a local fallback key in .env.local\n"
                    "  3. Update config.yaml with a valid api_key and model"
                )

        # Parse retry configuration
        retry_data = data.get("retry", {})
        retry_config = RetryConfig(
            enabled=retry_data.get("enabled", True),
            max_retries=retry_data.get("max_retries", 3),
            initial_delay=retry_data.get("initial_delay", 1.0),
            max_delay=retry_data.get("max_delay", 60.0),
            exponential_base=retry_data.get("exponential_base", 2.0),
        )

        llm_config = LLMConfig(
            api_key=api_key,
            api_base=api_base,
            model=model,
            provider=provider,
            retry=retry_config,
        )

        # Parse Agent configuration
        agent_config = AgentConfig(
            max_steps=data.get("max_steps", 50),
            max_tool_calls_per_step=data.get("max_tool_calls_per_step"),
            workspace_dir=data.get("workspace_dir", "./workspace"),
            system_prompt_path=data.get("system_prompt_path", "system_prompt.md"),
        )

        # Parse tools configuration
        tools_data = data.get("tools", {})

        # Parse MCP configuration
        mcp_data = tools_data.get("mcp", {})
        mcp_config = MCPConfig(
            connect_timeout=mcp_data.get("connect_timeout", 10.0),
            execute_timeout=mcp_data.get("execute_timeout", 60.0),
            sse_read_timeout=mcp_data.get("sse_read_timeout", 120.0),
        )

        tools_config = ToolsConfig(
            enable_file_tools=tools_data.get("enable_file_tools", True),
            enable_bash=tools_data.get("enable_bash", True),
            enable_note=tools_data.get("enable_note", True),
            enable_knowledge_base=tools_data.get("enable_knowledge_base", True),
            enable_skills=tools_data.get("enable_skills", True),
            skills_dir=tools_data.get("skills_dir", "./skills"),
            enable_mcp=tools_data.get("enable_mcp", True),
            mcp_config_path=tools_data.get("mcp_config_path", "mcp.json"),
            mcp=mcp_config,
        )

        security_data = data.get("security", {})
        security_config = SecurityConfig(
            approval_profile=security_data.get("approval_profile", "build"),
            access_level=security_data.get("access_level", "default"),
            sandbox_mode=security_data.get("sandbox_mode"),
            elevated_exec=security_data.get("elevated_exec"),
            network_mode=security_data.get("network_mode"),
            network_allow_domains=security_data.get("network_allow_domains", []),
            network_block_domains=security_data.get("network_block_domains", []),
            tool_allow=security_data.get("tool_allow", []),
            tool_exclude=security_data.get("tool_exclude", []),
        )

        observability_data = data.get("observability", {})
        observability_config = ObservabilityConfig(
            log_dir=observability_data.get("log_dir", "~/.mini-agent/log"),
            event_log_retention_enabled=observability_data.get(
                "event_log_retention_enabled", True
            ),
            event_log_prune_on_start=observability_data.get(
                "event_log_prune_on_start", True
            ),
            event_log_max_runs=observability_data.get("event_log_max_runs", 200),
            event_log_max_age_days=observability_data.get("event_log_max_age_days", 14),
            event_log_max_total_mb=observability_data.get(
                "event_log_max_total_mb", 512.0
            ),
        )

        return cls(
            llm=llm_config,
            agent=agent_config,
            tools=tools_config,
            security=security_config,
            observability=observability_config,
        )

    @staticmethod
    def get_package_dir() -> Path:
        """Get the package installation directory

        Returns:
            Path to the mini_agent package directory
        """
        # Get the directory where this config.py file is located
        return Path(__file__).parent

    @classmethod
    def find_config_file(cls, filename: str) -> Path | None:
        """Find configuration file with priority order

        Search for config file in the following order of priority:
        1) mini_agent/config/{filename} in current directory (development mode)
        2) ~/.mini-agent/config/{filename} in user home directory
        3) {package}/mini_agent/config/{filename} in package installation directory

        Args:
            filename: Configuration file name (e.g., "config.yaml", "mcp.json", "system_prompt.md")

        Returns:
            Path to found config file, or None if not found
        """
        # Priority 1: Development mode - current directory's config/ subdirectory
        dev_config = Path.cwd() / "mini_agent" / "config" / filename
        if dev_config.exists():
            return dev_config

        # Priority 2: User config directory
        user_config = Path.home() / ".mini-agent" / "config" / filename
        if user_config.exists():
            return user_config

        # Priority 3: Package installation directory's config/ subdirectory
        package_config = cls.get_package_dir() / "config" / filename
        if package_config.exists():
            return package_config

        return None

    @classmethod
    def get_default_config_path(cls) -> Path:
        """Get the default config file path with priority search

        Returns:
            Path to config.yaml (prioritizes: dev config/ > user config/ > package config/)
        """
        config_path = cls.find_config_file("config.yaml")
        if config_path:
            return config_path

        # Fallback to package config directory for error message purposes
        return cls.get_package_dir() / "config" / "config.yaml"
