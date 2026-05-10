"""Tests for v11.2 capability system objects."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
import sys

from mini_agent.tools.contracts import (
    GrantSource,
    ToolBinding,
    ToolGrant,
    ToolOperationKind,
    ToolPolicy,
    ToolPolicyDecision,
    ToolRiskLevel,
    ToolSpec,
)
from mini_agent.tools.registry import (
    ToolRegistry,
    build_core_tool_specs,
    shared_tool_registry,
    clear_shared_tool_registry,
)
from mini_agent.tools.permission_engine import (
    DEFAULT_OUTSIDE_ZONE_POLICY,
    OutsideZonePolicy,
    PermissionEngine,
    PermissionRequest,
)
from mini_agent.skills.resolver import (
    SkillLayer,
    SkillNamespace,
    SkillSpec,
    ResolvedSkill,
    ResolvedSkillSet,
    SkillResolver,
    InternalSkillRegistry,
    GlobalSkillRegistry,
    WorkspaceSkillRegistry,
    shared_skill_resolver,
    clear_shared_skill_resolver,
)
from mini_agent.memory.resolver import (
    MemoryScope,
    MemoryKind,
    MemoryEntry,
    ResolvedMemory,
    SessionMemoryStore,
    WorkspaceMemoryStore,
    GlobalMemoryStore,
    MemoryResolver,
    shared_memory_resolver,
    clear_shared_memory_resolver,
)


class TestToolSpec:
    """Tests for ToolSpec contract."""

    def test_tool_spec_creation(self) -> None:
        spec = ToolSpec(
            tool_name="read_file",
            namespace="core",
            description="Read file contents",
            operation_kind=ToolOperationKind.READ,
        )
        assert spec.tool_name == "read_file"
        assert spec.namespace == "core"
        assert spec.full_name == "core.read_file"
        assert spec.is_mutation is False

    def test_tool_spec_mutation_detection(self) -> None:
        write_spec = ToolSpec(
            tool_name="write_file",
            namespace="core",
            description="Write file contents",
            operation_kind=ToolOperationKind.WRITE,
        )
        assert write_spec.is_mutation is True

        execute_spec = ToolSpec(
            tool_name="bash",
            namespace="core",
            description="Execute shell",
            operation_kind=ToolOperationKind.EXECUTE,
        )
        assert execute_spec.is_mutation is True

    def test_tool_spec_validation(self) -> None:
        with pytest.raises(ValueError, match="tool_name is required"):
            ToolSpec(
                tool_name="",
                namespace="core",
                description="Test",
                operation_kind=ToolOperationKind.READ,
            )

        with pytest.raises(ValueError, match="namespace is required"):
            ToolSpec(
                tool_name="test",
                namespace="",
                description="Test",
                operation_kind=ToolOperationKind.READ,
            )


class TestToolBinding:
    """Tests for ToolBinding contract."""

    def test_tool_binding_creation(self) -> None:
        binding = ToolBinding(
            binding_id="bind-001",
            tool_name="read_file",
            workspace_id="ws-001",
            run_id="run-001",
        )
        assert binding.binding_id == "bind-001"
        assert binding.is_valid is True

    def test_tool_binding_expiration(self) -> None:
        expired_binding = ToolBinding(
            binding_id="bind-002",
            tool_name="read_file",
            workspace_id="ws-001",
            run_id="run-001",
            binding_valid_until=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        assert expired_binding.is_valid is False


class TestToolPolicy:
    """Tests for ToolPolicy contract."""

    def test_tool_policy_allow(self) -> None:
        policy = ToolPolicy(
            policy_id="pol-001",
            tool_name="read_file",
            decision=ToolPolicyDecision.ALLOW,
            workspace_id="ws-001",
            session_id="sess-001",
        )
        assert policy.is_allowed is True
        assert policy.requires_approval is False
        assert policy.has_constraints is False

    def test_tool_policy_approval_required(self) -> None:
        policy = ToolPolicy(
            policy_id="pol-002",
            tool_name="bash",
            decision=ToolPolicyDecision.APPROVAL_REQUIRED,
            workspace_id="ws-001",
            session_id="sess-001",
            reason="High risk tool",
        )
        assert policy.is_allowed is False
        assert policy.requires_approval is True

    def test_tool_policy_constraint_rewrite(self) -> None:
        policy = ToolPolicy(
            policy_id="pol-003",
            tool_name="bash",
            decision=ToolPolicyDecision.CONSTRAINT_REWRITE,
            workspace_id="ws-001",
            session_id="sess-001",
            constraint_rewrite={"network_policy": "disabled"},
        )
        assert policy.has_constraints is True
        assert policy.constraint_rewrite["network_policy"] == "disabled"


class TestToolGrant:
    """Tests for ToolGrant contract."""

    def test_tool_grant_creation(self) -> None:
        grant = ToolGrant(
            grant_id="grant-001",
            tool_name="bash",
            workspace_id="ws-001",
            session_id="sess-001",
            run_id="run-001",
        )
        assert grant.is_valid is True
        assert grant.is_expired is False
        assert grant.is_run_scoped is True

    def test_tool_grant_expiration(self) -> None:
        expired_grant = ToolGrant(
            grant_id="grant-002",
            tool_name="bash",
            workspace_id="ws-001",
            session_id="sess-001",
            run_id="run-001",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        assert expired_grant.is_expired is True
        assert expired_grant.is_valid is False


class TestToolRegistry:
    """Tests for ToolRegistry."""

    def test_tool_registry_register(self) -> None:
        registry = ToolRegistry()
        spec = ToolSpec(
            tool_name="test_tool",
            namespace="test",
            description="Test tool",
            operation_kind=ToolOperationKind.QUERY,
        )
        registry.register(spec)
        assert registry.has_tool("test_tool")
        assert len(registry) == 1

    def test_tool_registry_get(self) -> None:
        registry = ToolRegistry()
        spec = ToolSpec(
            tool_name="test_tool",
            namespace="test",
            description="Test tool",
            operation_kind=ToolOperationKind.QUERY,
        )
        registry.register(spec)

        found = registry.get("test_tool")
        assert found is not None
        assert found.full_name == "test.test_tool"

        found_by_full = registry.get("test.test_tool")
        assert found_by_full is not None

    def test_tool_registry_list_by_namespace(self) -> None:
        registry = ToolRegistry()
        for name in ["tool_a", "tool_b"]:
            registry.register(ToolSpec(
                tool_name=name,
                namespace="ns1",
                description=f"Tool {name}",
                operation_kind=ToolOperationKind.QUERY,
            ))
        registry.register(ToolSpec(
            tool_name="tool_c",
            namespace="ns2",
            description="Tool C",
            operation_kind=ToolOperationKind.QUERY,
        ))

        ns1_tools = registry.list_by_namespace("ns1")
        assert len(ns1_tools) == 2

        ns2_tools = registry.list_by_namespace("ns2")
        assert len(ns2_tools) == 1

    def test_build_core_tool_specs(self) -> None:
        specs = build_core_tool_specs()
        assert len(specs) == 4
        names = [spec.tool_name for spec in specs]
        assert "read_file" in names
        assert "write_file" in names
        assert "edit_file" in names
        assert "bash" in names


class TestPermissionEngine:
    """Tests for PermissionEngine."""

    def test_permission_engine_allow_low_risk(self) -> None:
        engine = PermissionEngine()
        spec = ToolSpec(
            tool_name="read_file",
            namespace="core",
            description="Read file",
            operation_kind=ToolOperationKind.READ,
            default_risk_level=ToolRiskLevel.LOW,
        )
        request = PermissionRequest(
            tool_name="read_file",
            workspace_id="ws-001",
            session_id="sess-001",
            run_id="run-001",
        )
        policy = engine.evaluate(request, spec)
        assert policy.decision == ToolPolicyDecision.ALLOW

    def test_permission_engine_approval_for_high_risk(self) -> None:
        engine = PermissionEngine(risk_approval_threshold=ToolRiskLevel.HIGH)
        spec = ToolSpec(
            tool_name="bash",
            namespace="core",
            description="Execute shell",
            operation_kind=ToolOperationKind.EXECUTE,
            default_risk_level=ToolRiskLevel.HIGH,
        )
        request = PermissionRequest(
            tool_name="bash",
            workspace_id="ws-001",
            session_id="sess-001",
            run_id="run-001",
        )
        policy = engine.evaluate(request, spec)
        assert policy.decision == ToolPolicyDecision.APPROVAL_REQUIRED

    def test_permission_engine_grant_bypass(self) -> None:
        engine = PermissionEngine(risk_approval_threshold=ToolRiskLevel.HIGH)
        spec = ToolSpec(
            tool_name="bash",
            namespace="core",
            description="Execute shell",
            operation_kind=ToolOperationKind.EXECUTE,
            default_risk_level=ToolRiskLevel.HIGH,
        )
        request = PermissionRequest(
            tool_name="bash",
            workspace_id="ws-001",
            session_id="sess-001",
            run_id="run-001",
        )

        engine.issue_grant(
            tool_name="bash",
            workspace_id="ws-001",
            session_id="sess-001",
            run_id="run-001",
        )

        policy = engine.evaluate(request, spec)
        assert policy.decision == ToolPolicyDecision.ALLOW


class TestOutsideZonePolicy:
    """Tests for OutsideZonePolicy."""

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-style paths don't resolve on Windows")
    def test_outside_zone_policy_blacklist(self) -> None:
        policy = OutsideZonePolicy(
            blacklist_paths=("/etc", "/sys"),
        )
        assert policy.is_blacklisted("/etc/passwd")
        assert policy.is_blacklisted("/sys/kernel")
        assert not policy.is_blacklisted("/home/user/file.txt")

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-style paths don't resolve on Windows")
    def test_outside_zone_policy_whitelist(self) -> None:
        policy = OutsideZonePolicy(
            whitelist_paths=("/home/user",),
        )
        assert policy.is_whitelisted("/home/user/file.txt")
        assert not policy.is_whitelisted("/etc/passwd")

    def test_outside_zone_policy_windows_path_handling(self) -> None:
        policy = OutsideZonePolicy(
            blacklist_paths=("C:\\Windows",),
        )
        assert policy.is_blacklisted("C:\\Windows\\System32")
        assert not policy.is_blacklisted("C:\\Users\\test")


class TestSkillResolver:
    """Tests for SkillResolver."""

    def test_skill_spec_creation(self) -> None:
        spec = SkillSpec(
            skill_name="test_skill",
            layer=SkillLayer.INTERNAL,
            description="Test skill",
            instructions="Test instructions",
        )
        assert spec.skill_name == "test_skill"
        assert spec.full_name == "core.test_skill"
        assert spec.is_internal is True

    def test_skill_resolver_basic(self) -> None:
        resolver = SkillResolver()

        internal_spec = SkillSpec(
            skill_name="internal_skill",
            layer=SkillLayer.INTERNAL,
            description="Internal skill",
            instructions="Internal instructions",
        )
        resolver.internal_registry.register(internal_spec)

        global_spec = SkillSpec(
            skill_name="global_skill",
            layer=SkillLayer.GLOBAL,
            description="Global skill",
            instructions="Global instructions",
        )
        resolver.global_registry.register(global_spec)

        resolved = resolver.resolve(
            workspace_id="ws-001",
            session_id="sess-001",
            run_id="run-001",
        )

        assert resolved.skill_count == 2
        assert resolved.has_skill("internal_skill")
        assert resolved.has_skill("global_skill")

    def test_skill_resolver_internal_protection(self) -> None:
        resolver = SkillResolver()

        internal_spec = SkillSpec(
            skill_name="protected",
            layer=SkillLayer.INTERNAL,
            description="Internal protected skill",
            instructions="Internal instructions",
        )
        resolver.internal_registry.register(internal_spec)

        workspace_registry = resolver.get_or_create_workspace_registry("ws-001")
        workspace_spec = SkillSpec(
            skill_name="protected",
            layer=SkillLayer.WORKSPACE,
            description="Workspace attempt to override",
            instructions="Workspace instructions",
        )
        workspace_registry.register(workspace_spec)

        resolved = resolver.resolve(
            workspace_id="ws-001",
            session_id="sess-001",
            run_id="run-001",
        )

        skill = resolved.get_skill("protected")
        assert skill is not None
        assert skill.source_layer == SkillLayer.INTERNAL


class TestMemoryResolver:
    """Tests for MemoryResolver."""

    def test_memory_entry_creation(self) -> None:
        entry = MemoryEntry(
            entry_id="entry-001",
            scope=MemoryScope.SESSION,
            kind=MemoryKind.FACT,
            content="This is a test fact",
        )
        assert entry.entry_id == "entry-001"
        assert entry.scope == MemoryScope.SESSION

    def test_memory_resolver_basic(self) -> None:
        resolver = MemoryResolver()

        session_entry = MemoryEntry(
            entry_id="session-001",
            scope=MemoryScope.SESSION,
            kind=MemoryKind.SCRATCHPAD,
            content="Session scratchpad content",
        )
        resolver.write(session_entry, session_id="sess-001", workspace_id="ws-001")

        workspace_entry = MemoryEntry(
            entry_id="workspace-001",
            scope=MemoryScope.WORKSPACE,
            kind=MemoryKind.EXPERIENCE,
            content="Workspace experience content",
        )
        resolver.write(workspace_entry, workspace_id="ws-001")

        global_entry = MemoryEntry(
            entry_id="global-001",
            scope=MemoryScope.GLOBAL,
            kind=MemoryKind.PREFERENCE,
            content="User preference content",
        )
        resolver.write(global_entry)

        resolved = resolver.resolve(session_id="sess-001", workspace_id="ws-001")

        assert resolved.total_entry_count == 3
        assert len(resolved.session_entries) == 1
        assert len(resolved.workspace_entries) == 1
        assert len(resolved.global_entries) == 1

    def test_memory_resolver_priority_order(self) -> None:
        resolver = MemoryResolver()

        session_entry = MemoryEntry(
            entry_id="entry-001",
            scope=MemoryScope.SESSION,
            kind=MemoryKind.FACT,
            content="Session fact",
        )
        resolver.write(session_entry, session_id="sess-001", workspace_id="ws-001")

        resolved = resolver.resolve(session_id="sess-001", workspace_id="ws-001")
        entries = resolved.get_all_entries()

        assert entries[0].scope == MemoryScope.SESSION

    def test_memory_resolver_promotion(self) -> None:
        resolver = MemoryResolver()

        session_entry = MemoryEntry(
            entry_id="promote-001",
            scope=MemoryScope.SESSION,
            kind=MemoryKind.SUMMARY,
            content="Summary to promote",
        )
        resolver.write(
            session_entry,
            session_id="sess-001",
            workspace_id="ws-001",
            promote_to_workspace=True,
        )

        resolved = resolver.resolve(session_id="sess-001", workspace_id="ws-001")
        assert len(resolved.workspace_entries) == 1
        assert resolved.workspace_entries[0].metadata.get("promoted_from") == "session"

    def test_memory_search(self) -> None:
        resolver = MemoryResolver()

        entry1 = MemoryEntry(
            entry_id="search-001",
            scope=MemoryScope.SESSION,
            kind=MemoryKind.FACT,
            content="Python is a programming language",
            tags=("python", "programming"),
        )
        resolver.write(entry1, session_id="sess-001", workspace_id="ws-001")

        entry2 = MemoryEntry(
            entry_id="search-002",
            scope=MemoryScope.SESSION,
            kind=MemoryKind.FACT,
            content="JavaScript is also a programming language",
            tags=("javascript", "programming"),
        )
        resolver.write(entry2, session_id="sess-001", workspace_id="ws-001")

        resolved = resolver.resolve(session_id="sess-001", workspace_id="ws-001")

        python_results = resolved.search_content("Python")
        assert len(python_results) == 1

        programming_results = resolved.get_entries_by_tag("programming")
        assert len(programming_results) == 2
