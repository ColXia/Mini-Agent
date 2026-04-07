/**
 * QQ Bot Channel implementation.
 *
 * Implements the IChannel interface for QQ Bot using the qq-official-bot SDK.
 */

import { Bot, ReceiverMode } from "qq-official-bot";
import * as path from "path";
import {
  IChannel,
  IGatewayClient,
  ISessionStore,
  ChannelReply,
  SessionState,
} from "@mini-agent/channel-types";
import { HTTPGatewayClient } from "./gateway_client";
import { MemorySessionStore } from "./session_store";

/**
 * QQ Bot configuration.
 */
export interface QQBotConfig {
  /** QQ Bot App ID */
  appid: string;
  /** QQ Bot Secret */
  secret: string;
  /** Sandbox mode */
  sandbox?: boolean;
  /** Connection mode: websocket or webhook */
  mode?: "websocket" | "webhook";
  /** Event intents */
  intents?: string[];
  /** Webhook path (for webhook mode) */
  webhookPath?: string;
  /** Webhook port (for webhook mode) */
  port?: number;
  /** Heartbeat interval (for websocket mode) */
  heartbeatInterval?: number;
  /** Max retries (for websocket mode) */
  maxRetries?: number;
  /** Reconnect delay (for websocket mode) */
  reconnectDelay?: number;
  /** Allowed workspace roots for /workspace command */
  allowedWorkspaceRoots?: string[];
  /** Max inbound message length passed to gateway */
  maxMessageChars?: number;
  /** Max reply chunk size for channel output */
  maxReplyChunkSize?: number;
}

interface QQConversationContext {
  storeKey: string;
  conversationId: string;
  senderId?: string;
  peerKind: "group" | "guild" | "dm" | "unknown";
}

/**
 * QQ Bot Channel.
 *
 * Connects to QQ platform and forwards messages to the Mini-Agent Gateway.
 */
export class QQBotChannel implements IChannel {
  private bot: Bot | null = null;
  private _gatewayClient: IGatewayClient;
  private _sessionStore: ISessionStore;
  private config: QQBotConfig;
  private defaultWorkspace: string;
  private defaultDryRun: boolean;
  private seenEventIds: Set<string> = new Set();
  private logFile: string;
  private allowedWorkspaceRoots: string[];
  private maxMessageChars: number;
  private maxReplyChunkSize: number;

  constructor(
    config: QQBotConfig,
    gatewayClient?: IGatewayClient,
    sessionStore?: ISessionStore,
    defaultWorkspace: string = "./workspace",
    defaultDryRun: boolean = false
  ) {
    this.config = config;
    this._gatewayClient =
      gatewayClient || new HTTPGatewayClient({ baseUrl: "http://127.0.0.1:8008" });
    this._sessionStore = sessionStore || new MemorySessionStore();
    this.allowedWorkspaceRoots = this.normalizeAllowedWorkspaceRoots(config.allowedWorkspaceRoots || []);
    this.defaultWorkspace = this.ensureWorkspaceInAllowed(defaultWorkspace);
    this.defaultDryRun = defaultDryRun;
    this.logFile = `${process.cwd()}/runtime.log`;
    this.maxMessageChars = this.normalizeInt(config.maxMessageChars, 12000, 512, 200000);
    this.maxReplyChunkSize = this.normalizeInt(config.maxReplyChunkSize, 1400, 200, 8000);
  }

  getChannelType(): string {
    return "qq";
  }

  get gatewayClient(): IGatewayClient {
    return this._gatewayClient;
  }

  get sessionStore(): ISessionStore {
    return this._sessionStore;
  }

  async start(): Promise<void> {
    const mode =
      this.config.mode === "webhook"
        ? ReceiverMode.WEBHOOK
        : ReceiverMode.WEBSOCKET;

    const botConfig: any = {
      appid: this.config.appid,
      secret: this.config.secret,
      sandbox: this.config.sandbox ?? true,
      intents: this.config.intents || [
        "GUILD_MESSAGES",
        "DIRECT_MESSAGE",
        "GROUP_AT_MESSAGE_CREATE",
        "C2C_MESSAGE_CREATE",
        "PUBLIC_GUILD_MESSAGES",
      ],
      mode,
    };

    if (mode === ReceiverMode.WEBHOOK) {
      botConfig.port = this.config.port || 3520;
      botConfig.path = this.config.webhookPath || "/qqbot/webhook";
    } else {
      botConfig.heartbeatInterval = this.config.heartbeatInterval || 45000;
      botConfig.maxRetries = this.config.maxRetries || 10;
      botConfig.reconnectDelay = this.config.reconnectDelay || 1000;
    }

    this.bot = new Bot(botConfig);

    // Set up event handlers
    this.setupEventHandlers();

    // Start the bot
    await this.bot.start();
    this.log("INFO", `QQ Bot started (mode=${this.config.mode || "websocket"})`);
  }

