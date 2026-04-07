import type { ChannelMessageResponse, ChatResponse } from "../types";
import { ApiEnvelope, buildAuthHeaders, buildUrl, normalizeErrorText, request, unwrapEnvelope } from "./client";

export interface ChatStreamPayload {
  message: string;
  session_id?: string;
  workspace_dir?: string;
  dry_run?: boolean;
}

export interface ChatStreamCallbacks {
  onSession?: (data: { session_id: string; workspace_dir: string }) => void;
  onStatus?: (data: { stage: string; at: string }) => void;
  onHeartbeat?: (data: { at: string }) => void;
  onDelta?: (chunk: string) => void;
  onError?: (message: string) => void;
  onDone?: (data: ChatResponse & { assistant_id?: string }) => void;
}

function parseSseEvent(block: string): { event: string; data: string } | null {
  const lines = block.split(/\r?\n/).filter(Boolean);
  if (lines.length === 0) {
    return null;
  }
  let event = "message";
  const dataLines: string[] = [];
  for (const line of lines) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trim());
    }
  }
  return { event, data: dataLines.join("\n") };
}

export async function streamChatMessage(
  payload: ChatStreamPayload,
  callbacks: ChatStreamCallbacks,
  signal?: AbortSignal
): Promise<void> {
  const query = new URLSearchParams();
  query.set("message", payload.message);
  if (payload.session_id) {
    query.set("session_id", payload.session_id);
  }
  if (payload.workspace_dir) {
    query.set("workspace_dir", payload.workspace_dir);
  }
  if (payload.dry_run) {
    query.set("dry_run", "true");
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(`/api/v1/agent/chat/stream?${query.toString()}`), {
      method: "GET",
      headers: { ...buildAuthHeaders(), Accept: "text/event-stream" },
      signal
    });
  } catch (error) {
    throw new Error(
      `请求失败（网络错误）：${buildUrl("/api/v1/agent/chat/stream")}，${String(error)}`
    );
  }
  if (!response.ok || !response.body) {
    const text = await response.text();
    throw new Error(normalizeErrorText(response.status, response.statusText, text));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });

    while (true) {
      const separatorIndex = buffer.indexOf("\n\n");
      if (separatorIndex < 0) {
        break;
      }
      const block = buffer.slice(0, separatorIndex);
      buffer = buffer.slice(separatorIndex + 2);

      const parsed = parseSseEvent(block);
      if (!parsed || !parsed.data) {
        continue;
      }
      let data: any = {};
      try {
        data = JSON.parse(parsed.data);
      } catch {
        data = { raw: parsed.data };
      }

      if (parsed.event === "session") {
        callbacks.onSession?.(data);
      } else if (parsed.event === "status") {
        callbacks.onStatus?.(data);
      } else if (parsed.event === "heartbeat") {
        callbacks.onHeartbeat?.(data);
      } else if (parsed.event === "delta") {
        callbacks.onDelta?.(String(data.chunk ?? ""));
      } else if (parsed.event === "error") {
        callbacks.onError?.(String(data.message ?? "未知流式错误"));
      } else if (parsed.event === "done") {
        callbacks.onDone?.(data);
      }
    }
  }
}

export async function sendChatMessage(
  payload: {
    message: string;
    session_id?: string;
    workspace_dir?: string;
    dry_run?: boolean;
  },
  signal?: AbortSignal
): Promise<ChatResponse> {
  const envelope = await request<ApiEnvelope<ChatResponse>>("/api/v1/agent/chat", {
    method: "POST",
    body: JSON.stringify(payload),
    signal
  });
  return unwrapEnvelope(envelope);
}

export interface ChannelMessagePayload {
  channel_type: "qq" | "wechat" | string;
  conversation_id: string;
  message: string;
  sender_id?: string;
  session_id?: string;
  workspace_dir?: string;
  dry_run?: boolean;
  metadata?: Record<string, unknown>;
}

export async function sendChannelMessage(payload: ChannelMessagePayload): Promise<ChannelMessageResponse> {
  const envelope = await request<ApiEnvelope<ChannelMessageResponse>>("/api/v1/channel/message", {
    method: "POST",
    body: JSON.stringify(payload)
  });
  return unwrapEnvelope(envelope);
}
