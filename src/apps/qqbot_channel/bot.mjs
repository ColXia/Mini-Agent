import process from "node:process";
import fs from "node:fs";
import path from "node:path";

import dotenv from "dotenv";
import { Bot, ReceiverMode } from "qq-official-bot";

dotenv.config();

const gatewayBase = (process.env.MINI_AGENT_GATEWAY_BASE || "http://127.0.0.1:8008").replace(/\/+$/, "");
const defaultWorkspace = process.env.QQBOT_DEFAULT_WORKSPACE || "C:/Users/Conli/Mini-Agent";
const defaultDryRun = String(process.env.QQBOT_DEFAULT_DRY_RUN || "false").toLowerCase() === "true";

const appid = process.env.QQBOT_APPID || "";
const secret = process.env.QQBOT_SECRET || "";
const modeRaw = (process.env.QQBOT_MODE || "websocket").trim().toLowerCase();
const mode = modeRaw === "webhook" ? ReceiverMode.WEBHOOK : ReceiverMode.WEBSOCKET;
const intents = String(
  process.env.QQBOT_INTENTS ||
    "GUILD_MESSAGES,DIRECT_MESSAGE,GROUP_AT_MESSAGE_CREATE,C2C_MESSAGE_CREATE,PUBLIC_GUILD_MESSAGES"
)
  .split(",")
  .map((item) => item.trim())
  .filter(Boolean);
const sandbox = String(process.env.QQBOT_SANDBOX || "true").toLowerCase() !== "false";

const webhookPath = process.env.QQBOT_WEBHOOK_PATH || "/qqbot/webhook";
const port = Number(process.env.QQBOT_PORT || 3520);
const heartbeatInterval = Number(process.env.QQBOT_HEARTBEAT_INTERVAL || 45000);
const maxRetries = Number(process.env.QQBOT_MAX_RETRIES || 10);
const reconnectDelay = Number(process.env.QQBOT_RECONNECT_DELAY || 1000);

if (!appid || !secret) {
  console.error("[qqbot-channel] Missing QQBOT_APPID or QQBOT_SECRET.");
  process.exit(1);
}

const sessions = new Map();
const seenEventIds = new Set();
const logFile = path.resolve(process.cwd(), "runtime.log");

function logLine(level, message, meta = undefined) {
  const line = `[${new Date().toISOString()}] [${level}] ${message}${
    meta ? ` ${JSON.stringify(meta)}` : ""
  }`;
  try {
    fs.appendFileSync(logFile, `${line}\n`, "utf8");
  } catch {
    // no-op
  }
  console.log(line);
}

function getConversationKey(event) {
  return (
    event.channel_id ||
    event.group_openid ||
    event.guild_id ||
    event.author?.id ||
    event.user_id ||
    event.id ||
    "default"
  );
}

function getSessionState(event) {
  const key = getConversationKey(event);
  if (!sessions.has(key)) {
    sessions.set(key, {
      key,
      sessionId: "",
      workspaceDir: defaultWorkspace,
      dryRun: defaultDryRun
    });
  }
  return sessions.get(key);
}

