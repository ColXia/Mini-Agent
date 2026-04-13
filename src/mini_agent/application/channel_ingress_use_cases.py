"""Application-layer use cases for channel ingress orchestration."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import HTTPException

from mini_agent.interfaces import (
    ChannelMessageRequest,
    ChannelMessageResponse,
    MainAgentChatRequest,
    MainAgentChatResponse,
    NovelCoverRequest,
    NovelFinalizeRequest,
    NovelIllustrateRequest,
    NovelSetupRequest,
    NovelWriteRequest,
)

from .interaction_request_adapter import ApplicationInteractionBinding
from .novel_service_use_cases import NovelServiceUseCases
from .remote_conversation_binding_service import RemoteConversationBindingService


RunMainAgentChatFn = Callable[[MainAgentChatRequest], Awaitable[MainAgentChatResponse]]
ResolveWorkspaceDirFn = Callable[[str | None], Path]
ToUtcIsoFn = Callable[[datetime], str]


class ChannelIngressUseCases:
    """Channel ingress orchestration with optional internal novel actions."""

    def __init__(
        self,
        *,
        run_main_agent_chat: RunMainAgentChatFn,
        novel_use_cases: NovelServiceUseCases,
        resolve_workspace_dir: ResolveWorkspaceDirFn,
        to_utc_iso: ToUtcIsoFn,
        remote_binding_service: RemoteConversationBindingService | None = None,
    ) -> None:
        self._run_main_agent_chat = run_main_agent_chat
        self._novel_use_cases = novel_use_cases
        self._resolve_workspace_dir = resolve_workspace_dir
        self._to_utc_iso = to_utc_iso
        self._remote_binding_service = remote_binding_service or RemoteConversationBindingService()

    async def handle_message(self, request: ChannelMessageRequest) -> ChannelMessageResponse:
        novel_action = self._extract_novel_action(request)
        if novel_action is not None:
            action, params = novel_action
            result = await self._dispatch_novel_action(action=action, params=params)
            workspace = self._resolve_workspace_dir(request.workspace_dir)
            session_id = request.session_id or self._build_novel_action_session_id(request)
            payload = {"kind": "novel_action", "action": action, "result": result}
            return ChannelMessageResponse(
                session_id=session_id,
                reply=json.dumps(payload, ensure_ascii=False),
                message_count=1,
                token_usage=0,
                workspace_dir=str(workspace),
                updated_at=self._to_utc_iso(datetime.now(timezone.utc)),
            )

        binding = ApplicationInteractionBinding.from_channel_message_request(request)
        resolved_session_id = self._remote_binding_service.resolve_session_id(
            channel_type=binding.channel_type,
            conversation_id=binding.conversation_id,
            explicit_session_id=request.session_id,
            dry_run=bool(request.dry_run),
        )
        chat_response = await self._run_main_agent_chat(
            binding.to_main_agent_chat_request(
                message=request.message,
                session_id=resolved_session_id,
                workspace_dir=request.workspace_dir,
                dry_run=request.dry_run,
            )
        )
        self._remote_binding_service.persist_binding(
            channel_type=binding.channel_type,
            conversation_id=binding.conversation_id,
            session_id=chat_response.session_id,
            workspace_dir=chat_response.workspace_dir,
            dry_run=bool(request.dry_run),
        )
        return ChannelMessageResponse(
            session_id=chat_response.session_id,
            reply=chat_response.reply,
            message_count=chat_response.message_count,
            token_usage=chat_response.token_usage,
            workspace_dir=chat_response.workspace_dir,
            updated_at=chat_response.updated_at,
        )

    def _extract_novel_action(self, request: ChannelMessageRequest) -> tuple[str, dict[str, Any]] | None:
        metadata = request.metadata or {}
        metadata_action = self._extract_novel_action_from_metadata(metadata)
        if metadata_action is not None:
            return metadata_action

        text = request.message.strip()
        if not text:
            return None
        if not text.lower().startswith("/novel"):
            return None
        return self._parse_novel_action_command(text)

    def _extract_novel_action_from_metadata(self, metadata: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
        if not metadata:
            return None
        novel_action = metadata.get("novel_action")
        if isinstance(novel_action, dict):
            action = str(novel_action.get("action", "")).strip().lower()
            params = novel_action.get("params")
            if not action:
                raise HTTPException(status_code=400, detail="Invalid novel_action metadata: missing action.")
            if params is None:
                return action, {}
            if not isinstance(params, dict):
                raise HTTPException(status_code=400, detail="Invalid novel_action metadata: params must be object.")
            return action, params

        intent = str(metadata.get("intent", "")).strip().lower()
        if intent != "novel_action":
            return None
        action = str(metadata.get("action", "")).strip().lower()
        params = metadata.get("params")
        if not action:
            raise HTTPException(status_code=400, detail="Invalid novel_action metadata: missing action.")
        if params is None:
            return action, {}
        if not isinstance(params, dict):
            raise HTTPException(status_code=400, detail="Invalid novel_action metadata: params must be object.")
        return action, params

    def _parse_novel_action_command(self, message: str) -> tuple[str, dict[str, Any]]:
        parts = message.split(maxsplit=2)
        if len(parts) < 2:
            raise HTTPException(
                status_code=400,
                detail="Invalid novel action command. Usage: /novel <action> [json-params].",
            )
        action = parts[1].strip().lower()
        if not action:
            raise HTTPException(
                status_code=400,
                detail="Invalid novel action command. Usage: /novel <action> [json-params].",
            )
        if len(parts) < 3:
            return action, {}
        raw_params = parts[2].strip()
        if not raw_params:
            return action, {}
        try:
            params = json.loads(raw_params)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid novel action JSON params: {exc.msg}",
            ) from exc
        if not isinstance(params, dict):
            raise HTTPException(status_code=400, detail="Novel action params must be JSON object.")
        return action, params

    async def _dispatch_novel_action(self, *, action: str, params: dict[str, Any]) -> dict[str, Any]:
        normalized = action.strip().lower()
        if normalized in {"config", "get_config"}:
            return await self._novel_use_cases.get_config(project_dir=self._optional_text(params.get("project_dir")))
        if normalized == "setup":
            request = NovelSetupRequest.model_validate(params)
            return await self._novel_use_cases.setup(
                topic=request.topic,
                genre=request.genre,
                num_chapters=request.num_chapters,
                words_per_chapter=request.words_per_chapter,
                project_dir=request.project_dir,
                dry_run=request.dry_run,
                api_host=request.api_host,
            )
        if normalized == "write":
            request = NovelWriteRequest.model_validate(params)
            return await self._novel_use_cases.write(
                chapter=request.chapter,
                guidance=request.guidance,
                project_dir=request.project_dir,
                dry_run=request.dry_run,
                api_host=request.api_host,
            )
        if normalized == "finalize":
            request = NovelFinalizeRequest.model_validate(params)
            return await self._novel_use_cases.finalize(
                chapter=request.chapter,
                project_dir=request.project_dir,
                dry_run=request.dry_run,
                api_host=request.api_host,
            )
        if normalized == "cover":
            request = NovelCoverRequest.model_validate(params)
            return await self._novel_use_cases.cover(
                prompt=request.prompt,
                output_name=request.output_name,
                aspect_ratio=request.aspect_ratio,
                style_type=request.style_type,
                style_weight=request.style_weight,
                project_dir=request.project_dir,
                dry_run=request.dry_run,
                api_host=request.api_host,
            )
        if normalized in {"illustrate", "illustrate_chapter"}:
            request = NovelIllustrateRequest.model_validate(params)
            return await self._novel_use_cases.illustrate(
                chapter=request.chapter,
                count=request.count,
                aspect_ratio=request.aspect_ratio,
                style_type=request.style_type,
                style_weight=request.style_weight,
                project_dir=request.project_dir,
                dry_run=request.dry_run,
                api_host=request.api_host,
            )

        supported = ["config", "setup", "write", "finalize", "cover", "illustrate"]
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported novel action '{action}'. Supported actions: {', '.join(supported)}.",
        )

    def _build_novel_action_session_id(self, request: ChannelMessageRequest) -> str:
        seed = f"{request.channel_type}|{request.conversation_id}"
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
        return f"novel-action-{digest}"

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
