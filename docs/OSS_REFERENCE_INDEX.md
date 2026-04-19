# OSS Reference Implementation Index

> **状态**: ✅ 活跃
> **最后更新**: 2026-04-06
> **文档索引**: [DOCS_INDEX.md](./DOCS_INDEX.md)

Updated: 2026-04-06

## Purpose
This index maps concrete upstream implementations to Mini-Agent refactor targets.

## Deep Fusion Sources (P12+ Transformation)

### Memoria (Memory Engine)

| Capability | Upstream File | Mini-Agent Target |
| --- | --- | --- |
| STM/LTM engram lifecycle | `memoria-master/memoria/memoria.py` | `mini_agent/memory/memoria_engine.py` |
| Engram data structure | `memoria-master/memoria/engram.py` | `mini_agent/memory/engram.py` |
| Lifespan decay + extension | `memoria-master/memoria/memoria.py:adjust_lifespan_and_memories` | `mini_agent/memory/memoria_engine.py` |
| Fire-together-wire-together | `memoria-master/memoria/engram.py:fire_together_wire_together` | `mini_agent/memory/memoria_engine.py` |
| LTM DFS graph traversal | `memoria-master/memoria/memoria.py:_search_longterm_memories_with_initials` | `mini_agent/memory/memoria_engine.py` |
| Abstractor (cross-attention compression) | `memoria-master/memoria/abstractor.py` | `mini_agent/memory/embedder.py` |

### Codex (Code Agent + Memory Consolidation)

| Capability | Upstream File | Mini-Agent Target |
| --- | --- | --- |
| Submission loop (event channel) | `codex-main/codex-rs/core/src/codex.rs:submission_loop` | `mini_agent/agent_core/execution/agent_loop.py` |
| TurnContext snapshot | `codex-main/codex-rs/core/src/codex.rs` | `mini_agent/agent_core/context/loop_context.py` |
| Two-phase memory pipeline | `codex-main/codex-rs/core/src/memories/README.md` | `mini_agent/memory/consolidation.py` |
| Phase 1 rollout extraction | `codex-main/codex-rs/core/src/memories/phase1.rs` | `mini_agent/memory/consolidation_phase1.py` |
| Phase 2 global consolidation | `codex-main/codex-rs/core/src/memories/phase2.rs` | `mini_agent/memory/consolidation_phase2.py` |
| Job leasing + watermarks | `codex-main/codex-rs/core/src/memories/storage.rs` | `mini_agent/memory/consolidation_scheduler.py` |
| Windows sandbox (Restricted Token) | `codex-main/codex-rs/sandboxing/` | `mini_agent/agent_core/execution/sandbox/windows.py` |
| Network isolation proxy | `codex-main/codex-rs/sandboxing/` | `mini_agent/agent_core/execution/sandbox/network.py` |

### Gemini CLI (Tool System + Memory Files)

| Capability | Upstream File | Mini-Agent Target |
| --- | --- | --- |
| DeclarativeTool pattern | `gemini-cli-main/packages/core/src/tools/tools.ts` | `mini_agent/agent_core/execution/tools/builder.py` |
| ToolInvocation separation | `gemini-cli-main/packages/core/src/tools/tools.ts` | `mini_agent/agent_core/execution/tools/invocation.py` |
| GEMINI.md hierarchical discovery | `gemini-cli-main/packages/core/src/context/memoryContextManager.ts` | `mini_agent/memory/memory_files.py` |
| MemoryTool (self-save) | `gemini-cli-main/packages/core/src/tools/memoryTool.ts` | `mini_agent/tools/memory_tool.py` |
| Reverse token budget compression | `gemini-cli-main/packages/core/src/context/chatCompressionService.ts` | `mini_agent/agent_core/context/context_compaction.py` |
| Tool output masking | `gemini-cli-main/packages/core/src/context/` | `mini_agent/agent_core/execution/output_masking.py` |
| MCP full client (OAuth+3 transports) | `gemini-cli-main/packages/core/src/tools/mcp-client.ts` | `mini_agent/agent_core/execution/mcp_client.py` |
| Scheduler state machine | `gemini-cli-main/packages/core/src/scheduler/scheduler.ts` | `mini_agent/agent_core/execution/scheduler.py` |
| AgentLoopContext interface | `gemini-cli-main/packages/core/src/config/agent-loop-context.ts` | `mini_agent/agent_core/context/loop_context.py` |

### Hermes Agent (Self-Learning + Search + Delegation)

