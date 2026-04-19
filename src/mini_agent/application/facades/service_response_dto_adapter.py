"""Shared adapters from user-service payloads into transport DTO contracts."""

from __future__ import annotations

from mini_agent.interfaces.agent import (
    MainAgentRunSummary,
    MainAgentWorkspaceRuntimeSummary,
    MainAgentWorkspaceSummary,
)
from mini_agent.interfaces.model import (
    MainAgentModelBindingDiagnostics,
    MainAgentModelBindingSummary,
    MainAgentModelCandidateListResponse,
    MainAgentModelCapabilities,
)


def model_candidate_list_response(payload: object) -> MainAgentModelCandidateListResponse:
    if isinstance(payload, list):
        items = list(payload)
    elif isinstance(payload, dict):
        items = list(payload.get("items") or [])
    else:
        items = list(getattr(payload, "items", []) or [])
    return MainAgentModelCandidateListResponse.model_validate({"items": items}, from_attributes=True)


def model_binding_summary_response(payload: object) -> MainAgentModelBindingSummary:
    return MainAgentModelBindingSummary.model_validate(payload, from_attributes=True)


def model_capabilities_response(payload: object) -> MainAgentModelCapabilities:
    return MainAgentModelCapabilities.model_validate(payload, from_attributes=True)


def model_binding_diagnostics_response(payload: object) -> MainAgentModelBindingDiagnostics:
    return MainAgentModelBindingDiagnostics.model_validate(payload, from_attributes=True)


def workspace_summary_response(payload: object) -> MainAgentWorkspaceSummary:
    return MainAgentWorkspaceSummary.model_validate(payload, from_attributes=True)


def workspace_runtime_summary_response(payload: object) -> MainAgentWorkspaceRuntimeSummary:
    return MainAgentWorkspaceRuntimeSummary.model_validate(payload, from_attributes=True)


def run_summary_response(payload: object) -> MainAgentRunSummary:
    return MainAgentRunSummary.model_validate(payload, from_attributes=True)


__all__ = [
    "model_binding_diagnostics_response",
    "model_binding_summary_response",
    "model_candidate_list_response",
    "model_capabilities_response",
    "run_summary_response",
    "workspace_runtime_summary_response",
    "workspace_summary_response",
]
