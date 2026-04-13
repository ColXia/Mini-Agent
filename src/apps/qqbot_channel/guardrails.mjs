import path from "node:path";

export function normalizeInt(value, fallback, minValue, maxValue) {
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

export function parseCsvEnv(raw) {
  return String(raw || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function normalizeAllowedWorkspaceRoots(rawRoots = [], baseDir = process.cwd()) {
  const defaults = [baseDir, path.resolve(baseDir, "workspace")];
  const merged = [...defaults, ...rawRoots];
  const dedup = new Set();
  const roots = [];
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

export function isWithinWorkspaceRoots(targetPath, roots) {
  for (const root of roots) {
    const relative = path.relative(root, targetPath);
    if (!relative || (!relative.startsWith("..") && !path.isAbsolute(relative))) {
      return true;
    }
  }
  return false;
}

export function ensureWorkspaceInAllowed(rawPath, roots) {
  const normalized = String(rawPath || "").trim();
  if (!normalized) {
    throw new Error("workspace path is empty");
  }
  const resolved = path.resolve(normalized);
  if (!isWithinWorkspaceRoots(resolved, roots)) {
    throw new Error(`path is outside allowed roots: ${resolved}`);
  }
  return resolved;
}

export function limitInboundMessage(text, maxMessageChars) {
  const trimmed = String(text || "").trim();
  if (!trimmed) {
    return "";
  }
  if (trimmed.length <= maxMessageChars) {
    return trimmed;
  }
  return `${trimmed.slice(0, maxMessageChars)}\n\n[truncated by qq channel guardrail]`;
}

export function splitLongText(text, maxChunk = 1400) {
  const source = String(text || "");
  if (source.length <= maxChunk) {
    return [source];
  }
  const chunks = [];
  for (let start = 0; start < source.length; start += maxChunk) {
    chunks.push(source.slice(start, start + maxChunk));
  }
  return chunks;
}
