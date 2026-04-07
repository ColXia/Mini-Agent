/**
 * WeChat channel implementation.
 *
 * This channel runs as a lightweight webhook server and forwards messages
 * to Mini-Agent Gateway while preserving channel/session binding metadata.
 */

import * as crypto from "crypto";
import * as http from "http";
import * as path from "path";
import {
  ChannelReply,
  IChannel,
  IGatewayClient,
  ISessionStore,
  SessionState,
} from "@mini-agent/channel-types";
import { HTTPGatewayClient } from "./gateway_client";
import { MemorySessionStore } from "./session_store";

export interface WeChatChannelConfig {
  token: string;
  appid?: string;
  host?: string;
  port?: number;
  path?: string;
  allowedWorkspaceRoots?: string[];
  maxMessageChars?: number;
  maxResponseChars?: number;
  maxBodyBytes?: number;
  maxTimestampSkewSeconds?: number;
  dedupeWindowSize?: number;
}

interface WeChatIncomingMessage {
  toUser: string;
  fromUser: string;
  msgType: string;
  msgId: string;
  content: string;
  picUrl: string;
  mediaId: string;
  format: string;
  recognition: string;
  locationX: string;
  locationY: string;
  label: string;
  title: string;
  description: string;
  url: string;
  event: string;
  eventKey: string;
}

export class WeChatChannel implements IChannel {
  private server: http.Server | null = null;
  private _gatewayClient: IGatewayClient;
  private _sessionStore: ISessionStore;
  private config: WeChatChannelConfig;
  private defaultWorkspace: string;
  private defaultDryRun: boolean;
  private allowedWorkspaceRoots: string[];
  private maxMessageChars: number;
  private maxResponseChars: number;
  private maxBodyBytes: number;
  private maxTimestampSkewSeconds: number;
  private dedupeWindowSize: number;
  private seenMessageKeys: Set<string> = new Set();

  constructor(
    config: WeChatChannelConfig,
    gatewayClient?: IGatewayClient,
    sessionStore?: ISessionStore,
    defaultWorkspace: string = "./workspace",
    defaultDryRun: boolean = false
  ) {
    this.config = {
      host: "0.0.0.0",
      port: 3530,
      path: "/wechat/webhook",
      ...config,
    };
    this._gatewayClient =
      gatewayClient || new HTTPGatewayClient({ baseUrl: "http://127.0.0.1:8008", timeout: 120000 });
    this._sessionStore = sessionStore || new MemorySessionStore();
    this.allowedWorkspaceRoots = this.normalizeAllowedWorkspaceRoots(this.config.allowedWorkspaceRoots || []);
    this.defaultWorkspace = this.ensureWorkspaceInAllowed(defaultWorkspace);
    this.defaultDryRun = defaultDryRun;
    this.maxMessageChars = this.normalizeInt(this.config.maxMessageChars, 12000, 512, 200000);
    this.maxResponseChars = this.normalizeInt(this.config.maxResponseChars, 4000, 256, 20000);
    this.maxBodyBytes = this.normalizeInt(this.config.maxBodyBytes, 1024 * 1024, 1024, 4 * 1024 * 1024);
    this.maxTimestampSkewSeconds = this.normalizeInt(this.config.maxTimestampSkewSeconds, 600, 0, 86400);
    this.dedupeWindowSize = this.normalizeInt(this.config.dedupeWindowSize, 4000, 100, 50000);
  }

  getChannelType(): string {
    return "wechat";
  }

  get gatewayClient(): IGatewayClient {
    return this._gatewayClient;
  }

  get sessionStore(): ISessionStore {
    return this._sessionStore;
  }

  async start(): Promise<void> {
    if (this.server) {
      return;
    }

    this.server = http.createServer(async (req, res) => {
      await this.handleRequest(req, res);
    });

    await new Promise<void>((resolve, reject) => {
      this.server?.once("error", reject);
      this.server?.listen(this.config.port, this.config.host, () => {
        resolve();
      });
    });

    this.log("INFO", `WeChat webhook listening on ${this.config.host}:${this.config.port}${this.config.path}`);
  }

  async stop(): Promise<void> {
    if (!this.server) {
      return;
    }
    const target = this.server;
    this.server = null;
    await new Promise<void>((resolve) => {
      target.close(() => resolve());
    });
    this.log("INFO", "WeChat webhook server stopped");
  }

  async sendMessage(_conversationId: string, _content: string): Promise<ChannelReply> {
    // WeChat official account channel is webhook-driven in this lightweight baseline.
    return {
      success: false,
      content: "",
      error: "Proactive message sending is not implemented in webhook mode",
    };
  }

