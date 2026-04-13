function cleanText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

export function safeJsonParse(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export async function gatewayRequest(gatewayBase, gatewayAuthToken, path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (gatewayAuthToken && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${gatewayAuthToken}`);
  }
  const response = await fetch(`${gatewayBase}${path}`, {
    ...options,
    headers,
  });
  if (!response.ok) {
    const raw = await response.text();
    const parsed = safeJsonParse(raw);
    const detail = typeof parsed?.detail === "string" ? parsed.detail : raw;
    throw new Error(`HTTP ${response.status}: ${detail || response.statusText}`);
  }
  return response;
}

function parseSseEventBlock(block) {
  const normalized = String(block || "").replace(/\r/g, "");
  if (!normalized.trim()) {
    return null;
  }
  let event = "message";
  const dataLines = [];
  for (const line of normalized.split("\n")) {
    if (line.startsWith("event:")) {
      event = cleanText(line.slice(6)) || "message";
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  const rawData = dataLines.join("\n");
  return {
    event,
    data: safeJsonParse(rawData) || { raw: rawData },
  };
}

export async function* iterateSseEvents(response) {
  if (!response?.body) {
    throw new Error("Streaming response body is unavailable.");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    let separatorIndex = buffer.indexOf("\n\n");
    while (separatorIndex >= 0) {
      const block = buffer.slice(0, separatorIndex);
      buffer = buffer.slice(separatorIndex + 2);
      const parsed = parseSseEventBlock(block);
      if (parsed) {
        yield parsed;
      }
      separatorIndex = buffer.indexOf("\n\n");
    }
    if (done) {
      break;
    }
  }
  const finalBlock = parseSseEventBlock(buffer);
  if (finalBlock) {
    yield finalBlock;
  }
}