| Capability | Upstream File | Mini-Agent Target |
| --- | --- | --- |
| FTS5 session search | `hermes-agent-main/tools/session_search_tool.py` | `mini_agent/memory/session_search.py` |
| SQLite FTS5 schema + triggers | `hermes-agent-main/hermes_state.py` | `mini_agent/memory/session_db.py` |
| Truncate-around-matches algorithm | `hermes-agent-main/tools/session_search_tool.py` | `mini_agent/memory/session_search.py` |
| Frozen snapshot memory pattern | `hermes-agent-main/tools/memory_tool.py` | `mini_agent/tools/memory_tool.py` |
| Self-learning skill creation | `hermes-agent-main/tools/skill_manager_tool.py` | `mini_agent/agent_core/skills/self_improve.py` |
| Progressive disclosure (3 tiers) | `hermes-agent-main/tools/skills_tool.py` | `mini_agent/agent_core/skills/loader.py` |
| Sub-agent delegation | `hermes-agent-main/tools/delegate_tool.py` | `mini_agent/agent_core/delegation.py` |
| MemoryProvider ABC | `hermes-agent-main/agent/memory_provider.py` | `mini_agent/memory/memory_provider.py` |
| Honcho user modeling | `hermes-agent-main/plugins/memory/honcho/` | `mini_agent/memory/user_modeling.py` |
| BasePlatformAdapter | `hermes-agent-main/gateway/platforms/base.py` | (not needed; active remote adapter is QQ-only) |

### OpenClaw (Agent Core)

| Capability | Upstream File | Mini-Agent Target |
| --- | --- | --- |
| 8-level binding routing | `openclaw-main/src/routing/resolve-route.ts` | `mini_agent/agent_core/route_resolver.py` |
| Session key construction | `openclaw-main/src/routing/session-key.ts` | `mini_agent/agent_core/session_key.py` |
| Skills platform (ClawHub) | `openclaw-main/src/agents/skills-clawhub.ts` | `mini_agent/agent_core/skills/registry.py` |
| Workspace skill loading | `openclaw-main/src/agents/skills/workspace.ts` | `mini_agent/agent_core/skills/loader.py` |
| Cron scheduler + isolated run | `openclaw-main/src/cron/isolated-agent/run.ts` | `mini_agent/agent_core/cron/isolated_run.py` |
| Browser CDP control | `openclaw-main/extensions/browser/src/browser/cdp.ts` | `mini_agent/agent_core/browser/cdp.py` |
| Chrome lifecycle | `openclaw-main/extensions/browser/src/browser/chrome.ts` | `mini_agent/agent_core/browser/chrome.py` |
| DM pairing system | `openclaw-main/src/pairing/pairing-store.ts` | `mini_agent/agent_core/security/pairing.py` |
| DM/group access policy | `openclaw-main/src/security/dm-policy-shared.ts` | `mini_agent/agent_core/security/policy.py` |
| Subagent registry | `openclaw-main/src/agents/subagent-registry.ts` | `mini_agent/agent_core/delegation.py` |

### CC Switch (Model Manager)

| Capability | Upstream File | Mini-Agent Target |
| --- | --- | --- |
| Provider config model | `cc-switch-main/src-tauri/src/config.rs` | `mini_agent/model_manager/provider.py` |
| Circuit breaker (3-state) | `cc-switch-main/src-tauri/src/proxy/circuit_breaker.rs` | `mini_agent/model_manager/circuit_breaker.py` |
| Failover switch | `cc-switch-main/src-tauri/src/proxy/failover_switch.rs` | `mini_agent/model_manager/failover.py` |
| Request forwarder + retry | `cc-switch-main/src-tauri/src/proxy/forwarder.rs` | `mini_agent/model_manager/proxy_server.py` |
| Rectifier (thinking/cache) | `cc-switch-main/src-tauri/src/proxy/` | `mini_agent/model_manager/rectifier.py` |
| Model mapper | `cc-switch-main/src-tauri/src/proxy/model_mapper.rs` | `mini_agent/model_manager/model_mapper.py` |
| Provider presets | `cc-switch-main/src/config/` | (excluded, user-defined only) |

### extracted-src (Enterprise Code Agent)

| Capability | Upstream File | Mini-Agent Target |
| --- | --- | --- |
| Coordinator mode (Research→Synthesis→Implementation) | `extracted-src/src/coordinator/coordinatorMode.ts` | `mini_agent/agent_core/execution/coordinator.py` |
| Tool type system (40+ properties) | `extracted-src/src/Tool.ts` | `mini_agent/agent_core/execution/tools/attributes.py` |
| Query engine state machine | `extracted-src/src/query.ts` | `mini_agent/agent_core/execution/agent_loop.py` |
| Multi-layer permissions | `extracted-src/src/` | `mini_agent/agent_core/execution/permissions/policy.py` |
| Relevance memory retrieval | `extracted-src/src/memdir/` | `mini_agent/memory/relevance.py` |
| Daily log + nightly distillation | `extracted-src/src/memdir/` | `mini_agent/memory/daily_log.py` |
| Plugin system | `extracted-src/src/plugins/` | `mini_agent/plugins/` |
| Streaming tool executor | `extracted-src/src/query.ts` | `mini_agent/agent_core/execution/agent_loop.py` |