  private async handleRequest(req: http.IncomingMessage, res: http.ServerResponse): Promise<void> {
    const host = req.headers.host || "127.0.0.1";
    const url = new URL(req.url || "/", `http://${host}`);
    const expectedPath = this.config.path || "/wechat/webhook";

    if (url.pathname !== expectedPath) {
      res.statusCode = 404;
      res.end("Not Found");
      return;
    }

    const signature = url.searchParams.get("signature") || "";
    const timestamp = url.searchParams.get("timestamp") || "";
    const nonce = url.searchParams.get("nonce") || "";
    const echostr = url.searchParams.get("echostr") || "";

    if (req.method === "GET") {
      if (!this.isValidSignature(signature, timestamp, nonce)) {
        res.statusCode = 401;
        res.end("invalid signature");
        return;
      }
      if (!this.isTimestampAccepted(timestamp)) {
        res.statusCode = 401;
        res.end("invalid timestamp");
        return;
      }
      res.statusCode = 200;
      res.setHeader("Content-Type", "text/plain; charset=utf-8");
      res.end(echostr);
      return;
    }

    if (req.method !== "POST") {
      res.statusCode = 405;
      res.end("Method Not Allowed");
      return;
    }

    if (!this.isValidSignature(signature, timestamp, nonce)) {
      res.statusCode = 401;
      res.end("invalid signature");
      return;
    }
    if (!this.isTimestampAccepted(timestamp)) {
      res.statusCode = 401;
      res.end("invalid timestamp");
      return;
    }

    let body = "";
    try {
      body = await this.readBody(req);
    } catch (error: any) {
      res.statusCode = 413;
      res.end(`request too large: ${error?.message || String(error)}`);
      return;
    }
    const incoming = this.parseIncomingMessage(body);
    if (this.isDuplicateMessage(incoming, body)) {
      this.log("INFO", `Duplicate WeChat message ignored: ${incoming.msgId || "(no-msg-id)"}`);
      res.statusCode = 200;
      res.setHeader("Content-Type", "text/plain; charset=utf-8");
      res.end("success");
      return;
    }

    let replyText = "";
    try {
      replyText = await this.handleIncomingMessage(incoming);
    } catch (error: any) {
      this.log("ERROR", `Failed to process message: ${error?.message || String(error)}`);
      replyText = `Error: ${error?.message || String(error)}`;
    }

    const xml = this.buildTextReply(incoming.fromUser, incoming.toUser, replyText);
    res.statusCode = 200;
    res.setHeader("Content-Type", "application/xml; charset=utf-8");
    res.end(xml);
  }

  private async handleIncomingMessage(incoming: WeChatIncomingMessage): Promise<string> {
    const conversationId = `dm:${incoming.toUser}:${incoming.fromUser}`;
    let state = await this.sessionStore.get(conversationId);
    if (!state) {
      state = {
        conversation_id: conversationId,
        workspace_dir: this.defaultWorkspace,
        dry_run: this.defaultDryRun,
      };
    }

    const commandText = await this.handleCommand(incoming, state);
    if (commandText !== null) {
      return commandText;
    }

    const messageText = this.limitInboundMessage(this.buildGatewayMessage(incoming));
    if (!messageText) {
      return "Unsupported message type.";
    }

    const response = await this.gatewayClient.chat({
      message: messageText,
      session_id: state.session_id,
      workspace_dir: state.workspace_dir,
      channel_type: this.getChannelType(),
      conversation_id: conversationId,
      sender_id: incoming.fromUser,
      metadata: {
        msg_type: incoming.msgType,
        msg_id: incoming.msgId,
        event: incoming.event,
        event_key: incoming.eventKey,
      },
      dry_run: state.dry_run,
    });

    state.session_id = response.session_id;
    await this.sessionStore.set(conversationId, state);

    return this.limitReplyText(response.reply || "OK");
  }

