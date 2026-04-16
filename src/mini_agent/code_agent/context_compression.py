"""Backward-compatible context-compression facade over agent-core context compaction."""

from mini_agent.agent_core.context.context_compaction import (
    CompressionStats,
    ContextCompressionResult,
    LayeredContextCompactor,
    estimate_tokens,
)

__all__ = [
    "CompressionStats",
    "ContextCompressionResult",
    "LayeredContextCompactor",
    "estimate_tokens",
]
