"""Interface-layer contracts for hard-refactor API v1."""

from .agent import (
    MainAgentChatRequest,
    MainAgentChatResponse,
    MainAgentSessionMutationResponse,
    MainAgentSessionSummary,
)
from .channel import ChannelMessageRequest, ChannelMessageResponse
from .common import ApiEnvelope, ApiError
from .novel import (
    ChapterRollbackRequest,
    ChapterVersionMetaUpdateRequest,
    NovelChapterResponse,
    NovelChapterSaveRequest,
    NovelCoverRequest,
    NovelFinalizeRequest,
    NovelIllustrateRequest,
    NovelSetupRequest,
    NovelWriteRequest,
)
from .ops import (
    StudioMemoryDailyResponse,
    StudioMemoryNote,
    StudioMemorySearchResponse,
    StudioMemorySummaryResponse,
    StudioProviderDeleteResponse,
    StudioProviderHealthResponse,
    StudioProviderListResponse,
    StudioProviderSummary,
    StudioProviderUpsertRequest,
)
from .system import MainAgentRuntimeDiagnostics, SystemHealthResponse

__all__ = [
    "ApiEnvelope",
    "ApiError",
    "ChannelMessageRequest",
    "ChannelMessageResponse",
    "MainAgentChatRequest",
    "MainAgentChatResponse",
    "MainAgentSessionMutationResponse",
    "MainAgentSessionSummary",
    "ChapterRollbackRequest",
    "ChapterVersionMetaUpdateRequest",
    "NovelChapterResponse",
    "NovelChapterSaveRequest",
    "NovelCoverRequest",
    "NovelFinalizeRequest",
    "NovelIllustrateRequest",
    "NovelSetupRequest",
    "NovelWriteRequest",
    "StudioMemoryDailyResponse",
    "StudioMemoryNote",
    "StudioMemorySearchResponse",
    "StudioMemorySummaryResponse",
    "StudioProviderDeleteResponse",
    "StudioProviderHealthResponse",
    "StudioProviderListResponse",
    "StudioProviderSummary",
    "StudioProviderUpsertRequest",
    "MainAgentRuntimeDiagnostics",
    "SystemHealthResponse",
]
