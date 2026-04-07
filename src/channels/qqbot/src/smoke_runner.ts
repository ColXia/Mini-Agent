/**
 * QQ channel smoke runner.
 *
 * Runs the synthetic message flow against a real gateway endpoint by using
 * QQBotChannel.processSmokeMessage, so no upstream QQ network dependency is required.
 */

import * as path from "path";
import { QQBotChannel } from "./channel";
import { HTTPGatewayClient } from "./gateway_client";
import { MemorySessionStore } from "./session_store";

function parseBoolean(raw: string | undefined, fallback: boolean): boolean {
  const value = String(raw || "").trim().toLowerCase();
  if (!value) {
    return fallback;
  }
  return value === "1" || value === "true" || value === "on" || value === "yes";
}

function parseCsv(raw: string | undefined, defaults: string[]): string[] {
  const source = String(raw || "").trim();
  if (!source) {
    return defaults;
  }
  const items = source
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return items.length ? items : defaults;
}

function hasReplyContaining(replies: string[], keyword: string): boolean {
  const lower = keyword.toLowerCase();
  return replies.some((item) => String(item || "").toLowerCase().includes(lower));
}

async function main(): Promise<void> {
  const gatewayBaseUrl = process.env.MINI_AGENT_GATEWAY_BASE || "http://127.0.0.1:8008";
  const gatewayAuthToken =
    process.env.QQBOT_GATEWAY_AUTH_TOKEN ||
    process.env.MINI_AGENT_GATEWAY_AUTH_TOKEN ||
    "";
  const defaultWorkspace = process.env.QQBOT_DEFAULT_WORKSPACE || path.resolve(process.cwd(), "workspace");
  const defaultDryRun = parseBoolean(process.env.QQBOT_DEFAULT_DRY_RUN, true);
  const sessionStorePath =
    process.env.QQBOT_SESSION_STORE_PATH || path.resolve(process.cwd(), ".qqbot_smoke_sessions.json");
  const allowedWorkspaceRoots = parseCsv(process.env.QQBOT_ALLOWED_WORKSPACE_ROOTS, [
    process.cwd(),
    path.resolve(process.cwd(), "workspace"),
  ]);
  const maxMessageChars = Number.parseInt(process.env.QQBOT_MAX_MESSAGE_CHARS || "12000", 10);
  const maxReplyChunkSize = Number.parseInt(process.env.QQBOT_MAX_REPLY_CHUNK_SIZE || "1400", 10);
  const smokeMessage = process.env.QQBOT_SMOKE_MESSAGE || "qq smoke message";
  const smokeGroupId = process.env.QQBOT_SMOKE_GROUP_ID || "smoke-group-001";
  const smokeSenderId = process.env.QQBOT_SMOKE_SENDER_ID || "smoke-user-001";
  const rejectedWorkspace =
    process.env.QQBOT_SMOKE_REJECT_WORKSPACE || path.join(path.parse(process.cwd()).root, "outside-smoke-workspace");

  const gatewayClient = new HTTPGatewayClient({
    baseUrl: gatewayBaseUrl,
    timeout: 120000,
    gatewayAuthToken,
  });
  const sessionStore = new MemorySessionStore({ filePath: sessionStorePath });

  const channel = new QQBotChannel(
    {
      appid: "smoke-app-id",
      secret: "smoke-secret",
      sandbox: true,
      mode: "webhook",
      allowedWorkspaceRoots,
      maxMessageChars,
      maxReplyChunkSize,
    },
    gatewayClient,
    sessionStore,
    defaultWorkspace,
    defaultDryRun
  );

  const eventOptions = {
    groupOpenId: smokeGroupId,
    senderId: smokeSenderId,
    eventName: "message.group.smoke",
  };

  const setWorkspaceReplies = await channel.processSmokeMessage(
    `/workspace ${allowedWorkspaceRoots[0]}`,
    eventOptions
  );
  if (!hasReplyContaining(setWorkspaceReplies, "Workspace set to:")) {
    throw new Error("QQ smoke failed: /workspace allow-path command did not succeed.");
  }

  const rejectWorkspaceReplies = await channel.processSmokeMessage(
    `/workspace ${rejectedWorkspace}`,
    eventOptions
  );
  if (!hasReplyContaining(rejectWorkspaceReplies, "Workspace rejected")) {
    throw new Error("QQ smoke failed: /workspace reject-path guardrail did not trigger.");
  }

  const chatReplies = await channel.processSmokeMessage(smokeMessage, eventOptions);
  const mergedReply = chatReplies.join("\n").trim();
  if (!mergedReply) {
    throw new Error("QQ smoke failed: chat flow produced empty reply.");
  }

  console.log(
    JSON.stringify(
      {
        status: "ok",
        checks: {
          workspace_allow: true,
          workspace_reject: true,
          chat_reply_length: mergedReply.length,
          chat_reply_count: chatReplies.length,
        },
        replies: chatReplies,
      },
      null,
      2
    )
  );
}

main().catch((error: any) => {
  console.error(`QQ channel smoke runner failed: ${error?.message || String(error)}`);
  process.exit(1);
});