  private async handleCommand(incoming: WeChatIncomingMessage, state: SessionState): Promise<string | null> {
    if (incoming.msgType !== "text") {
      if (incoming.msgType === "event" && incoming.event === "subscribe") {
        return "Mini-Agent connected. Send /help to view commands.";
      }
      return null;
    }

    const text = (incoming.content || "").trim();
    if (!text.startsWith("/")) {
      return null;
    }

    const [command, ...rest] = text.split(/\s+/);
    const arg = rest.join(" ").trim();

    switch (command.toLowerCase()) {
      case "/help":
        return [
          "Mini-Agent WeChat Commands:",
          "/help - Show this help",
          "/status - Show session status",
          "/workspace <path> - Set workspace directory",
          "/dryrun <on|off> - Toggle dry run mode",
          "/reset - Reset session context",
          "/clear - Clear local session cache",
        ].join("\n");

      case "/status":
        return (
          `Session ID: ${state.session_id || "(none)"}\n` +
          `Workspace: ${state.workspace_dir}\n` +
          `Dry Run: ${state.dry_run}`
        );

      case "/workspace":
        if (!arg) {
          return "Usage: /workspace <path>";
        }
        try {
          state.workspace_dir = this.ensureWorkspaceInAllowed(arg);
        } catch (error: any) {
          return `Workspace rejected: ${error?.message || String(error)}`;
        }
        await this.sessionStore.set(state.conversation_id, state);
        return `Workspace set to: ${state.workspace_dir}`;

      case "/dryrun":
        if (!arg) {
          return "Usage: /dryrun <on|off>";
        }
        state.dry_run = arg.toLowerCase() === "on" || arg.toLowerCase() === "true";
        await this.sessionStore.set(state.conversation_id, state);
        return `Dry Run set to: ${state.dry_run}`;

      case "/reset":
        if (!state.session_id) {
          return "No active session to reset.";
        }
        await this.gatewayClient.resetSession(state.session_id);
        return `Session reset: ${state.session_id}`;

      case "/clear":
        await this.sessionStore.delete(state.conversation_id);
        return "Local session cache cleared.";

      case "/ping":
        return "pong";

      default:
        return null;
    }
  }

  private buildGatewayMessage(incoming: WeChatIncomingMessage): string {
    if (incoming.msgType === "text") {
      return incoming.content;
    }

    if (incoming.msgType === "image") {
      return `[image] url=${incoming.picUrl || "(unknown)"} media_id=${incoming.mediaId || "(none)"}`;
    }

    if (incoming.msgType === "voice") {
      const recognition = incoming.recognition ? ` recognition=${incoming.recognition}` : "";
      return `[voice] media_id=${incoming.mediaId || "(none)"} format=${incoming.format || "(unknown)"}${recognition}`;
    }

    if (incoming.msgType === "video" || incoming.msgType === "shortvideo") {
      return `[${incoming.msgType}] media_id=${incoming.mediaId || "(none)"}`;
    }

    if (incoming.msgType === "location") {
      return `[location] x=${incoming.locationX} y=${incoming.locationY} label=${incoming.label}`;
    }

    if (incoming.msgType === "link") {
      return `[link] title=${incoming.title} desc=${incoming.description} url=${incoming.url}`;
    }

    if (incoming.msgType === "event") {
      if (!incoming.event) {
        return "";
      }
      return `[event] ${incoming.event}${incoming.eventKey ? ` key=${incoming.eventKey}` : ""}`;
    }

    return "";
  }

  private isValidSignature(signature: string, timestamp: string, nonce: string): boolean {
    if (!signature || !timestamp || !nonce || !this.config.token) {
      return false;
    }
    const raw = [this.config.token, timestamp, nonce].sort().join("");
    const digest = crypto.createHash("sha1").update(raw).digest("hex");
    return digest === signature;
  }

  private async readBody(req: http.IncomingMessage): Promise<string> {
    return new Promise<string>((resolve, reject) => {
      const chunks: Buffer[] = [];
      let total = 0;
      let settled = false;

      const cleanup = (): void => {
        req.off("data", onData);
        req.off("end", onEnd);
        req.off("error", onError);
      };

      const fail = (error: Error): void => {
        if (settled) {
          return;
        }
        settled = true;
        cleanup();
        reject(error);
      };

      const onData = (chunk: Buffer): void => {
        total += chunk.length;
        if (total > this.maxBodyBytes) {
          fail(new Error(`body exceeds max bytes ${this.maxBodyBytes}`));
          req.destroy();
          return;
        }
        chunks.push(chunk);
      };

      const onEnd = (): void => {
        if (settled) {
          return;
        }
        settled = true;
        cleanup();
        resolve(Buffer.concat(chunks).toString("utf8"));
      };

      const onError = (error: Error): void => {
        fail(error);
      };

      req.on("data", onData);
      req.on("end", onEnd);
      req.on("error", onError);
    });
  }