function safeJsonParse(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

async function gatewayRequest(path, options = {}) {
  const response = await fetch(`${gatewayBase}${path}`, options);
  if (!response.ok) {
    const raw = await response.text();
    const parsed = safeJsonParse(raw);
    const detail = typeof parsed?.detail === "string" ? parsed.detail : raw;
    throw new Error(`HTTP ${response.status}: ${detail || response.statusText}`);
  }
  return response;
}

function toBool(raw) {
  const value = String(raw || "").trim().toLowerCase();
  return value === "1" || value === "true" || value === "on" || value === "yes";
}

function splitLongText(text, maxChunk = 1400) {
  if (text.length <= maxChunk) {
    return [text];
  }
  const chunks = [];
  for (let start = 0; start < text.length; start += maxChunk) {
    chunks.push(text.slice(start, start + maxChunk));
  }
  return chunks;
}

async function replySafe(event, text) {
  const chunks = splitLongText(text || "");
  for (const chunk of chunks) {
    if (typeof event.reply === "function") {
      await event.reply(chunk);
      continue;
    }
    if (event.group_id && typeof bot.sendGroupMessage === "function") {
      await bot.sendGroupMessage(event.group_id, chunk);
      continue;
    }
    if (event.user_id && typeof bot.sendPrivateMessage === "function") {
      await bot.sendPrivateMessage(event.user_id, chunk);
      continue;
    }
    throw new Error("No available reply method for this event");
  }
}

async function handleCommand(event, state, rawText) {
  const text = rawText.trim();
  const [command, ...rest] = text.split(/\s+/);
  const arg = rest.join(" ").trim();

  if (command === "/help") {
    await replySafe(
      event,
      [
        "Mini-Agent QQ 通道指令:",
        "/help - 查看帮助",
        "/status - 查看当前会话状态",
        "/workspace <path> - 设置当前会话工作目录",
        "/dryrun <on|off> - 切换 Dry Run",
        "/reset - 重置当前会话上下文",
        "/clear - 清理本会话缓存",
        "",
        "直接发送普通消息即可转发给 Mini-Agent。"
      ].join("\n")
    );
    return true;
  }

  if (command === "/status") {
    await replySafe(
      event,
      `会话状态\nsessionId: ${state.sessionId || "(none)"}\nworkspace: ${state.workspaceDir}\ndryRun: ${state.dryRun}`
    );
    return true;
  }

  if (command === "/ping") {
    await replySafe(event, "pong");
    return true;
  }

  if (command === "/workspace") {
    if (!arg) {
      await replySafe(event, "用法: /workspace <path>");
      return true;
    }
    state.workspaceDir = arg;
    await replySafe(event, `已设置工作目录: ${state.workspaceDir}`);
    return true;
  }

  if (command === "/dryrun") {
    if (!arg) {
      await replySafe(event, "用法: /dryrun <on|off>");
      return true;
    }
    state.dryRun = toBool(arg);
    await replySafe(event, `Dry Run 已设置为: ${state.dryRun}`);
    return true;
  }

  if (command === "/reset") {
    if (!state.sessionId) {
      await replySafe(event, "当前还没有可重置的会话。");
      return true;
    }
    await gatewayRequest(`/api/v1/agent/sessions/${encodeURIComponent(state.sessionId)}/reset`, { method: "POST" });
    await replySafe(event, `会话已重置: ${state.sessionId}`);
    return true;
  }

  if (command === "/clear") {
    sessions.delete(state.key);
    await replySafe(event, "本地会话缓存已清理。");
    return true;
  }

  return false;
}

async function forwardMessage(event, state, rawText) {
  const payload = {
    channel_type: "qq",
    conversation_id: state.key,
    sender_id: String(event.author?.id || event.user_id || "").trim() || undefined,
    message: rawText,
    session_id: state.sessionId || undefined,
    workspace_dir: state.workspaceDir,
    dry_run: state.dryRun
  };

  const response = await gatewayRequest("/api/v1/channel/message", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  const envelope = await response.json();
  if (!envelope?.ok || !envelope?.data) {
    const message = envelope?.error?.message || "Invalid v1 envelope from gateway";
    throw new Error(String(message));
  }
  const data = envelope.data;
  state.sessionId = data.session_id || state.sessionId;
  await replySafe(event, data.reply || "(empty reply)");
}

async function handleIncomingEvent(event, eventName) {
  const eventId = String(event.id || event.message_id || `${eventName}:${Date.now()}`);
  if (seenEventIds.has(eventId)) {
    return;
  }
  seenEventIds.add(eventId);
  if (seenEventIds.size > 2000) {
    const arr = Array.from(seenEventIds).slice(-1000);
    seenEventIds.clear();
    for (const id of arr) {
      seenEventIds.add(id);
    }
  }

  const content = String(event.content || "").trim();
  if (!content) {
    return;
  }

  const state = getSessionState(event);
  logLine("INFO", "Incoming message", {
    eventName,
    eventId,
    key: state.key,
    content
  });

  try {
    const isCommand = content.startsWith("/");
    if (isCommand) {
      const handled = await handleCommand(event, state, content);
      if (handled) {
        return;
      }
    }
    await forwardMessage(event, state, content);
  } catch (error) {
    logLine("ERROR", "Handle message failed", {
      eventName,
      eventId,
      error: String(error)
    });
    try {
      await replySafe(event, `请求失败: ${String(error)}`);
    } catch (replyErr) {
      logLine("ERROR", "Reply failed", {
        eventName,
        eventId,
        error: String(replyErr)
      });
    }
  }
}

const botConfig = {
  appid,
  secret,
  sandbox,
  intents,
  mode
};

if (mode === ReceiverMode.WEBHOOK) {
  Object.assign(botConfig, {
    port,
    path: webhookPath
  });
} else {
  Object.assign(botConfig, {
    heartbeatInterval,
    maxRetries,
    reconnectDelay
  });
}

const bot = new Bot(botConfig);

for (const eventName of [
  "message",
  "message.guild",
  "message.group",
  "message.private",
  "message.private.direct",
  "message.private.friend"
]) {
  bot.on(eventName, async (event) => {
    await handleIncomingEvent(event, eventName);
  });
}

bot.on("ready", () => {
  logLine(
    "INFO",
    `qqbot-channel ready mode=${modeRaw} sandbox=${sandbox} gateway=${gatewayBase} intents=${intents.join(",")}`
  );
});

bot.on("error", (error) => {
  logLine("ERROR", "bot error", { error: String(error) });
});

bot.on("system", (event) => {
  logLine("INFO", "system event", {
    type: event?.system_type || "",
    subType: event?.sub_type || ""
  });
});
logLine("INFO", "qqbot-channel booting", {
  mode: modeRaw,
  sandbox,
  gatewayBase,
  intents
});

bot
  .start()
  .then(() => {
    logLine("INFO", "qqbot-channel started");
  })
  .catch((error) => {
    logLine("ERROR", "qqbot-channel start failed", { error: String(error) });
  });
