/**
 * WeChat Channel entry point.
 */

import * as dotenv from "dotenv";
import * as path from "path";
import { WeChatChannel } from "./channel";
import { HTTPGatewayClient } from "./gateway_client";
import { MemorySessionStore } from "./session_store";

dotenv.config({ path: path.resolve(__dirname, "../.env") });

async function main(): Promise<void> {
  const token = process.env.WECHAT_TOKEN || "";
  const appid = process.env.WECHAT_APPID || "";
  const host = process.env.WECHAT_HOST || "0.0.0.0";
  const port = parseInt(process.env.WECHAT_PORT || "3530", 10);
  const webhookPath = process.env.WECHAT_PATH || "/wechat/webhook";

  const gatewayBaseUrl = process.env.MINI_AGENT_GATEWAY_BASE || "http://127.0.0.1:8008";
  const gatewayAuthToken =
    process.env.WECHAT_GATEWAY_AUTH_TOKEN ||
    process.env.MINI_AGENT_GATEWAY_AUTH_TOKEN ||
    "";
  const defaultWorkspace = process.env.WECHAT_DEFAULT_WORKSPACE || process.cwd();
  const defaultDryRun = process.env.WECHAT_DEFAULT_DRY_RUN?.toLowerCase() === "true";
  const sessionStorePath =
    process.env.WECHAT_SESSION_STORE_PATH || path.resolve(process.cwd(), ".wechat_sessions.json");
  const allowedWorkspaceRoots = (
    process.env.WECHAT_ALLOWED_WORKSPACE_ROOTS ||
    `${process.cwd()},${path.resolve(process.cwd(), "workspace")}`
  )
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const maxMessageChars = parseInt(process.env.WECHAT_MAX_MESSAGE_CHARS || "12000", 10);
  const maxResponseChars = parseInt(process.env.WECHAT_MAX_RESPONSE_CHARS || "4000", 10);
  const maxBodyBytes = parseInt(process.env.WECHAT_MAX_BODY_BYTES || "1048576", 10);
  const maxTimestampSkewSeconds = parseInt(
    process.env.WECHAT_MAX_TIMESTAMP_SKEW_SECONDS || "600",
    10
  );
  const dedupeWindowSize = parseInt(process.env.WECHAT_DEDUPE_WINDOW_SIZE || "4000", 10);

  if (!token) {
    console.error("[wechat-channel] Missing WECHAT_TOKEN");
    process.exit(1);
  }

  const gatewayClient = new HTTPGatewayClient({
    baseUrl: gatewayBaseUrl,
    timeout: 120000,
    gatewayAuthToken,
  });
  const sessionStore = new MemorySessionStore({ filePath: sessionStorePath });

  const channel = new WeChatChannel(
    {
      token,
      appid,
      host,
      port,
      path: webhookPath,
      allowedWorkspaceRoots,
      maxMessageChars,
      maxResponseChars,
      maxBodyBytes,
      maxTimestampSkewSeconds,
      dedupeWindowSize,
    },
    gatewayClient,
    sessionStore,
    defaultWorkspace,
    defaultDryRun
  );

  process.on("SIGINT", async () => {
    console.log("\n[wechat-channel] Shutting down...");
    await channel.stop();
    process.exit(0);
  });

  process.on("SIGTERM", async () => {
    console.log("\n[wechat-channel] Shutting down...");
    await channel.stop();
    process.exit(0);
  });

  try {
    console.log("[wechat-channel] Starting...");
    console.log(`[wechat-channel] Gateway: ${gatewayBaseUrl}`);
    console.log(`[wechat-channel] Webhook: ${host}:${port}${webhookPath}`);
    console.log(`[wechat-channel] Session store: ${sessionStorePath}`);
    console.log(`[wechat-channel] Allowed roots: ${allowedWorkspaceRoots.join(", ")}`);
    console.log(`[wechat-channel] Max message chars: ${maxMessageChars}`);
    console.log(`[wechat-channel] Max response chars: ${maxResponseChars}`);
    console.log(`[wechat-channel] Max body bytes: ${maxBodyBytes}`);
    console.log(`[wechat-channel] Max timestamp skew seconds: ${maxTimestampSkewSeconds}`);
    console.log(`[wechat-channel] Dedupe window size: ${dedupeWindowSize}`);
    if (gatewayAuthToken) {
      console.log("[wechat-channel] Gateway auth token: enabled");
    }

    const healthy = await gatewayClient.healthCheck();
    if (!healthy) {
      console.warn(`[wechat-channel] Warning: Gateway at ${gatewayBaseUrl} is not responding`);
    }

    await channel.start();
    console.log("[wechat-channel] Started successfully");
  } catch (error: any) {
    console.error(`[wechat-channel] Failed to start: ${error?.message || String(error)}`);
    process.exit(1);
  }
}

main();
