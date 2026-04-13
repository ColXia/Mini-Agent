import path from "node:path";

import {
  ensureWorkspaceInAllowed,
  limitInboundMessage,
  normalizeAllowedWorkspaceRoots,
  normalizeInt,
  parseCsvEnv,
} from "./guardrails.mjs";
import { gatewayRequest, iterateSseEvents } from "./gateway_io.mjs";

function cleanText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function parseBoolean(raw, fallback) {
  const value = String(raw || "").trim().toLowerCase();
  if (!value) {
    return fallback;
  }
  return value === "1" || value === "true" || value === "on" || value === "yes";
}

function assertCondition(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function main() {
  const gatewayBase = (process.env.MINI_AGENT_GATEWAY_BASE || "http://127.0.0.1:8008").replace(/\/+$/, "");
  const gatewayAuthToken =
    cleanText(process.env.QQBOT_GATEWAY_AUTH_TOKEN || "") ||
    cleanText(process.env.MINI_AGENT_GATEWAY_AUTH_TOKEN || "");
  const qqbotName = cleanText(process.env.QQBOT_NAME || "nyonyo") || "nyonyo";
  const defaultDryRun = parseBoolean(process.env.QQBOT_DEFAULT_DRY_RUN, true);
  const allowedWorkspaceRoots = normalizeAllowedWorkspaceRoots(
    parseCsvEnv(process.env.QQBOT_ALLOWED_WORKSPACE_ROOTS),
    process.cwd()
  );
  const maxMessageChars = normalizeInt(process.env.QQBOT_MAX_MESSAGE_CHARS, 12000, 512, 200000);
  const defaultWorkspace = ensureWorkspaceInAllowed(
    process.env.QQBOT_DEFAULT_WORKSPACE || process.cwd(),
    allowedWorkspaceRoots
  );
  const smokeMessage = process.env.QQBOT_SMOKE_MESSAGE || "qq smoke message";
  const rejectedWorkspace =
    process.env.QQBOT_SMOKE_REJECT_WORKSPACE ||
    path.join(path.parse(process.cwd()).root, "outside-smoke-workspace");

  const state = {
    key: process.env.QQBOT_SMOKE_GROUP_ID || "smoke-group-001",
    botName: qqbotName,
    sessionId: "",
    workspaceDir: defaultWorkspace,
    dryRun: defaultDryRun,
  };
  const senderId = cleanText(process.env.QQBOT_SMOKE_SENDER_ID || "smoke-user-001");

  const allowedWorkspace = ensureWorkspaceInAllowed(allowedWorkspaceRoots[0], allowedWorkspaceRoots);
  state.workspaceDir = allowedWorkspace;
  assertCondition(state.workspaceDir === allowedWorkspace, "workspace allow-path check failed");

  let rejected = false;
  try {
    ensureWorkspaceInAllowed(rejectedWorkspace, allowedWorkspaceRoots);
  } catch {
    rejected = true;
  }
  assertCondition(rejected, "workspace reject-path guardrail did not trigger");

  async function forwardMessage(rawText) {
    const params = new URLSearchParams();
    params.set("message", limitInboundMessage(rawText, maxMessageChars));
    params.set("workspace_dir", state.workspaceDir);
    params.set("dry_run", String(Boolean(state.dryRun)));
    params.set("surface", "qq");
    params.set("channel_type", "qq");
    params.set("conversation_id", state.key);
    if (senderId) {
      params.set("sender_id", senderId);
    }
    if (state.sessionId) {
      params.set("session_id", state.sessionId);
    } else {
      params.set("session_title_hint", state.botName);
    }

    const response = await gatewayRequest(
      gatewayBase,
      gatewayAuthToken,
      `/api/v1/agent/chat/stream?${params.toString()}`,
      {
        headers: {
          Accept: "text/event-stream",
        },
      }
    );

    let accumulatedReply = "";
    for await (const item of iterateSseEvents(response)) {
      const eventType = cleanText(item?.event).toLowerCase() || "message";
      const data = item?.data && typeof item.data === "object" ? item.data : {};
      if (eventType === "session") {
        const sessionId = cleanText(data?.session_id);
        if (sessionId) {
          state.sessionId = sessionId;
        }
        continue;
      }
      if (eventType === "delta") {
        accumulatedReply += String(data?.chunk || "");
        continue;
      }
      if (eventType === "done") {
        const sessionId = cleanText(data?.session_id);
        if (sessionId) {
          state.sessionId = sessionId;
        }
        return String(data?.reply || "").trim() || accumulatedReply.trim();
      }
      if (eventType === "error") {
        throw new Error(cleanText(data?.message) || "agent stream failed");
      }
    }

    return accumulatedReply.trim();
  }

  const firstReply = await forwardMessage(smokeMessage);
  assertCondition(Boolean(firstReply), "chat flow produced empty reply");
  assertCondition(Boolean(state.sessionId), "chat flow did not bind a session id");
  const firstSessionId = state.sessionId;

  const secondReply = await forwardMessage(`${smokeMessage} second`);
  assertCondition(Boolean(secondReply), "follow-up chat flow produced empty reply");
  assertCondition(state.sessionId === firstSessionId, "follow-up chat changed the bound session unexpectedly");

  const resetResponse = await gatewayRequest(
    gatewayBase,
    gatewayAuthToken,
    `/api/v1/agent/sessions/${encodeURIComponent(state.sessionId)}/reset`,
    {
      method: "POST",
    }
  );
  assertCondition(resetResponse.ok, "reset request failed");

  console.log(
    JSON.stringify(
      {
        status: "ok",
        checks: {
          workspace_allow: true,
          workspace_reject: true,
          chat_reply_length: firstReply.length,
          followup_reply_length: secondReply.length,
          session_bound: Boolean(state.sessionId),
          reset: true,
        },
        session_id: state.sessionId,
      },
      null,
      2
    )
  );
}

main().catch((error) => {
  console.error(`QQ channel smoke runner failed: ${error?.message || String(error)}`);
  process.exit(1);
});