  async stop(): Promise<void> {
    if (this.bot) {
      await this.bot.stop();
      this.bot = null;
    }
    this.log("INFO", "QQ Bot stopped");
  }

  async sendMessage(conversationId: string, content: string): Promise<ChannelReply> {
    if (!this.bot) {
      return {
        success: false,
        content: "",
        error: "QQ Bot is not running",
      };
    }

    const normalized = String(conversationId || "").trim();
    if (!normalized) {
      return {
        success: false,
        content: "",
        error: "conversationId is required",
      };
    }

    try {
      if (normalized.startsWith("group:") && this.bot.sendGroupMessage) {
        const groupId = normalized.slice("group:".length);
        await this.bot.sendGroupMessage(groupId, content);
        return { success: true, content };
      }
      if (normalized.startsWith("dm:") && this.bot.sendPrivateMessage) {
        const userId = normalized.slice("dm:".length);
        await this.bot.sendPrivateMessage(userId, content);
        return { success: true, content };
      }
    } catch (error: any) {
      return {
        success: false,
        content: "",
        error: error?.message || String(error),
      };
    }

    // Most QQ Bot responses are best effort by replying directly to incoming events.
    return {
      success: false,
      content: "",
      error: `Proactive messaging is not supported for conversation: ${normalized}`,
    };
  }

