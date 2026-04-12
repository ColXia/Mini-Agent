"""
Skill Tool - Tool for Agent to load Skills on-demand

Implements Progressive Disclosure (Level 2): Load full skill content when needed
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from mini_agent.agent_core.skills.install import WorkspaceSkillInstaller
from mini_agent.agent_core.skills.loader import AgentSkillLoader
from mini_agent.agent_core.skills.policy import WorkspaceSkillRuntimeBridge

from .base import Tool, ToolResult


class GetSkillTool(Tool):
    """Tool to get detailed information about a specific skill"""

    def __init__(self, skill_loader):
        self.skill_loader = skill_loader

    @property
    def name(self) -> str:
        return "get_skill"

    @property
    def description(self) -> str:
        return (
            "Load the full instructions for a named skill. "
            "Use this before relying on a skill, citing it by name, or following a skill-specific workflow; "
            "tier-1 skill metadata alone is only a routing hint."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": (
                        "Exact name of the skill to retrieve. "
                        "Call this when a relevant skill appears in available-skill metadata or relevant-skill context."
                    ),
                }
            },
            "required": ["skill_name"],
        }

    async def execute(self, skill_name: str) -> ToolResult:
        """Get detailed information about specified skill"""
        skill = self.skill_loader.get_skill(skill_name)

        if not skill:
            available = ", ".join(self.skill_loader.list_skills())
            return ToolResult(
                success=False,
                content="",
                error=f"Skill '{skill_name}' does not exist. Available skills: {available}",
            )

        # Return complete skill content
        result = skill.to_prompt()
        return ToolResult(success=True, content=result)


class InstallSkillTool(Tool):
    """Tool to create and install a workspace skill from inline content."""

    def __init__(
        self,
        *,
        workspace_dir: str,
        workspace_skills_dir: str | None,
        skill_loader,
    ) -> None:
        self.workspace_dir = workspace_dir
        self.workspace_skills_dir = workspace_skills_dir
        self.skill_loader = skill_loader

    @property
    def name(self) -> str:
        return "install_skill"

    @property
    def description(self) -> str:
        return (
            "Create and install a new workspace skill from inline instructions. "
            "This writes a SKILL.md file into workspace skill storage and activates it."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "Unique name for the new skill.",
                },
                "description": {
                    "type": "string",
                    "description": "Short summary describing when the skill should be used.",
                },
                "instructions": {
                    "type": "string",
                    "description": "Full skill instructions written into SKILL.md.",
                },
                "activate": {
                    "type": "boolean",
                    "description": "Whether to activate the new skill in the current workspace policy.",
                    "default": True,
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "Whether to replace an existing skill with the same name.",
                    "default": False,
                },
            },
            "required": ["skill_name", "description", "instructions"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        skill_name: str,
        description: str,
        instructions: str,
        activate: bool = True,
        overwrite: bool = False,
    ) -> ToolResult:
        try:
            installer = WorkspaceSkillInstaller(
                self.workspace_dir,
                skills_root=self.workspace_skills_dir,
            )
            result = installer.install_inline(
                skill_name=skill_name,
                description=description,
                instructions=instructions,
                activate=activate,
                overwrite=overwrite,
                loader=self.skill_loader,
            )
        except Exception as exc:
            return ToolResult(success=False, content="", error=f"Skill install failed: {exc}")

        lines = [
            f"Installed skill: {result.skill_name}",
            f"Path: {result.installed_path}",
            f"Source: {result.source_kind}",
            f"Activated: {'yes' if result.activated else 'no'}",
            f"Policy mode: {result.policy.mode}",
        ]
        if result.ledger_path:
            lines.append(f"Ledger: {result.ledger_path}")
        return ToolResult(success=True, content="\n".join(lines))


class InstallSkillFromPathTool(Tool):
    """Tool to install an existing skill source into workspace storage."""

    def __init__(
        self,
        *,
        workspace_dir: str,
        workspace_skills_dir: str | None,
        skill_loader,
    ) -> None:
        self.workspace_dir = workspace_dir
        self.workspace_skills_dir = workspace_skills_dir
        self.skill_loader = skill_loader

    @property
    def name(self) -> str:
        return "install_skill_from_path"

    @property
    def description(self) -> str:
        return (
            "Install an existing skill source into workspace skill storage. "
            "Supported sources include a local skill directory, a SKILL.md file, a single-skill archive, or an HTTP/HTTPS URL to one of those."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path or URL to a skill directory, SKILL.md file, or single-skill archive.",
                },
                "activate": {
                    "type": "boolean",
                    "description": "Whether to activate the installed skill in the current workspace policy.",
                    "default": True,
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "Whether to replace an existing installed skill with the same name.",
                    "default": False,
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        path: str,
        activate: bool = True,
        overwrite: bool = False,
    ) -> ToolResult:
        try:
            installer = WorkspaceSkillInstaller(
                self.workspace_dir,
                skills_root=self.workspace_skills_dir,
            )
            result = installer.install_from_path(
                path,
                activate=activate,
                overwrite=overwrite,
                loader=self.skill_loader,
            )
        except Exception as exc:
            return ToolResult(success=False, content="", error=f"Skill install from path failed: {exc}")

        lines = [
            f"Installed skill: {result.skill_name}",
            f"Path: {result.installed_path}",
            f"Source: {result.source_kind}",
            f"From: {result.source_path or path}",
            f"Activated: {'yes' if result.activated else 'no'}",
            f"Policy mode: {result.policy.mode}",
        ]
        if result.ledger_path:
            lines.append(f"Ledger: {result.ledger_path}")
        return ToolResult(success=True, content="\n".join(lines))


class UninstallSkillTool(Tool):
    """Tool to remove one installed workspace skill and keep a rollback backup."""

    def __init__(
        self,
        *,
        workspace_dir: str,
        workspace_skills_dir: str | None,
        skill_loader,
    ) -> None:
        self.workspace_dir = workspace_dir
        self.workspace_skills_dir = workspace_skills_dir
        self.skill_loader = skill_loader

    @property
    def name(self) -> str:
        return "uninstall_skill"

    @property
    def description(self) -> str:
        return (
            "Uninstall one workspace skill by name. "
            "This removes the installed skill, keeps a rollback backup, and records the change in the skill source ledger."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "Name of the installed workspace skill to remove.",
                }
            },
            "required": ["skill_name"],
            "additionalProperties": False,
        }

    async def execute(self, skill_name: str) -> ToolResult:
        try:
            installer = WorkspaceSkillInstaller(
                self.workspace_dir,
                skills_root=self.workspace_skills_dir,
            )
            result = installer.uninstall(skill_name, loader=self.skill_loader)
        except Exception as exc:
            return ToolResult(success=False, content="", error=f"Skill uninstall failed: {exc}")

        lines = [
            f"Uninstalled skill: {result.skill_name}",
            f"Removed: {result.removed_path}",
        ]
        if result.backup_path:
            lines.append(f"Backup: {result.backup_path}")
        if result.ledger_path:
            lines.append(f"Ledger: {result.ledger_path}")
        return ToolResult(success=True, content="\n".join(lines))


class RollbackSkillTool(Tool):
    """Tool to restore the latest backup for one workspace skill."""

    def __init__(
        self,
        *,
        workspace_dir: str,
        workspace_skills_dir: str | None,
        skill_loader,
    ) -> None:
        self.workspace_dir = workspace_dir
        self.workspace_skills_dir = workspace_skills_dir
        self.skill_loader = skill_loader

    @property
    def name(self) -> str:
        return "rollback_skill"

    @property
    def description(self) -> str:
        return (
            "Rollback one workspace skill to the latest backup recorded in the skill source ledger."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "Name of the workspace skill to restore from backup.",
                }
            },
            "required": ["skill_name"],
            "additionalProperties": False,
        }

    async def execute(self, skill_name: str) -> ToolResult:
        try:
            installer = WorkspaceSkillInstaller(
                self.workspace_dir,
                skills_root=self.workspace_skills_dir,
            )
            result = installer.rollback(skill_name, loader=self.skill_loader)
        except Exception as exc:
            return ToolResult(success=False, content="", error=f"Skill rollback failed: {exc}")

        lines = [
            f"Rolled back skill: {result.skill_name}",
            f"Restored: {result.restored_path}",
            f"Backup: {result.backup_path}",
        ]
        if result.ledger_path:
            lines.append(f"Ledger: {result.ledger_path}")
        return ToolResult(success=True, content="\n".join(lines))


def create_skill_tools(
    skills_dir: str = "./skills",
    workspace_skills_dir: str | None = None,
    workspace_dir: str | None = None,
) -> tuple[List[Tool], Optional[object]]:
    """
    Create skill tool for Progressive Disclosure

    Provides:
    - get_skill: load the full content of an active skill on demand
    - install_skill: when a workspace target exists, create and activate a
      new workspace skill from inline content
    - install_skill_from_path: when a workspace target exists, import an
      existing local/remote skill source
    - uninstall_skill: remove an installed workspace skill while keeping a backup
    - rollback_skill: restore the latest backup for one workspace skill

    Args:
        skills_dir: Skills directory path

    Returns:
        Tuple of (list of tools, skill loader)
    """
    workspace_skill_root = workspace_skills_dir or os.getenv("MINI_AGENT_WORKSPACE_SKILLS_DIR")
    if workspace_skill_root is None and workspace_dir:
        workspace_skill_root = str((Path(workspace_dir).expanduser().resolve() / ".mini-agent" / "skills"))
    loader = AgentSkillLoader(
        builtin_dir=skills_dir,
        workspace_dir=workspace_skill_root,
    )
    loader.discover()
    bridge = WorkspaceSkillRuntimeBridge(
        loader,
        workspace_dir=workspace_dir,
        eligible_only=True,
    )

    # Create only the get_skill tool (Progressive Disclosure Level 2)
    tools = [
        GetSkillTool(bridge),
    ]
    if workspace_dir:
        tools.append(
            InstallSkillTool(
                workspace_dir=workspace_dir,
                workspace_skills_dir=workspace_skill_root,
                skill_loader=bridge,
            )
        )
        tools.append(
            InstallSkillFromPathTool(
                workspace_dir=workspace_dir,
                workspace_skills_dir=workspace_skill_root,
                skill_loader=bridge,
            )
        )
        tools.append(
            UninstallSkillTool(
                workspace_dir=workspace_dir,
                workspace_skills_dir=workspace_skill_root,
                skill_loader=bridge,
            )
        )
        tools.append(
            RollbackSkillTool(
                workspace_dir=workspace_dir,
                workspace_skills_dir=workspace_skill_root,
                skill_loader=bridge,
            )
        )

    return tools, bridge
