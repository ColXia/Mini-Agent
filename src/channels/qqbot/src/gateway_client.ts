/**
 * HTTP Gateway client implementation.
 *
 * Provides HTTP-based communication with the Mini-Agent Gateway.
 */

import {
  IGatewayClient,
  ChatRequest,
  ChatResponse,
} from "@mini-agent/channel-types";

export interface HTTPGatewayClientConfig {
  baseUrl: string;
  timeout?: number;
  gatewayAuthToken?: string;
}

/**
 * HTTP-based Gateway client.
 */
export class HTTPGatewayClient implements IGatewayClient {
  private baseUrl: string;
  private timeout: number;
  private gatewayAuthToken: string;

  constructor(config: HTTPGatewayClientConfig) {
    this.baseUrl = config.baseUrl.replace(/\/+$/, "");
    this.timeout = config.timeout || 120000;
    this.gatewayAuthToken = (config.gatewayAuthToken || "").trim();
  }

  async chat(request: ChatRequest): Promise<ChatResponse> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeout);

    try {
      const channelType = (request.channel_type || "").trim();
      const conversationId = (request.conversation_id || "").trim();
      if (!channelType) {
        throw new Error("channel_type is required for /api/v1/channel/message");
      }
      if (!conversationId) {
        throw new Error("conversation_id is required for /api/v1/channel/message");
      }

      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (this.gatewayAuthToken) {
        headers["Authorization"] = `Bearer ${this.gatewayAuthToken}`;
      }

      const response = await fetch(`${this.baseUrl}/api/v1/channel/message`, {
        method: "POST",
        headers,
        signal: controller.signal,
        body: JSON.stringify({
          channel_type: channelType,
          conversation_id: conversationId,
          sender_id: request.sender_id || undefined,
          message: request.message,
          session_id: request.session_id || undefined,
          workspace_dir: request.workspace_dir || undefined,
          metadata: request.metadata || undefined,
          dry_run: request.dry_run || false,
        }),
      });

      let payload: any = null;
      try {
        payload = await response.json();
      } catch {
        payload = null;
      }

      if (!response.ok) {
        const detail =
          typeof payload?.detail === "string"
            ? payload.detail
            : typeof payload?.error?.message === "string"
            ? payload.error.message
            : JSON.stringify(payload ?? {});
        throw new Error(`HTTP ${response.status}: ${detail}`);
      }

      if (!payload || payload.ok !== true || typeof payload.data !== "object" || payload.data === null) {
        throw new Error("Invalid gateway v1 envelope response.");
      }
      return payload.data as ChatResponse;
    } catch (error: any) {
      if (error?.name === "AbortError") {
        throw new Error(`Gateway request timeout after ${this.timeout}ms`);
      }
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  async resetSession(sessionId: string): Promise<boolean> {
    const headers: Record<string, string> = {};
    if (this.gatewayAuthToken) {
      headers["Authorization"] = `Bearer ${this.gatewayAuthToken}`;
    }
    const response = await fetch(
      `${this.baseUrl}/api/v1/agent/sessions/${encodeURIComponent(sessionId)}/reset`,
      { method: "POST", headers }
    );
    if (!response.ok) {
      return false;
    }
    try {
      const payload: any = await response.json();
      return payload?.ok === true;
    } catch {
      return false;
    }
  }

  async healthCheck(): Promise<boolean> {
    try {
      const headers: Record<string, string> = {};
      if (this.gatewayAuthToken) {
        headers["Authorization"] = `Bearer ${this.gatewayAuthToken}`;
      }
      const response = await fetch(`${this.baseUrl}/api/v1/system/health`, { headers });
      return response.ok;
    } catch {
      return false;
    }
  }
}
