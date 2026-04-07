"""Mini memory core package (P12 kickoff)."""

from mini_agent.memory.engram import Engram, MemoryLayer
from mini_agent.memory.memoria_engine import MemoriaEngine, MemoryQueryResult
from mini_agent.memory.memory_files import (
    MemoryFileLayout,
    append_memory_note,
    discover_memory_layout,
    ensure_memory_file,
)
from mini_agent.memory.consolidation import MemoryConsolidationPipeline
from mini_agent.memory.consolidation_phase1 import Phase1Artifact, Phase1ArtifactStore, Phase1Extractor
from mini_agent.memory.consolidation_phase2 import Phase2Consolidator, Phase2Result
from mini_agent.memory.consolidation_scheduler import ConsolidationJobStore, ConsolidationScheduler
from mini_agent.memory.builtin_memory import BuiltinMemoryProvider
from mini_agent.memory.memory_provider import MemoryProvider
from mini_agent.memory.relevance import ConsolidatedMemoryRelevanceRetriever, RelevanceMemoryHit
from mini_agent.memory.session_search import SessionSearchIndex

__all__ = [
    "Engram",
    "MemoryLayer",
    "MemoriaEngine",
    "MemoryQueryResult",
    "MemoryFileLayout",
    "discover_memory_layout",
    "ensure_memory_file",
    "append_memory_note",
    "MemoryProvider",
    "BuiltinMemoryProvider",
    "MemoryConsolidationPipeline",
    "Phase1Artifact",
    "Phase1Extractor",
    "Phase1ArtifactStore",
    "Phase2Consolidator",
    "Phase2Result",
    "ConsolidationJobStore",
    "ConsolidationScheduler",
    "ConsolidatedMemoryRelevanceRetriever",
    "RelevanceMemoryHit",
    "SessionSearchIndex",
]
