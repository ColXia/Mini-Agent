export interface ApiErrorPayload {
  code?: string;
  message?: string;
  detail?: unknown;
}

export interface ApiEnvelope<T> {
  ok: boolean;
  data: T | null;
  error: ApiErrorPayload | null;
}

function resolveApiBase(): string {
  const configured = String(import.meta.env.VITE_API_BASE ?? "").trim();
  if (configured) {
    return configured.replace(/\/+$/, "");
  }
  // Default to same-origin path and let Vite dev proxy forward /api to gateway.
  return "";
}

const API_BASE = resolveApiBase();
const STUDIO_API_KEY = String(import.meta.env.VITE_STUDIO_API_KEY ?? "").trim();

export function getApiBase(): string {
  return API_BASE;
}

export function buildUrl(path: string): string {
  if (!API_BASE) {
    return path;
  }
  return `${API_BASE}${path}`;
}

export function buildAuthHeaders(): Record<string, string> {
  if (!STUDIO_API_KEY) {
    return {};
  }
  return { "x-api-key": STUDIO_API_KEY };
}

export function normalizeErrorText(status: number, statusText: string, bodyText: string): string {
  const trimmed = bodyText.trim();
  if (!trimmed) {
    return `HTTP ${status}: ${statusText || "未知错误"}`;
  }
  try {
    const parsed = JSON.parse(trimmed) as { detail?: unknown; message?: unknown };
    const detail = parsed.detail ?? parsed.message;
    if (typeof detail === "string" && detail.trim()) {
      return `HTTP ${status}: ${detail}`;
    }
  } catch {
    // Ignore JSON parse errors and fall back to raw text.
  }
  return `HTTP ${status}: ${trimmed}`;
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(buildUrl(path), {
      headers: {
        ...buildAuthHeaders(),
        "Content-Type": "application/json",
        ...(options.headers ?? {})
      },
      ...options
    });
  } catch (error) {
    throw new Error(`请求失败（网络错误）：${buildUrl(path)}，${String(error)}`);
  }

  if (!response.ok) {
    const text = await response.text();
    throw new Error(normalizeErrorText(response.status, response.statusText, text));
  }
  return (await response.json()) as T;
}

export function unwrapEnvelope<T>(payload: ApiEnvelope<T>): T {
  if (payload.ok && payload.data !== null) {
    return payload.data;
  }
  const message = payload.error?.message || "接口返回为空，请检查后端日志。";
  throw new Error(message);
}

export function appendOptionalQuery(path: string, options: Record<string, string | number | undefined | null>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(options)) {
    if (value === undefined || value === null || `${value}`.trim() === "") {
      continue;
    }
    params.set(key, String(value));
  }
  const query = params.toString();
  if (!query) {
    return path;
  }
  return `${path}?${query}`;
}
