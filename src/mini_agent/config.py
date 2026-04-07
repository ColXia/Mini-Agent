"""Configuration management module

Provides unified configuration loading and management functionality
"""

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


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

    # Skills
    enable_skills: bool = True
    skills_dir: str = "./skills"

    # MCP tools
    enable_mcp: bool = True
    mcp_config_path: str = "mcp.json"
    mcp: MCPConfig = Field(default_factory=MCPConfig)


class SecurityConfig(BaseModel):
    """Runtime safety policy configuration."""

    approval_profile: str = "auto-edit"  # suggest | auto-edit | full-auto
    sandbox_mode: str | None = None  # workspace | unrestricted
    elevated_exec: str | None = None  # deny | require_approval | allow
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
    def load(cls) -> "Config":
        """Load configuration from the default search path."""
        config_path = cls.get_default_config_path()
        if not config_path.exists():
            raise FileNotFoundError(
                "Configuration file not found. Run scripts/setup-config.sh or place config.yaml in mini_agent/config/."
            )
        return cls.from_yaml(config_path)

    @classmethod
    def from_yaml(cls, config_path: str | Path) -> "Config":
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

        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            raise ValueError("Configuration file is empty")

        # Parse LLM configuration
        # Priority: config.yaml > preset environment variables > error
        configured_api_key = data.get("api_key")
        configured_api_base = data.get("api_base")
        configured_model = data.get("model")
        configured_provider = data.get("provider")

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
            if preset:
                api_key = preset["api_key"]
                api_base = preset["api_base"]
                model = preset["models"][0]  # Use first (default) model
                provider = preset["api_type"]
            else:
                # No valid configuration found
                raise ValueError(
                    "No valid LLM configuration found. Please either:\n"
                    "  1. Set environment variable: OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, or MINIMAX_API_KEY\n"
                    "  2. Configure providers using: mini-agent provider add\n"
                    "  3. Update config.yaml with valid api_key and model"
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
            api_base=data.get("api_base", "https://api.minimax.io"),
            model=data.get("model", "MiniMax-M2.5"),
            provider=data.get("provider", "anthropic"),
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
            enable_skills=tools_data.get("enable_skills", True),
            skills_dir=tools_data.get("skills_dir", "./skills"),
            enable_mcp=tools_data.get("enable_mcp", True),
            mcp_config_path=tools_data.get("mcp_config_path", "mcp.json"),
            mcp=mcp_config,
        )

        security_data = data.get("security", {})
        security_config = SecurityConfig(
            approval_profile=security_data.get("approval_profile", "auto-edit"),
            sandbox_mode=security_data.get("sandbox_mode"),
            elevated_exec=security_data.get("elevated_exec"),
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
