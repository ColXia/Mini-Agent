"""Agent-core skills loader and registry primitives."""

from mini_agent.agent_core.skills.eligibility import (
    SkillEligibilityChecker,
    SkillEligibilityResult,
    SkillRequirements,
    parse_skill_requirements,
)
from mini_agent.agent_core.skills.install import (
    WorkspaceSkillInstallResult,
    WorkspaceSkillInstaller,
)
from mini_agent.agent_core.skills.loader import (
    AgentSkillLoader,
    AgentSkillRuntimeBridge,
    SkillTier1Metadata,
    parse_skill_markdown,
)
from mini_agent.agent_core.skills.policy import (
    WorkspaceSkillPolicy,
    WorkspaceSkillPolicyStore,
    WorkspaceSkillRuntimeBridge,
    compute_active_skill_names,
    describe_skill_activation,
    normalize_skill_name,
    normalize_skill_policy_mode,
)
from mini_agent.agent_core.skills.registry import AgentSkill, SkillRegistry, SkillSource
from mini_agent.agent_core.skills.self_improve import (
    SelfImprovingSkillEngine,
    SkillEvolutionRecord,
    SkillPerformanceMetrics,
)

__all__ = [
    "SkillRequirements",
    "SkillEligibilityResult",
    "SkillEligibilityChecker",
    "parse_skill_requirements",
    "SkillSource",
    "AgentSkill",
    "SkillRegistry",
    "SkillTier1Metadata",
    "AgentSkillLoader",
    "AgentSkillRuntimeBridge",
    "WorkspaceSkillInstaller",
    "WorkspaceSkillInstallResult",
    "parse_skill_markdown",
    "WorkspaceSkillPolicy",
    "WorkspaceSkillPolicyStore",
    "WorkspaceSkillRuntimeBridge",
    "compute_active_skill_names",
    "describe_skill_activation",
    "normalize_skill_name",
    "normalize_skill_policy_mode",
    "SelfImprovingSkillEngine",
    "SkillEvolutionRecord",
    "SkillPerformanceMetrics",
]
