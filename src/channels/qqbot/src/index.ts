/**
 * QQ Bot Channel entry point.
 *
 * Run this to start the QQ Bot channel.
 */

import * as dotenv from "dotenv";
import * as path from "path";
import { QQBotChannel } from "./channel";
import { HTTPGatewayClient } from "./gateway_client";
import { MemorySessionStore } from "./session_store";

// Load environment variables
dotenv.config({ path: path.resolve(__dirname, "../.env") });

async function main(): Promise<void> {
  // Configuration from environment
  const appid = process.env.QQBOT_APPID || "";
  const secret = process.env.QQBOT_SECRET || "";
  const mode = (process.env.QQBOT_MODE || "websocket").toLowerCase() as
    | "websocket"
    | "webhook";
  const sandbox = process.env.QQBOT_SANDBOX !== "false";
  const intents = (
    process.env.QQBOT_INTENTS ||
    "GUILD_MESSAGES,DIRECT_MESSAGE,GROUP_AT_MESSAGE_CREATE,C2C_MESSAGE_CREATE,PUBLIC_GUILD_MESSAGES"
  )
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  const gatewayBaseUrl =
    process.env.MINI_AGENT_GATEWAY_BASE || "http://127.0.0.1:8008";
  const gatewayAuthToken =
    process.env.QQBOT_GATEWAY_AUTH_TOKEN ||
    process.env.MINI_AGENT_GATEWAY_AUTH_TOKEN ||
    "";
  const defaultWorkspace =
    process.env.QQBOT_DEFAULT_WORKSPACE || process.cwd();
  const sessionStorePath =
    process.env.QQBOT_SESSION_STORE_PATH || path.resolve(process.cwd(), ".qqbot_sessions.json");
  const defaultDryRun =
    process.env.QQBOT_DEFAULT_DRY_RUN?.toLowerCase() === "true";
  const allowedWorkspaceRoots = (
    process.env.QQBOT_ALLOWED_WORKSPACE_ROOTS ||
    `${process.cwd()},${path.resolve(process.cwd(), "workspace")}`
  )
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const maxMessageChars = parseInt(process.env.QQBOT_MAX_MESSAGE_CHARS || "12000", 10);
  const maxReplyChunkSize = parseInt(process.env.QQBOT_MAX_REPLY_CHUNK_SIZE || "1400", 10);

  // Validate configuration
  if (!appid || !secret) {
    console.error("[qqbot-channel] Missing QQBOT_APPID or QQBOT_SECRET");
    process.exit(1);
  }

  // Create channel
  const gatewayClient = new HTTPGatewayClient({
    baseUrl: gatewayBaseUrl,
    timeout: 120000,
    gatewayAuthToken,
  });

  const sessionStore = new MemorySessionStore({ filePath: sessionStorePath });

  const channel = new QQBotChannel(
    {
      appid,
      secret,
      sandbox,
      mode,
      intents,
      webhookPath: process.env.QQBOT_WEBHOOK_PATH || "/qqbot/webhook",
      port: parseInt(process.env.QQBOT_PORT || "3520", 10),
      heartbeatInterval: parseInt(
        process.env.QQBOT_HEARTBEAT_INTERVAL || "45000",
        10
      ),
      maxRetries: parseInt(process.env.QQBOT_MAX_RETRIES || "10", 10),
      reconnectDelay: parseInt(
        process.env.QQBOT_RECONNECT_DELAY || "1000",
        10
      ),
      allowedWorkspaceRoots,
      maxMessageChars,
      maxReplyChunkSize,
    },
    gatewayClient,
    sessionStore,
    defaultWorkspace,
    defaultDryRun
  );

  // Handle shutdown
  process.on("SIGINT", async () => {
    console.log("\n[qqbot-channel] Shutting down...");
    await channel.stop();
    process.exit(0);
  });

  process.on("SIGTERM", async () => {
    console.log("\n[qqbot-channel] Shutting down...");
    await channel.stop();
    process.exit(0);
  });

  // Start channel
  try {
    console.log(`[qqbot-channel] Starting...`);
    console.log(`[qqbot-channel] Gateway: ${gatewayBaseUrl}`);
    console.log(`[qqbot-channel] Mode: ${mode}`);
    console.log(`[qqbot-channel] Sandbox: ${sandbox}`);
    console.log(`[qqbot-channel] Session store: ${sessionStorePath}`);
    console.log(`[qqbot-channel] Allowed roots: ${allowedWorkspaceRoots.join(", ")}`);
    console.log(`[qqbot-channel] Max message chars: ${maxMessageChars}`);
    console.log(`[qqbot-channel] Max reply chunk: ${maxReplyChunkSize}`);
    if (gatewayAuthToken) {
      console.log("[qqbot-channel] Gateway auth token: enabled");
    }

    // Check gateway health
    const healthy = await gatewayClient.healthCheck();
    if (!healthy) {
      console.warn(
        `[qqbot-channel] Warning: Gateway at ${gatewayBaseUrl} is not responding`
      );
    }

    await channel.start();
    console.log("[qqbot-channel] Started successfully");
  } catch (error: any) {
    console.error(`[qqbot-channel] Failed to start: ${error.message}`);
    process.exit(1);
  }
}

main();