## Gateway / Session / Security (P2-P11)

| Capability | Upstream File | Mini-Agent Target |
| --- | --- | --- |
| Gateway single-entry architecture | `C:/Users/Conli/ai开源项目/openclaw-main/docs/concepts/architecture.md` | `gateway/core/*`, gateway runtime boundary |
| Session route model (DM/group/cron) | `C:/Users/Conli/ai开源项目/openclaw-main/docs/concepts/session.md` | interaction/session routing in `mini_agent/interaction/surface.py` + runtime session ownership in `mini_agent/runtime/session_state.py` |
| Session maintenance and pruning policy | `C:/Users/Conli/ai开源项目/openclaw-main/docs/concepts/session-pruning.md` | `mini_agent/agent_core/engine.py` pruning hook + retention policy |
| Gateway lock singleton | `C:/Users/Conli/ai开源项目/openclaw-main/docs/gateway/gateway-lock.md` | gateway startup lock in `src/apps/agent_studio_gateway/main.py` |
| Pairing and trust boundary | `C:/Users/Conli/ai开源项目/openclaw-main/docs/gateway/pairing.md` | channel/session access control layer |
| Sandbox/tool/elevated layered policy | `C:/Users/Conli/ai开源项目/openclaw-main/docs/gateway/sandbox-vs-tool-policy-vs-elevated.md` | runtime policy engine (`tools` + approvals) |
| Sandbox backends and scope | `C:/Users/Conli/ai开源项目/openclaw-main/docs/gateway/sandboxing.md` | future sandbox config model in `mini_agent/config.py` |
| Security audit baseline | `C:/Users/Conli/ai开源项目/openclaw-main/docs/gateway/security/index.md` | `doctor/audit` command design |

## ACP / Agent Runtime

| Capability | Upstream File | Mini-Agent Target |
| --- | --- | --- |
| ACP session binding and commands | `C:/Users/Conli/ai开源项目/openclaw-main/docs/tools/acp-agents.md` | `mini_agent/acp/__init__.py` lifecycle model |
| ACP IDE integration shape | `C:/Users/Conli/ai开源项目/hermes-agent-main/docs/acp-setup.md` | ACP integration docs and defaults |
| ACP JSON-RPC method model | `C:/Users/Conli/ai开源项目/gemini-cli-main/docs/cli/acp-mode.md` | protocol compatibility and fs proxy boundary |

## Session Persistence / Resume

| Capability | Upstream File | Mini-Agent Target |
| --- | --- | --- |
| CLI session retention and resume | `C:/Users/Conli/ai开源项目/gemini-cli-main/docs/cli/session-management.md` | persistent session backend + cleanup policy |
| Thread persistence and `resumeThread()` | `C:/Users/Conli/ai开源项目/codex-main/sdk/typescript/README.md` | resume API for CLI/Gateway/ACP |

## MCP / Config Sync

| Capability | Upstream File | Mini-Agent Target |
| --- | --- | --- |
| MCP discovery/execution/resource model | `C:/Users/Conli/ai开源项目/gemini-cli-main/docs/tools/mcp-server.md` | split `mcp_loader` into discovery/registry/executor |
| Multi-client MCP config mapping | `C:/Users/Conli/ai开源项目/cc-switch-main/docs/user-manual/en/3-extensions/3.1-mcp.md` | import/export adapters for Codex/Gemini/Claude formats |
| Codex MCP canonical table format | `C:/Users/Conli/ai开源项目/cc-switch-main/src-tauri/src/mcp/codex.rs` | codex config compatibility checks |
| Unified MCP service orchestration | `C:/Users/Conli/ai开源项目/cc-switch-main/src-tauri/src/services/mcp.rs` | central MCP profile sync service |
| Atomic config write helper | `C:/Users/Conli/ai开源项目/cc-switch-main/src-tauri/src/config.rs` | Mini-Agent atomic config write utility |

## Plugin / Memory

| Capability | Upstream File | Mini-Agent Target |
| --- | --- | --- |
| Plugin capability model | `C:/Users/Conli/ai开源项目/openclaw-main/docs/plugins/architecture.md` | removed in v11.1 hard cut; prior target was `mini_agent/plugins/registry.py` + `tests/test_plugin_registry.py` |
| Memory file strategy (`MEMORY.md` + daily notes) | `C:/Users/Conli/ai开源项目/openclaw-main/docs/concepts/memory.md` | `mini_agent/tools/note_tool.py` + `mini_agent/runtime/tooling.py` + `tests/test_note_tool.py` |