  async processSmokeMessage(
    content: string,
    options: { groupOpenId?: string; senderId?: string; eventName?: string } = {}
  ): Promise<string[]> {
    const replies: string[] = [];
    const eventId = `smoke-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
    const event = {
      id: eventId,
      content,
      group_openid: options.groupOpenId || "smoke-group-001",
      author: { id: options.senderId || "smoke-user-001" },
      async reply(text: string) {
        replies.push(String(text || ""));
      },
    };
    await this.handleIncomingEvent(event, options.eventName || "message.group.smoke");
    return replies;
  }

  private setupEventHandlers(): void {
    if (!this.bot) return;

    const eventNames = [
      "message",
      "message.guild",
      "message.group",
      "message.private",
      "message.private.direct",
      "message.private.friend",
    ];

    for (const eventName of eventNames) {
      this.bot.on(eventName, async (event: any) => {
        await this.handleIncomingEvent(event, eventName);
      });
    }

    this.bot.on("ready", () => {
      this.log("INFO", "QQ Bot is ready");
    });

    this.bot.on("error", (error: Error) => {
      this.log("ERROR", `Bot error: ${error.message}`);
    });
  }

  private async handleIncomingEvent(event: any, eventName: string): Promise<void> {
    const eventId = String(
      event.id || event.message_id || `${eventName}:${Date.now()}`
    );

    // Deduplicate events
    if (this.seenEventIds.has(eventId)) {
      return;
    }
    this.seenEventIds.add(eventId);

    // Clean up old event IDs
    if (this.seenEventIds.size > 2000) {
      const arr = Array.from(this.seenEventIds).slice(-1000);
      this.seenEventIds.clear();
      arr.forEach((id) => this.seenEventIds.add(id));
    }

    const content = this.limitInboundMessage(this.extractMessageText(event));
    if (!content) return;

    const context = this.getConversationContext(event);
    this.log(
      "INFO",
      `Incoming message from ${context.storeKey} (${context.peerKind}): ${content.slice(0, 80)}...`
    );

    try {
      // Get or create session state
      let state = await this.sessionStore.get(context.storeKey);
      if (!state) {
        state = {
          conversation_id: context.storeKey,
          workspace_dir: this.defaultWorkspace,
          dry_run: this.defaultDryRun,
        };
      }

      // Handle commands
      if (content.startsWith("/")) {
        const handled = await this.handleCommand(event, state, content);
        if (handled) return;
      }

      // Forward to Gateway
      const response = await this.gatewayClient.chat({
        message: content,
        session_id: state.session_id,
        workspace_dir: state.workspace_dir,
        channel_type: this.getChannelType(),
        conversation_id: context.conversationId,
        sender_id: context.senderId,
        metadata: {
          event_name: eventName,
          peer_kind: context.peerKind,
          guild_id: event.guild_id,
          channel_id: event.channel_id,
          group_openid: event.group_openid,
          message_id: event.id || event.message_id,
        },
        dry_run: state.dry_run,
      });

      // Update session state
      state.session_id = response.session_id;
      await this.sessionStore.set(context.storeKey, state);

      // Reply to user
      await this.replySafe(event, response.reply);
    } catch (error: any) {
      this.log("ERROR", `Failed to handle message: ${error.message}`);
      await this.replySafe(event, `Error: ${error.message}`);
    }
  }

  private async handleCommand(
    event: any,
    state: SessionState,
    content: string
  ): Promise<boolean> {
    const [command, ...rest] = content.split(/\s+/);
    const arg = rest.join(" ").trim();

    switch (command.toLowerCase()) {
      case "/help":
        await this.replySafe(
          event,
          [
            "Mini-Agent QQ Bot Commands:",
            "/help - Show this help",
            "/status - Show session status",
            "/workspace <path> - Set workspace directory",
            "/dryrun <on|off> - Toggle dry run mode",
            "/reset - Reset session context",
            "/clear - Clear local session cache",
            "",
            "Send any message to chat with Mini-Agent.",
          ].join("\n")
        );
        return true;

      case "/status":
        await this.replySafe(
          event,
          `Session Status:\n` +
            `Session ID: ${state.session_id || "(none)"}\n` +
            `Workspace: ${state.workspace_dir}\n` +
            `Dry Run: ${state.dry_run}`
        );
        return true;

      case "/ping":
        await this.replySafe(event, "pong");
        return true;

      case "/workspace":
        if (!arg) {
          await this.replySafe(event, "Usage: /workspace <path>");
          return true;
        }
        try {
          state.workspace_dir = this.ensureWorkspaceInAllowed(arg);
        } catch (error: any) {
          await this.replySafe(event, `Workspace rejected: ${error?.message || String(error)}`);
          return true;
        }
        await this.sessionStore.set(state.conversation_id, state);
        await this.replySafe(event, `Workspace set to: ${state.workspace_dir}`);
        return true;

      case "/dryrun":
        if (!arg) {
          await this.replySafe(event, "Usage: /dryrun <on|off>");
          return true;
        }
        state.dry_run = arg.toLowerCase() === "on" || arg.toLowerCase() === "true";
        await this.sessionStore.set(state.conversation_id, state);
        await this.replySafe(event, `Dry Run set to: ${state.dry_run}`);
        return true;

      case "/reset":
        if (state.session_id) {
          await this.gatewayClient.resetSession(state.session_id);
          await this.replySafe(event, `Session reset: ${state.session_id}`);
        } else {
          await this.replySafe(event, "No active session to reset.");
        }
        return true;

      case "/clear":
        await this.sessionStore.delete(state.conversation_id);
        await this.replySafe(event, "Local session cache cleared.");
        return true;

      default:
        return false;
    }
  }

  private getConversationContext(event: any): QQConversationContext {
    const channelId = String(event.channel_id || "").trim();
    const guildId = String(event.guild_id || "").trim();
    const groupOpenId = String(event.group_openid || "").trim();
    const senderId = String(event.author?.id || event.user_id || event.member_openid || "").trim();

    if (groupOpenId) {
      return {
        storeKey: `group:${groupOpenId}`,
        conversationId: `group:${groupOpenId}`,
        senderId: senderId || undefined,
        peerKind: "group",
      };
    }

    if (channelId) {
      const convo = guildId ? `guild:${guildId}:channel:${channelId}` : `channel:${channelId}`;
      return {
        storeKey: convo,
        conversationId: convo,
        senderId: senderId || undefined,
        peerKind: "guild",
      };
    }

    if (senderId) {
      return {
        storeKey: `dm:${senderId}`,
        conversationId: `dm:${senderId}`,
        senderId,
        peerKind: "dm",
      };
    }

    const fallback = String(event.id || Date.now());
    return {
      storeKey: `unknown:${fallback}`,
      conversationId: `unknown:${fallback}`,
      peerKind: "unknown",
    };
  }

  private extractMessageText(event: any): string {
    const text = String(event.content || "").trim();
    const attachments = this.normalizeAttachments(event);

    if (!attachments.length) {
      return text;
    }

    const attachmentLines = attachments.map((item, idx) => {
      const parts: string[] = [`[Attachment ${idx + 1}]`];
      if (item.type) {
        parts.push(`type=${item.type}`);
      }
      if (item.filename) {
        parts.push(`name=${item.filename}`);
      }
      if (item.url) {
        parts.push(`url=${item.url}`);
      }
      return parts.join(" ");
    });

    if (!text) {
      return `User sent attachment(s):\n${attachmentLines.join("\n")}`;
    }
    return `${text}\n\n${attachmentLines.join("\n")}`;
  }

  private normalizeAttachments(event: any): Array<{ type: string; filename: string; url: string }> {
    const rawList = Array.isArray(event.attachments)
      ? event.attachments
      : Array.isArray(event.message_attachments)
      ? event.message_attachments
      : [];

    const result: Array<{ type: string; filename: string; url: string }> = [];
    for (const item of rawList) {
      const type = String(item?.content_type || item?.type || "").trim();
      const filename = String(item?.filename || item?.name || "").trim();
      let url = String(item?.url || item?.file_info || "").trim();
      if (url && url.startsWith("//")) {
        url = `https:${url}`;
      }
      result.push({ type, filename, url });
    }
    return result;
  }

  private async replySafe(event: any, text: string): Promise<void> {
    const chunks = this.splitLongText(text || "", this.maxReplyChunkSize);
    for (const chunk of chunks) {
      try {
        if (typeof event.reply === "function") {
          await event.reply(chunk);
          continue;
        }
        // Fallback: try bot methods
        if (event.group_id && this.bot?.sendGroupMessage) {
          await this.bot.sendGroupMessage(event.group_id, chunk);
          continue;
        }
        if (event.user_id && this.bot?.sendPrivateMessage) {
          await this.bot.sendPrivateMessage(event.user_id, chunk);
          continue;
        }
      } catch (error: any) {
        this.log("ERROR", `Failed to reply: ${error.message}`);
      }
    }
  }

  private splitLongText(text: string, maxChunk: number = 1400): string[] {
    if (text.length <= maxChunk) {
      return [text];
    }
    const chunks: string[] = [];
    for (let start = 0; start < text.length; start += maxChunk) {
      chunks.push(text.slice(start, start + maxChunk));
    }
    return chunks;
  }

  private normalizeInt(value: number | undefined, fallback: number, minValue: number, maxValue: number): number {
    const raw = Number(value ?? fallback);
    if (!Number.isFinite(raw)) {
      return fallback;
    }
    const rounded = Math.floor(raw);
    if (rounded < minValue) {
      return minValue;
    }
    if (rounded > maxValue) {
      return maxValue;
    }
    return rounded;
  }

  private normalizeAllowedWorkspaceRoots(rawRoots: string[]): string[] {
    const defaults = [process.cwd(), path.resolve(process.cwd(), "workspace")];
    const merged = [...defaults, ...rawRoots];
    const dedup = new Set<string>();
    const roots: string[] = [];
    for (const item of merged) {
      const normalized = String(item || "").trim();
      if (!normalized) {
        continue;
      }
      const resolved = path.resolve(normalized);
      const key = resolved.toLowerCase();
      if (dedup.has(key)) {
        continue;
      }
      dedup.add(key);
      roots.push(resolved);
    }
    return roots;
  }

  private isWithinWorkspaceRoots(targetPath: string): boolean {
    for (const root of this.allowedWorkspaceRoots) {
      const relative = path.relative(root, targetPath);
      if (!relative || (!relative.startsWith("..") && !path.isAbsolute(relative))) {
        return true;
      }
    }
    return false;
  }

  private ensureWorkspaceInAllowed(rawPath: string): string {
    const normalized = String(rawPath || "").trim();
    if (!normalized) {
      throw new Error("workspace path is empty");
    }
    const resolved = path.resolve(normalized);
    if (!this.isWithinWorkspaceRoots(resolved)) {
      throw new Error(`path is outside allowed roots: ${resolved}`);
    }
    return resolved;
  }

  private limitInboundMessage(text: string): string {
    const trimmed = String(text || "").trim();
    if (!trimmed) {
      return "";
    }
    if (trimmed.length <= this.maxMessageChars) {
      return trimmed;
    }
    return `${trimmed.slice(0, this.maxMessageChars)}\n\n[truncated by qq channel guardrail]`;
  }

  private log(level: string, message: string): void {
    const line = `[${new Date().toISOString()}] [${level}] ${message}`;
    console.log(line);
    try {
      const fs = require("fs");
      fs.appendFileSync(this.logFile, `${line}\n`, "utf8");
    } catch {
      // Ignore file write errors
    }
  }
}