  private parseIncomingMessage(xml: string): WeChatIncomingMessage {
    return {
      toUser: this.extractXmlTag(xml, "ToUserName"),
      fromUser: this.extractXmlTag(xml, "FromUserName"),
      msgType: this.extractXmlTag(xml, "MsgType").toLowerCase(),
      msgId: this.extractXmlTag(xml, "MsgId"),
      content: this.extractXmlTag(xml, "Content"),
      picUrl: this.extractXmlTag(xml, "PicUrl"),
      mediaId: this.extractXmlTag(xml, "MediaId"),
      format: this.extractXmlTag(xml, "Format"),
      recognition: this.extractXmlTag(xml, "Recognition"),
      locationX: this.extractXmlTag(xml, "Location_X"),
      locationY: this.extractXmlTag(xml, "Location_Y"),
      label: this.extractXmlTag(xml, "Label"),
      title: this.extractXmlTag(xml, "Title"),
      description: this.extractXmlTag(xml, "Description"),
      url: this.extractXmlTag(xml, "Url"),
      event: this.extractXmlTag(xml, "Event").toLowerCase(),
      eventKey: this.extractXmlTag(xml, "EventKey"),
    };
  }

  private extractXmlTag(xml: string, tag: string): string {
    const cdataPattern = new RegExp(`<${tag}><!\\[CDATA\\[([\\s\\S]*?)\\]\\]><\\/${tag}>`, "i");
    const plainPattern = new RegExp(`<${tag}>([\\s\\S]*?)<\\/${tag}>`, "i");
    const cdataMatch = xml.match(cdataPattern);
    if (cdataMatch?.[1]) {
      return cdataMatch[1].trim();
    }
    const plainMatch = xml.match(plainPattern);
    if (plainMatch?.[1]) {
      return plainMatch[1].trim();
    }
    return "";
  }

  private buildTextReply(toUser: string, fromUser: string, content: string): string {
    const safeContent = this.wrapCdata(this.limitReplyText(content || "OK"));
    return (
      "<xml>" +
      `<ToUserName>${this.wrapCdata(toUser)}</ToUserName>` +
      `<FromUserName>${this.wrapCdata(fromUser)}</FromUserName>` +
      `<CreateTime>${Math.floor(Date.now() / 1000)}</CreateTime>` +
      "<MsgType><![CDATA[text]]></MsgType>" +
      `<Content>${safeContent}</Content>` +
      "</xml>"
    );
  }

  private wrapCdata(value: string): string {
    const normalized = String(value).replace(/]]>/g, "]]]]><![CDATA[>");
    return `<![CDATA[${normalized}]]>`;
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
    const normalized = String(text || "").trim();
    if (!normalized) {
      return "";
    }
    if (normalized.length <= this.maxMessageChars) {
      return normalized;
    }
    return `${normalized.slice(0, this.maxMessageChars)}\n\n[truncated by wechat channel guardrail]`;
  }

  private limitReplyText(text: string): string {
    const normalized = String(text || "").trim() || "OK";
    if (normalized.length <= this.maxResponseChars) {
      return normalized;
    }
    return `${normalized.slice(0, this.maxResponseChars)}\n\n[truncated]`;
  }

  private isTimestampAccepted(timestamp: string): boolean {
    const value = Number(timestamp);
    if (!Number.isFinite(value) || value <= 0) {
      return false;
    }
    if (this.maxTimestampSkewSeconds <= 0) {
      return true;
    }
    const now = Math.floor(Date.now() / 1000);
    return Math.abs(now - Math.floor(value)) <= this.maxTimestampSkewSeconds;
  }

  private buildMessageKey(incoming: WeChatIncomingMessage, rawBody: string): string {
    if (incoming.msgId) {
      return `msg:${incoming.msgId}`;
    }
    const hash = crypto.createHash("sha1").update(rawBody).digest("hex");
    return `hash:${hash}`;
  }

  private isDuplicateMessage(incoming: WeChatIncomingMessage, rawBody: string): boolean {
    const key = this.buildMessageKey(incoming, rawBody);
    if (this.seenMessageKeys.has(key)) {
      return true;
    }
    this.seenMessageKeys.add(key);
    if (this.seenMessageKeys.size > this.dedupeWindowSize) {
      const retained = Array.from(this.seenMessageKeys).slice(-Math.floor(this.dedupeWindowSize / 2));
      this.seenMessageKeys.clear();
      for (const item of retained) {
        this.seenMessageKeys.add(item);
      }
    }
    return false;
  }

  private log(level: string, message: string): void {
    console.log(`[${new Date().toISOString()}] [${level}] ${message}`);
  }
}
