# Mini-Agent Lite Addendum (v1)

> **状态**: ✅ 活跃
> **创建日期**: 2026-04-05
> **最后更新**: 2026-04-06
> **文档索引**: [DOCS_INDEX.md](./DOCS_INDEX.md)

Created: 2026-04-05

## Why this addendum
The transformation plan defines a broad platform target.
This addendum constrains implementation to Mini-Agent principles:
- small
- fast
- strong

## Product Principle (non-negotiable)
1. Keep only core user-value capabilities in default path.
2. Avoid platform-scale expansion unless explicitly needed.
3. Prefer bounded slices with clear test coverage.

## Mini Definition (Capability Strong, Architecture Lean)
`Mini` does not mean capability downgrade.
It means:
1. Core capabilities must be complete and strong.
2. Architecture stays lean with one canonical implementation path.
3. Avoid duplicate control planes, compatibility shells, and speculative layers.
4. Keep integration surface minimal while preserving core power.

## Scope Contract

### Must (default)
- Agent turn loop with execution policy guards.
- Session persistence/restore + checkpoint basics.
- Core observability (health, run events, essential export).
- Minimal MCP compatibility and safe execution boundaries.

### Should (when direct value)
- Drift diagnostics and focused trend analytics.
- Targeted filtering and triage affordances.

### Defer (unless explicitly requested)
- Full multi-channel platform operation.
- Heavy multi-agent orchestration defaults.
- Large plugin ecosystem behavior expansion.
- Enterprise-only control plane complexity.

## Mini-First Phase Map (P12+)

### Phase A (must-do core)
1. Memory core minimal path:
   - STM/LTM abstraction + relevance retrieval baseline.
   - `GEMINI.md`/`MEMORY.md` file discovery and safe update.
2. Model manager minimal path:
   - custom provider config + mapper + failover baseline.
3. Code agent minimal path:
   - stable turn loop + declarative tool invocation + context budget.

### Phase B (controlled enhancements)
1. Focused session search (FTS5) for debugging/recovery.
2. Two-phase consolidation only after Phase A metrics are stable.
3. Drift/trend diagnostics remain lightweight and endpoint-driven.

### Phase C (explicit opt-in only)
1. Multi-agent coordinator mode by feature flag.
2. Browser automation and future remote-adapter expansion only after core reliability.
3. Enterprise-heavy control-plane capabilities only when required.

## Delivery Rule
Use vertical slices to reach full core capability:
1. Start from minimal runnable skeleton.
2. Iterate to full-strength behavior for each core module.
3. Keep complexity growth proportional and test-backed.

## Complexity Budget Rule
Any new feature should satisfy at least 3/4:
1. Directly improves current workflow reliability or speed.
2. Can be delivered in one bounded slice.
3. Adds no hidden operational burden.
4. Has deterministic tests in stable suite.

## Source Index Anchor
When context is lost, recover from:
- `C:/Users/Conli/ai开源项目/00-mini-agent-index/README.md`
- `C:/Users/Conli/ai开源项目/00-mini-agent-index/restore/RECOVERY_CHECKLIST.md`
- `C:/Users/Conli/ai开源项目/00-mini-agent-index/projects/INDEX_MAP.md`
