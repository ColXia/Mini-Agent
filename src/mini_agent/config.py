"""Configuration management module

Provides unified configuration loading and management functionality
"""

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

import mini_agent.config_bootstrap as _config_bootstrap


OFFICIAL_PRESET_ENV_KEYS = _config_bootstrap.OFFICIAL_PRESET_ENV_KEYS
load_local_env_files = _config_bootstrap.load_local_env_files
run_first_launch_preset_key_setup = _config_bootstrap.run_first_launch_preset_key_setup


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


def _parse_bool_value(value: object, *, default: bool | None = None) -> bool | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_int_value(value: object, *, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _parse_float_value(value: object, *, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        return float(str(value).strip())
    except Exception:
        return default


_PLACEHOLDER_API_KEYS = {
    "YOUR_API_KEY_HERE",
    "sk-cp-xxxxx",
    "your_api_key",
    "your-api-key",
}


def _as_mapping(value: object, *, section: str) -> dict[str, object]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    raise ValueError(f"Configuration section '{section}' must be a mapping.")


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
    bootstrap_selected_provider: str | None = None
    bootstrap_selection_reason: str | None = None
    bootstrap_selection_policy: str | None = None
    bootstrap_preferred_provider: str | None = None
    bootstrap_preferred_provider_available: bool | None = None
    bootstrap_alternatives: list[dict[str, object]] = Field(default_factory=list)


class RuntimeConfig(BaseModel):
    """Runtime execution configuration."""

    retry: RetryConfig = Field(default_factory=RetryConfig)
    request_policy: "RuntimeRequestPolicyConfig" = Field(
        default_factory=lambda: RuntimeRequestPolicyConfig()
    )
    rectifier: "RuntimeRectifierConfig" = Field(
        default_factory=lambda: RuntimeRectifierConfig()
    )


class RuntimeRequestPolicyConfig(BaseModel):
    """Global runtime request-policy defaults."""

    max_output_tokens: int | None = None
    reasoning_split_enabled: bool | None = None
    thinking_budget_tokens: int | None = None
    temperature: float | None = None
    streaming_enabled: bool = True
    include_stream_usage: bool = True


class RuntimeRectifierConfig(BaseModel):
    """Global runtime rectifier defaults."""

    enabled: bool = True
    cache_injection: bool = True
    strip_thinking_signature: bool = True


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
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)

    @classmethod
    def load(cls, *, allow_interactive_setup: bool = True) -> "Config":
        """Load configuration from the default search path."""
        config_path = cls.get_default_config_path()
        if not config_path.exists():
            config_path = cls._bootstrap_default_config(config_path)
        return cls.from_yaml(config_path, allow_interactive_setup=allow_interactive_setup)

    @classmethod
    def _bootstrap_default_config(cls, fallback_path: Path) -> Path:
        example = cls.find_config_file("config-example.yaml")
        if example and example.exists():
            fallback_path.parent.mkdir(parents=True, exist_ok=True)
            fallback_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"[INFO] Created default config from template: {fallback_path}")
            return fallback_path
        raise FileNotFoundError(
            "Configuration file not found. Place config.yaml in "
            "src/mini_agent/config/ (preferred) or ~/.mini-agent/config/."
        )

    @staticmethod
    def _load_yaml_mapping(config_path: Path) -> dict[str, object]:
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not data:
            raise ValueError("Configuration file is empty")
        if not isinstance(data, dict):
            raise ValueError("Configuration file root must be a mapping.")
        return dict(data)

    @staticmethod
    def _validate_legacy_keys(data: dict[str, object]) -> None:
        if "retry" in data:
            raise ValueError(
                "Legacy top-level 'retry' is no longer supported. "
                "Move it to 'runtime.retry'."
            )

    @classmethod
    def _resolve_llm_config(
        cls,
        data: dict[str, object],
        *,
        config_path: Path,
        allow_interactive_setup: bool,
    ) -> LLMConfig:
        configured_api_key = _resolve_env_reference(data.get("api_key"))
        configured_api_base = _resolve_env_reference(data.get("api_base"))
        configured_model = _resolve_env_reference(data.get("model"))
        configured_provider = _resolve_env_reference(data.get("provider"))

        has_valid_config = (
            configured_api_key
            and configured_api_key not in _PLACEHOLDER_API_KEYS
            and not _is_unresolved_env_reference(configured_api_key)
            and configured_model
        )
        if has_valid_config:
            return LLMConfig(
                api_key=configured_api_key,
                api_base=configured_api_base or "https://api.minimax.io",
                model=configured_model,
                provider=configured_provider or "anthropic",
            )

        from mini_agent.model_manager.preset_providers import (
            get_first_available_preset,
        )

        preset = get_first_available_preset()
        if not preset and allow_interactive_setup:
            run_first_launch_preset_key_setup()
            load_local_env_files(config_path)
            preset = get_first_available_preset()
        if not preset:
            raise ValueError(
                "No available API keys found. Please either:\n"
                "  1. Set environment variable: OPENAI_API_KEY, ANTHROPIC_API_KEY, or MINIMAX_API_KEY\n"
                "  2. Add a local fallback key in .env.local\n"
                "  3. Update config.yaml with a valid api_key and model"
            )

        return LLMConfig(
            api_key=str(preset["api_key"]),
            api_base=str(preset["api_base"]),
            model=str(preset.get("model") or preset["models"][0]),
            provider=str(preset["api_type"]),
            bootstrap_selected_provider=str(preset.get("bootstrap_selected_provider") or "").strip() or None,
            bootstrap_selection_reason=str(preset.get("bootstrap_selection_reason") or "").strip() or None,
            bootstrap_selection_policy=str(preset.get("bootstrap_selection_policy") or "").strip() or None,
            bootstrap_preferred_provider=str(preset.get("bootstrap_preferred_provider") or "").strip() or None,
            bootstrap_preferred_provider_available=(
                bool(preset.get("bootstrap_preferred_provider_available"))
                if "bootstrap_preferred_provider_available" in preset
                else None
            ),
            bootstrap_alternatives=[
                dict(item)
                for item in preset.get("bootstrap_alternatives", [])
                if isinstance(item, dict)
            ],
        )

    @staticmethod
    def _runtime_request_policy_env_defaults() -> RuntimeRequestPolicyConfig:
        return RuntimeRequestPolicyConfig(
            max_output_tokens=None,
            reasoning_split_enabled=None,
            thinking_budget_tokens=_parse_int_value(
                os.getenv("MINI_AGENT_THINKING_BUDGET_TOKENS")
            ),
            temperature=_parse_float_value(os.getenv("MINI_AGENT_LLM_TEMPERATURE")),
            streaming_enabled=bool(
                _parse_bool_value(
                    os.getenv("MINI_AGENT_STREAMING_ENABLED"),
                    default=True,
                )
            ),
            include_stream_usage=bool(
                _parse_bool_value(
                    os.getenv("MINI_AGENT_STREAM_USAGE_ENABLED"),
                    default=True,
                )
            ),
        )

    @staticmethod
    def _runtime_rectifier_env_defaults() -> RuntimeRectifierConfig:
        return RuntimeRectifierConfig(
            enabled=bool(
                _parse_bool_value(
                    os.getenv("MINI_AGENT_RECTIFIER_ENABLED"),
                    default=True,
                )
            ),
            cache_injection=bool(
                _parse_bool_value(
                    os.getenv("MINI_AGENT_RECTIFIER_CACHE_INJECTION"),
                    default=True,
                )
            ),
            strip_thinking_signature=bool(
                _parse_bool_value(
                    os.getenv("MINI_AGENT_RECTIFIER_STRIP_THINKING_SIGNATURE"),
                    default=True,
                )
            ),
        )

    @classmethod
    def _resolve_runtime_config(cls, data: dict[str, object]) -> RuntimeConfig:
        runtime_data = _as_mapping(data.get("runtime"), section="runtime")
        retry_data = _as_mapping(runtime_data.get("retry"), section="runtime.retry")
        request_policy_data = _as_mapping(
            runtime_data.get("request_policy"),
            section="runtime.request_policy",
        )
        rectifier_data = _as_mapping(
            runtime_data.get("rectifier"),
            section="runtime.rectifier",
        )

        request_policy_env = cls._runtime_request_policy_env_defaults()
        rectifier_env = cls._runtime_rectifier_env_defaults()

        return RuntimeConfig(
            retry=RetryConfig(
                enabled=retry_data.get("enabled", True),
                max_retries=retry_data.get("max_retries", 3),
                initial_delay=retry_data.get("initial_delay", 1.0),
                max_delay=retry_data.get("max_delay", 60.0),
                exponential_base=retry_data.get("exponential_base", 2.0),
            ),
            request_policy=RuntimeRequestPolicyConfig(
                max_output_tokens=_parse_int_value(
                    request_policy_data.get("max_output_tokens"),
                    default=request_policy_env.max_output_tokens,
                ),
                reasoning_split_enabled=(
                    _parse_bool_value(
                        request_policy_data.get("reasoning_split_enabled"),
                        default=None,
                    )
                    if "reasoning_split_enabled" in request_policy_data
                    else request_policy_env.reasoning_split_enabled
                ),
                thinking_budget_tokens=_parse_int_value(
                    request_policy_data.get("thinking_budget_tokens"),
                    default=request_policy_env.thinking_budget_tokens,
                ),
                temperature=_parse_float_value(
                    request_policy_data.get("temperature"),
                    default=request_policy_env.temperature,
                ),
                streaming_enabled=bool(
                    _parse_bool_value(
                        request_policy_data.get("streaming_enabled"),
                        default=request_policy_env.streaming_enabled,
                    )
                ),
                include_stream_usage=bool(
                    _parse_bool_value(
                        request_policy_data.get("include_stream_usage"),
                        default=request_policy_env.include_stream_usage,
                    )
                ),
            ),
            rectifier=RuntimeRectifierConfig(
                enabled=bool(
                    _parse_bool_value(
                        rectifier_data.get("enabled"),
                        default=rectifier_env.enabled,
                    )
                ),
                cache_injection=bool(
                    _parse_bool_value(
                        rectifier_data.get("cache_injection"),
                        default=rectifier_env.cache_injection,
                    )
                ),
                strip_thinking_signature=bool(
                    _parse_bool_value(
                        rectifier_data.get("strip_thinking_signature"),
                        default=rectifier_env.strip_thinking_signature,
                    )
                ),
            ),
        )

    @staticmethod
    def _resolve_agent_config(data: dict[str, object]) -> AgentConfig:
        return AgentConfig(
            max_steps=data.get("max_steps", 50),
            max_tool_calls_per_step=data.get("max_tool_calls_per_step"),
            workspace_dir=data.get("workspace_dir", "./workspace"),
            system_prompt_path=data.get("system_prompt_path", "system_prompt.md"),
        )

    @staticmethod
    def _resolve_tools_config(data: dict[str, object]) -> ToolsConfig:
        tools_data = _as_mapping(data.get("tools"), section="tools")
        mcp_data = _as_mapping(tools_data.get("mcp"), section="tools.mcp")
        return ToolsConfig(
            enable_file_tools=tools_data.get("enable_file_tools", True),
            enable_bash=tools_data.get("enable_bash", True),
            enable_note=tools_data.get("enable_note", True),
            enable_knowledge_base=tools_data.get("enable_knowledge_base", True),
            enable_skills=tools_data.get("enable_skills", True),
            skills_dir=tools_data.get("skills_dir", "./skills"),
            enable_mcp=tools_data.get("enable_mcp", True),
            mcp_config_path=tools_data.get("mcp_config_path", "mcp.json"),
            mcp=MCPConfig(
                connect_timeout=mcp_data.get("connect_timeout", 10.0),
                execute_timeout=mcp_data.get("execute_timeout", 60.0),
                sse_read_timeout=mcp_data.get("sse_read_timeout", 120.0),
            ),
        )

    @staticmethod
    def _resolve_security_config(data: dict[str, object]) -> SecurityConfig:
        security_data = _as_mapping(data.get("security"), section="security")
        return SecurityConfig(
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

    @staticmethod
    def _resolve_observability_config(data: dict[str, object]) -> ObservabilityConfig:
        observability_data = _as_mapping(
            data.get("observability"),
            section="observability",
        )
        return ObservabilityConfig(
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

        load_local_env_files(config_path)
        data = cls._load_yaml_mapping(config_path)
        cls._validate_legacy_keys(data)

        return cls(
            llm=cls._resolve_llm_config(
                data,
                config_path=config_path,
                allow_interactive_setup=allow_interactive_setup,
            ),
            agent=cls._resolve_agent_config(data),
            tools=cls._resolve_tools_config(data),
            runtime=cls._resolve_runtime_config(data),
            security=cls._resolve_security_config(data),
            observability=cls._resolve_observability_config(data),
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
        1) src/mini_agent/config/{filename} in current directory (preferred dev mode)
        2) mini_agent/config/{filename} in current directory (legacy dev mode)
        3) ~/.mini-agent/config/{filename} in user home directory
        4) {package}/config/{filename} in package installation directory

        Args:
            filename: Configuration file name (e.g., "config.yaml", "mcp.json", "system_prompt.md")

        Returns:
            Path to found config file, or None if not found
        """
        # Priority 1: Preferred src-layout development path
        src_dev_config = Path.cwd() / "src" / "mini_agent" / "config" / filename
        if src_dev_config.exists():
            return src_dev_config

        # Priority 2: Legacy development mode path
        dev_config = Path.cwd() / "mini_agent" / "config" / filename
        if dev_config.exists():
            return dev_config

        # Priority 3: User config directory
        user_config = Path.home() / ".mini-agent" / "config" / filename
        if user_config.exists():
            return user_config

        # Priority 4: Package installation directory's config/ subdirectory
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
