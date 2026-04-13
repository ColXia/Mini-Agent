import process from "node:process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import dotenv from "dotenv";
import { Bot, ReceiverMode } from "qq-official-bot";
import {
  ensureWorkspaceInAllowed,
  limitInboundMessage,
  normalizeAllowedWorkspaceRoots,
  normalizeInt,
  parseCsvEnv,
  splitLongText,
} from "./guardrails.mjs";
import {
  gatewayRequest as performGatewayRequest,
  iterateSseEvents,
  safeJsonParse,
} from "./gateway_io.mjs";

dotenv.config();

const gatewayBase = (process.env.MINI_AGENT_GATEWAY_BASE || "http://127.0.0.1:8008").replace(/\/+$/, "");
const gatewayAuthToken = cleanText(
  process.env.QQBOT_GATEWAY_AUTH_TOKEN || process.env.MINI_AGENT_GATEWAY_AUTH_TOKEN || ""
);
const allowedWorkspaceRoots = normalizeAllowedWorkspaceRoots(
  parseCsvEnv(process.env.QQBOT_ALLOWED_WORKSPACE_ROOTS),
  process.cwd()
);
const defaultWorkspace = (() => {
  try {
    return ensureWorkspaceInAllowed(
      process.env.QQBOT_DEFAULT_WORKSPACE || process.cwd(),
      allowedWorkspaceRoots
    );
  } catch (error) {
    console.error(`[qqbot-channel] Invalid QQBOT_DEFAULT_WORKSPACE: ${String(error?.message || error)}`);
    process.exit(1);
  }
})();
const defaultDryRun = String(process.env.QQBOT_DEFAULT_DRY_RUN || "false").toLowerCase() === "true";
const qqbotName = cleanText(process.env.QQBOT_NAME || "nyonyo") || "nyonyo";
const maxMessageChars = normalizeInt(process.env.QQBOT_MAX_MESSAGE_CHARS, 12000, 512, 200000);
const maxReplyChunkSize = normalizeInt(process.env.QQBOT_MAX_REPLY_CHUNK_SIZE, 1400, 200, 8000);

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

// Channel-local convenience cache only.
// This must not become a second remote session truth model.
const conversationBindings = new Map();
const seenEventIds = new Set();
const logFile = path.resolve(process.cwd(), "runtime.log");
const commandCatalogPath = fileURLToPath(new URL("../../mini_agent/commands/catalog.json", import.meta.url));
let commandCatalogCache = null;

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

function getConversationBindingState(event) {
  const key = getConversationKey(event);
  if (!conversationBindings.has(key)) {
    conversationBindings.set(key, {
      // Conversation identity for remote binding.
      conversationId: key,
      // Transitional binding hint only. Canonical remote binding now lives in shared app/session layers.
      sessionId: "",
      // Remote delivery / selection preference.
      followLatest: true,
      // Remote operator routing preferences, not session truth.
      workspaceDir: defaultWorkspace,
      dryRun: defaultDryRun
    });
  }
  return conversationBindings.get(key);
}

function cleanText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function loadCommandCatalog() {
  if (commandCatalogCache) {
    return commandCatalogCache;
  }
  const raw = fs.readFileSync(commandCatalogPath, "utf8").replace(/^\uFEFF/, "");
  const payload = safeJsonParse(raw);
  commandCatalogCache = payload && Array.isArray(payload.commands) ? payload : { commands: [] };
  return commandCatalogCache;
}

function surfaceValues(entry, key, surface) {
  const raw = entry?.[key];
  if (Array.isArray(raw)) {
    return raw.map((item) => cleanText(item)).filter(Boolean);
  }
  if (raw && typeof raw === "object") {
    const surfaceValues = Array.isArray(raw[surface]) ? raw[surface] : Array.isArray(raw.all) ? raw.all : [];
    return surfaceValues.map((item) => cleanText(item)).filter(Boolean);
  }
  return [];
}

function commandEntriesForSurface(surface) {
  return loadCommandCatalog()
    .commands
    .filter((entry) => Array.isArray(entry?.surfaces) && entry.surfaces.includes(surface))
    .map((entry) => ({
      ...entry,
      formsForSurface: surfaceValues(entry, "forms", surface),
      completionTokensForSurface: surfaceValues(entry, "completion_tokens", surface),
      examplesForSurface: surfaceValues(entry, "examples", surface),
    }));
}

function normalizeCommandName(value) {
  return cleanText(value).toLowerCase().replace(/-/g, "_");
}

function tokenizeCommandText(text) {
  const input = String(text || "").trim();
  const tokens = [];
  const pattern = /"([^"]*)"|'([^']*)'|[^\s]+/g;
  for (const match of input.matchAll(pattern)) {
    const token = match[1] ?? match[2] ?? match[0] ?? "";
    if (token) {
      tokens.push(token);
    }
  }
  return tokens;
}

function knownSurfaceCommands(surface) {
  const commands = new Set();
  for (const entry of commandEntriesForSurface(surface)) {
    const candidates = [
      ...(Array.isArray(entry.formsForSurface) ? entry.formsForSurface : []),
      ...(Array.isArray(entry.completionTokensForSurface) ? entry.completionTokensForSurface : [])
    ];
    for (const value of candidates) {
      const head = cleanText(value).split(/\s+/)[0];
      if (head) {
        commands.add(`/${normalizeCommandName(head)}`);
      }
    }
  }
  return Array.from(commands).sort();
}

function scoreSuggestedValues(target, candidates) {
  return candidates
    .map((candidate) => {
      const normalized = normalizeCommandName(String(candidate || "").replace(/^\//, ""));
      let score = 0;
      if (normalized === target) {
        score += 100;
      }
      if (normalized.startsWith(target) || target.startsWith(normalized)) {
        score += 50;
      }
      if (normalized.includes(target) || target.includes(normalized)) {
        score += 20;
      }
      const prefixLength = (() => {
        const max = Math.min(normalized.length, target.length);
        let count = 0;
        while (count < max && normalized[count] === target[count]) {
          count += 1;
        }
        return count;
      })();
      score += prefixLength;
      return { candidate: String(candidate || ""), score };
    })
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score || a.candidate.localeCompare(b.candidate))
    .slice(0, 3)
    .map((item) => item.candidate);
}

function suggestSharedCommandName(value, surface, extras = []) {
  const target = normalizeCommandName(String(value || "").replace(/^\//, ""));
  if (!target) {
    return "";
  }
  const candidates = [
    ...new Set(
      [...knownSurfaceCommands(surface), ...extras].map(
        (item) => `/${normalizeCommandName(String(item).replace(/^\//, ""))}`
      )
    ),
  ];
  const scored = scoreSuggestedValues(target, candidates);
  if (!scored.length) {
    return "";
  }
  return ` Did you mean: ${scored.join(", ")}?`;
}

function parseCommandText(rawText, { aliases = {} } = {}) {
  const raw = String(rawText || "").trim();
  const tokens = tokenizeCommandText(raw);
  if (!tokens.length) {
    return null;
  }
  const normalizedAliases = Object.fromEntries(
    Object.entries(aliases).map(([key, value]) => [`/${normalizeCommandName(String(key).replace(/^\//, ""))}`, `/${normalizeCommandName(String(value).replace(/^\//, ""))}`])
  );
  const rawName = `/${normalizeCommandName(String(tokens[0]).replace(/^\//, ""))}`;
  const canonicalName = normalizedAliases[rawName] || rawName;
  return {
    rawText: raw,
    rawName,
    name: canonicalName,
    args: tokens.slice(1),
  };
}

function buildSharedHelpText(surface) {
  const title = surface === "qq" ? "Mini-Agent QQ commands:" : "Mini-Agent commands:";
  const lines = [title];
  let currentCategory = "";
  for (const entry of commandEntriesForSurface(surface)) {
    const forms = Array.isArray(entry.formsForSurface) ? entry.formsForSurface : [];
    if (!forms.length) {
      continue;
    }
    const category = cleanText(entry.category) || "Other";
    if (category !== currentCategory) {
      if (lines[lines.length - 1] !== "") {
        lines.push("");
      }
      lines.push(`${category}:`);
      currentCategory = category;
    }
    const summary = cleanText(entry.summary);
    lines.push(`/${forms[0]}${summary ? ` - ${summary}` : ""}`);
    for (const form of forms.slice(1)) {
      lines.push(`/${form}`);
    }
  }
  lines.push("");
  lines.push("Send a normal message to forward it to Mini-Agent.");
  return lines.join("\n");
}

function commandEntryForSurface(surface, commandName) {
  const target = normalizeCommandName(String(commandName || "").replace(/^\//, ""));
  if (!target) {
    return null;
  }
  return (
    commandEntriesForSurface(surface).find((entry) => {
      if (normalizeCommandName(entry?.name) === target) {
        return true;
      }
      return (Array.isArray(entry.formsForSurface) ? entry.formsForSurface : []).some((form) => {
        const head = cleanText(form).split(/\s+/)[0];
        return normalizeCommandName(head) === target;
      });
    }) || null
  );
}

function commandFormsForSurface(surface, commandName) {
  const entry = commandEntryForSurface(surface, commandName);
  return Array.isArray(entry?.formsForSurface) ? entry.formsForSurface : [];
}

function actionVariantsFromToken(token) {
  const raw = cleanText(token).trim();
  if (!raw) {
    return [];
  }
  const stripped = raw.replace(/^\[/, "").replace(/\]$/, "");
  const values = [];
  const seen = new Set();
  for (const part of stripped.split("|")) {
    const normalized = normalizeCommandName(String(part || "").replace(/[<>\[\]]/g, ""));
    if (!normalized || seen.has(normalized)) {
      continue;
    }
    seen.add(normalized);
    values.push(normalized);
  }
  return values;
}

function buildCommandUsageText(surface, commandName, fallbackOrOptions = "") {
  const options =
    fallbackOrOptions && typeof fallbackOrOptions === "object"
      ? fallbackOrOptions
      : { fallback: fallbackOrOptions };
  const fallback = cleanText(options?.fallback || "");
  const action = normalizeCommandName(options?.action || "");
  const forms = commandFormsForSurface(surface, commandName);
  if (!forms.length) {
    return fallback;
  }
  let selected = forms[0];
  if (action) {
    const normalizedCommand = normalizeCommandName(commandName);
    const ranked = [];
    forms.forEach((form, index) => {
      const tokens = cleanText(form).split(/\s+/);
      if (tokens.length < 2 || normalizeCommandName(tokens[0]) !== normalizedCommand) {
        return;
      }
      const variants = actionVariantsFromToken(tokens[1]);
      if (!variants.includes(action)) {
        return;
      }
      const exact = variants.length === 1 && variants[0] === action;
      ranked.push({ score: exact ? 2 : 1, tokens: tokens.length, index, form });
    });
    if (ranked.length) {
      ranked.sort((a, b) => b.score - a.score || a.tokens - b.tokens || a.index - b.index);
      selected = ranked[0].form;
    }
  }
  return `Usage: /${selected}`;
}

function commandActionCandidates(surface, commandName) {
  const entry = commandEntryForSurface(surface, commandName);
  if (!entry) {
    return [];
  }
  const head = normalizeCommandName(String(commandName || "").replace(/^\//, ""));
  const actions = new Set();
  const sources = [
    ...(Array.isArray(entry.formsForSurface) ? entry.formsForSurface : []),
    ...(Array.isArray(entry.completionTokensForSurface) ? entry.completionTokensForSurface : []),
  ];
  for (const source of sources) {
    const tokens = cleanText(source).split(/\s+/).map((item) => normalizeCommandName(item));
    if (tokens[0] !== head || !tokens[1]) {
      continue;
    }
    const candidate = tokens[1].replace(/[[\]<>]/g, "");
    if (candidate) {
      actions.add(candidate);
    }
  }
  return Array.from(actions).sort();
}

function suggestCommandAction(commandName, value, surface) {
  const target = normalizeCommandName(value);
  if (!target) {
    return "";
  }
  const candidates = commandActionCandidates(surface, commandName);
  const scored = scoreSuggestedValues(target, candidates);
  if (!scored.length) {
    return "";
  }
  return ` Did you mean: ${scored.join(", ")}?`;
}

function buildUnknownActionText(surface, commandName, action, fallback) {
  const suggestion = suggestCommandAction(commandName, action, surface);
  const usage = buildCommandUsageText(surface, commandName, fallback);
  const header = `Unknown ${normalizeCommandName(commandName)} action: ${cleanText(action) || "(empty)"}.${suggestion}`;
  return usage ? `${header}\n${usage}` : header;
}

async function gatewayRequest(path, options = {}) {
  return performGatewayRequest(gatewayBase, gatewayAuthToken, path, options);
}

function qqSenderId(event) {
  return String(event?.author?.id || event?.user_id || "").trim() || undefined;
}

function qqSessionMutationPayload(event, state, payload = {}) {
  return {
    ...payload,
    surface: "qq",
    channel_type: "qq",
    conversation_id: state.conversationId,
    sender_id: qqSenderId(event)
  };
}

async function postSharedSessionEnvelope(event, state, suffix, payload, invalidMessage) {
  if (!state.sessionId) {
    await replySafe(event, "No shared session is currently bound.");
    return null;
  }
  const response = await gatewayRequest(
    `/api/v1/agent/sessions/${encodeURIComponent(state.sessionId)}/${suffix}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(qqSessionMutationPayload(event, state, payload))
    }
  );
  const envelope = await response.json();
  if (!envelope?.ok || !envelope?.data) {
    throw new Error(invalidMessage);
  }
  return envelope.data;
}

function toBool(raw) {
  const value = String(raw || "").trim().toLowerCase();
  return value === "1" || value === "true" || value === "on" || value === "yes";
}

function compactText(text, maxLength = 220) {
  const normalized = String(text || "").replace(/\s+/g, " ").trim();
  if (!normalized) {
    return "(empty)";
  }
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, maxLength - 3)}...`;
}

function formatRecentMessages(items) {
  const entries = Array.isArray(items) ? items : [];
  if (!entries.length) {
    return "No recent shared-session messages.";
  }
  return [
    `Latest ${entries.length} shared message(s):`,
    ...entries.map((item) => {
      const surface = String(item?.surface || "unknown").trim() || "unknown";
      const role = String(item?.role || "message").trim() || "message";
      const content = compactText(item?.content || "");
      return `[${surface}/${role}] ${content}`;
    })
  ].join("\n");
}

function safeText(value) {
  return String(value || "").trim();
}

function gatewayErrorDetail(error) {
  const raw = String(error?.message || error || "").trim();
  if (!raw) {
    return "Unknown gateway error.";
  }
  return raw
    .replace(/^Error:\s*/i, "")
    .replace(/^HTTP\s+\d+:\s*/i, "")
    .trim() || raw;
}

function routeOwnership(detail) {
  const origin = safeText(detail?.origin_surface).toLowerCase() || "remote";
  const active = safeText(detail?.active_surface).toLowerCase() || origin || "unknown";
  const flow = origin === active ? origin : `${origin}->${active}`;
  const ownership = Boolean(detail?.reply_enabled) ? "reply" : "own";
  return `${flow} / ${ownership}`;
}

function recoverySnapshot(detail) {
  const recovery = detail?.recovery;
  return recovery && typeof recovery === "object" ? recovery : {};
}

function pendingApprovals(detail) {
  const items = detail?.pending_approvals;
  return Array.isArray(items) ? items.filter((item) => safeText(item?.token)) : [];
}

function recoveryPendingApprovals(detail) {
  const recovery = recoverySnapshot(detail);
  const items = recovery?.pending_approvals;
  return Array.isArray(items) ? items.filter((item) => safeText(item?.token)) : [];
}

function formatSharedSessionRecovery(detail, { includeMessages = false } = {}) {
  const recovery = recoverySnapshot(detail);
  const recoveryState = safeText(recovery?.state) || (detail?.busy ? "running" : "idle");
  const recoverySummary =
    safeText(detail?.busy ? detail?.running_state : recovery?.summary) || "idle";
  const lastActivity = safeText(recovery?.last_activity);
  const lastUser = compactText(recovery?.last_user_message || "", 120);
  const lastAssistant = compactText(recovery?.last_assistant_message || "", 120);
  const liveApprovals = pendingApprovals(detail);
  const lostApprovals = recoveryPendingApprovals(detail);
  const pendingSkillReload = Boolean(detail?.pending_skill_reload);
  const pendingSkillReloadReason = safeText(detail?.pending_skill_reload_reason);

  const lines = [
    "Shared-session recovery:",
    `sessionId: ${safeText(detail?.session_id) || "(unknown)"}`,
    `route: ${routeOwnership(detail)}`,
    `state: ${recoveryState}`,
    `task: ${recoverySummary}`
  ];
  if (lastActivity && lastActivity !== "(empty)") {
    lines.push(`activity: ${lastActivity}`);
  }
  if (lastUser && lastUser !== "(empty)") {
    lines.push(`last user: ${lastUser}`);
  }
  if (lastAssistant && lastAssistant !== "(empty)") {
    lines.push(`last reply: ${lastAssistant}`);
  }
  if (pendingSkillReload) {
    lines.push(`skills: reload pending${pendingSkillReloadReason ? ` (${pendingSkillReloadReason})` : ""}`);
  }
  if (liveApprovals.length) {
    const tokens = liveApprovals.map((item) => `${safeText(item.tool_name) || "tool"}[${safeText(item.token)}]`);
    lines.push(`pending approvals: ${tokens.join(", ")}`);
  } else if (lostApprovals.length) {
    const tokens = lostApprovals.map((item) => `${safeText(item.tool_name) || "tool"}[${safeText(item.token)}]`);
    lines.push(`lost approvals after restart: ${tokens.join(", ")}`);
    lines.push("resume hint: send a new message to continue with recovery context");
  } else if (recoveryState.toLowerCase() === "interrupted") {
    lines.push("resume hint: send a new message to continue with recovery context");
  }
  if (includeMessages) {
    lines.push("");
    lines.push(formatRecentMessages(detail?.recent_messages));
  }
  return lines.join("\n");
}

function normalizeSourceList(value) {
  const raw = Array.isArray(value) ? value : [];
  const seen = new Set();
  const items = [];
  for (const entry of raw) {
    const cleaned = safeText(entry).toLowerCase();
    if (!cleaned || seen.has(cleaned)) {
      continue;
    }
    seen.add(cleaned);
    items.push(cleaned);
  }
  return items;
}

function normalizeContextPolicy(value) {
  const raw = value && typeof value === "object" ? value : {};
  const includeSources = normalizeSourceList(raw.include_sources ?? raw.include);
  const excludeSources = normalizeSourceList(raw.exclude_sources ?? raw.exclude).filter(
    (item) => !includeSources.includes(item)
  );
  const maxItems = Math.max(1, Number(raw.max_items) || 4);
  const maxItemsPerSource = Math.max(1, Number(raw.max_items_per_source) || 1);
  const maxTotalChars = Math.max(200, Number(raw.max_total_chars) || 2400);
  const active =
    includeSources.length > 0 ||
    excludeSources.length > 0 ||
    maxItems !== 4 ||
    maxItemsPerSource !== 1 ||
    maxTotalChars !== 2400;
  return {
    include_sources: includeSources,
    exclude_sources: excludeSources,
    max_items: maxItems,
    max_items_per_source: maxItemsPerSource,
    max_total_chars: maxTotalChars,
    active
  };
}

function contextPolicySummary(policy) {
  const normalized = normalizeContextPolicy(policy);
  const parts = [];
  if (normalized.include_sources.length) {
    parts.push(`include=${normalized.include_sources.join(", ")}`);
  }
  if (normalized.exclude_sources.length) {
    parts.push(`exclude=${normalized.exclude_sources.join(", ")}`);
  }
  parts.push(
    `budget=${normalized.max_items} item(s)/${normalized.max_total_chars} chars/${normalized.max_items_per_source} per-source`
  );
  return parts.join(" | ");
}

function formatRemoteContextShow(detail, mode = "full") {
  const policy = normalizeContextPolicy(detail?.context_policy);
  const prepared = detail?.last_prepared_context && typeof detail.last_prepared_context === "object"
    ? detail.last_prepared_context
    : {};
  const items = Array.isArray(prepared.items) ? prepared.items : [];
  const providerStatuses = Array.isArray(prepared.provider_statuses) ? prepared.provider_statuses : [];
  const lines = [
    "Prepared-context policy:",
    `Policy: ${contextPolicySummary(policy)}`
  ];

  if (!prepared || typeof prepared !== "object" || Object.keys(prepared).length === 0) {
    lines.push("");
    lines.push("Last prepared context: none");
    return lines.join("\n");
  }

  const itemCount = Math.max(0, Number(prepared.item_count) || items.length);
  const sources = Array.isArray(prepared.sources) ? prepared.sources : [];
  lines.push("");
  lines.push(
    `Last prepared context: ${itemCount} item(s)${
      sources.length ? ` from ${sources.join(", ")}` : ""
    }`
  );
  for (const [index, item] of items.entries()) {
    const source = safeText(item?.source) || "context";
    const title = safeText(item?.title) || "Context";
    const content = compactText(item?.content || "", mode === "brief" ? 140 : 220);
    lines.push(`${index + 1}. [${source}] ${title} -> ${content}`);
    if (mode !== "brief" && item?.metadata && typeof item.metadata === "object") {
      const metadata = item.metadata;
      const rankingBasis = safeText(metadata.ranking_basis);
      const rawScore = Number(metadata.ranking_score);
      const itemRelevance = Number(metadata.item_relevance);
      const finalSelection = Number(metadata.final_selection_score);
      const rankingBits = [];
      if (rankingBasis) {
        rankingBits.push(`basis ${rankingBasis}`);
      }
      if (Number.isFinite(rawScore)) {
        rankingBits.push(`raw ${rawScore.toFixed(4)}`);
      }
      if (Number.isFinite(itemRelevance)) {
        rankingBits.push(`item-relevance ${itemRelevance.toFixed(3)}`);
      }
      if (rankingBits.length) {
        lines.push(`   ranking: ${rankingBits.join(" | ")}`);
      }
      if (Number.isFinite(finalSelection)) {
        lines.push(`   selection: final ${finalSelection.toFixed(3)}`);
      }
    }
  }
  if (mode !== "brief" && providerStatuses.length) {
    lines.push("");
    lines.push("Providers:");
    for (const item of providerStatuses) {
      const provider = safeText(item?.provider) || "provider";
      const status = safeText(item?.status) || "unknown";
      const reason = safeText(item?.reason);
      const itemCountValue = Math.max(0, Number(item?.item_count) || 0);
      lines.push(`- ${provider}: ${status}${itemCountValue ? ` (${itemCountValue} item(s))` : ""}${reason ? ` | ${reason}` : ""}`);
    }
  }
  return lines.join("\n");
}

function formatRemoteContextStats(detail) {
  const diagnostics =
    detail?.prepared_context_diagnostics && typeof detail.prepared_context_diagnostics === "object"
      ? detail.prepared_context_diagnostics
      : {};
  const turnCount = Math.max(0, Number(diagnostics.turn_count) || 0);
  const turnsWithContext = Math.max(0, Number(diagnostics.turns_with_context) || 0);
  const turnsWithoutContext = Math.max(0, Number(diagnostics.turns_without_context) || 0);
  const totalItems = Math.max(0, Number(diagnostics.total_items) || 0);
  const curatedDrops = Math.max(0, Number(diagnostics.total_budget_drops) || 0);
  const duplicateDrops = Math.max(0, Number(diagnostics.total_duplicate_drops) || 0);
  const lines = [
    "Prepared-context diagnostics:",
    `Context diagnostics: ${turnCount} turn(s) | ${turnsWithContext} with context | ${turnsWithoutContext} without context | ${totalItems} item(s) | curated ${curatedDrops} | dedupe-drop ${duplicateDrops}`
  ];

  const sourceTurns = diagnostics.source_turn_counts && typeof diagnostics.source_turn_counts === "object"
    ? diagnostics.source_turn_counts
    : {};
  const sourceItems = diagnostics.source_item_counts && typeof diagnostics.source_item_counts === "object"
    ? diagnostics.source_item_counts
    : {};
  const providerStatuses =
    diagnostics.provider_status_by_provider && typeof diagnostics.provider_status_by_provider === "object"
      ? diagnostics.provider_status_by_provider
      : {};

  const sourceNames = Object.keys(sourceTurns);
  if (sourceNames.length) {
    lines.push("");
    lines.push("Sources:");
    for (const name of sourceNames) {
      lines.push(`- ${name}: ${Math.max(0, Number(sourceTurns[name]) || 0)} turn(s) | ${Math.max(0, Number(sourceItems[name]) || 0)} item(s)`);
    }
  }
  const providerNames = Object.keys(providerStatuses);
  if (providerNames.length) {
    lines.push("");
    lines.push("Provider statuses:");
    for (const name of providerNames) {
      const stats = providerStatuses[name] && typeof providerStatuses[name] === "object" ? providerStatuses[name] : {};
      const parts = Object.keys(stats)
        .sort()
        .map((key) => `${key} ${Math.max(0, Number(stats[key]) || 0)}`)
        .filter(Boolean);
      lines.push(`- ${name}: ${parts.join(", ")}`);
    }
  }
  return lines.join("\n");
}

function normalizeRemoteModelIdentity(detail, prefix = "selected_") {
  const source = safeText(detail?.[`${prefix}model_source`]);
  const providerId = safeText(detail?.[`${prefix}provider_id`]);
  const modelId = safeText(detail?.[`${prefix}model_id`]);
  if (!source || !providerId || !modelId) {
    return null;
  }
  return { source, providerId, modelId };
}

function formatModelIdentity(identity) {
  if (!identity) {
    return "auto";
  }
  if (identity.source === "config") {
    return identity.modelId || "auto";
  }
  return `${identity.providerId}/${identity.modelId}`;
}

function formatRemoteModelStatus(detail) {
  const selected = normalizeRemoteModelIdentity(detail, "selected_");
  const pending = normalizeRemoteModelIdentity(detail, "pending_");
  const lines = [
    "Session model:",
    `selected: ${formatModelIdentity(selected)}`
  ];
  if (pending && (!selected || pending.providerId !== selected.providerId || pending.modelId !== selected.modelId || pending.source !== selected.source)) {
    lines.push(`pending: ${formatModelIdentity(pending)} (queued)`);
  } else {
    lines.push("pending: none");
  }
  return lines.join("\n");
}

function buildSharedSessionLabel(item) {
  const title = safeText(item?.title);
  const recovery = recoverySnapshot(item);
  const recoveryState = safeText(recovery?.state).toLowerCase();
  const pendingSkillReload = Boolean(item?.pending_skill_reload);
  if (title) {
    const origin = safeText(item?.origin_surface).toLowerCase() || "remote";
    const active = safeText(item?.active_surface).toLowerCase() || origin || "unknown";
    const messageCount = Number(item?.message_count || 0);
    const suffix =
      recoveryState === "interrupted" || recoveryState === "running"
        ? `${origin}->${active} | ${recoveryState}`
        : pendingSkillReload
          ? `${origin}->${active} | reload`
          : `${origin}->${active}`;
    return `${compactText(title, 40)} | ${messageCount} msg | ${suffix}`;
  }
  const channel = safeText(item?.channel_type).toLowerCase();
  const conversation = safeText(item?.conversation_id);
  const origin = safeText(item?.origin_surface).toLowerCase() || channel || "remote";
  const active = safeText(item?.active_surface).toLowerCase() || origin || "unknown";
  const prefix = channel ? channel.toUpperCase() : origin.toUpperCase();
  const subject = conversation
    ? `${prefix} ${conversation}`
    : `${prefix} ${compactText(item?.session_id || "", 18)}`;
  const messageCount = Number(item?.message_count || 0);
  const suffix =
    recoveryState === "interrupted" || recoveryState === "running"
      ? `${origin}->${active} | ${recoveryState}`
      : pendingSkillReload
        ? `${origin}->${active} | reload`
        : `${origin}->${active}`;
  return `${subject} | ${messageCount} msg | ${suffix}`;
}

function formatSharedSessionList(items, currentSessionId) {
  const entries = Array.isArray(items) ? items : [];
  if (!entries.length) {
    return "No shared sessions available.";
  }
  return [
    "Shared sessions:",
    ...entries.map((item, index) => {
      const marker = safeText(item?.session_id) === safeText(currentSessionId) ? "*" : " ";
      return `${marker} #${index + 1} ${buildSharedSessionLabel(item)} | ${compactText(item?.session_id || "", 24)}`;
    })
  ].join("\n");
}

async function fetchSharedSessions(workspaceDir = "") {
  const params = new URLSearchParams();
  params.set("shared_only", "true");
  const normalizedWorkspace = safeText(workspaceDir);
  if (normalizedWorkspace) {
    params.set("workspace_dir", normalizedWorkspace);
  }
  const response = await gatewayRequest(`/api/v1/agent/sessions?${params.toString()}`);
  const envelope = await response.json();
  if (!envelope?.ok || !Array.isArray(envelope?.data)) {
    throw new Error("Invalid session list response from gateway");
  }
  return envelope.data.slice().sort((left, right) => {
    const leftUpdated = safeText(left?.updated_at);
    const rightUpdated = safeText(right?.updated_at);
    return rightUpdated.localeCompare(leftUpdated);
  });
}

function normalizeWorkspaceKey(value) {
  return safeText(value).replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
}

function sessionsForWorkspace(items, workspaceDir) {
  const entries = Array.isArray(items) ? items : [];
  const workspaceKey = normalizeWorkspaceKey(workspaceDir);
  if (!workspaceKey) {
    return entries;
  }
  return entries.filter(
    (item) => normalizeWorkspaceKey(item?.workspace_dir) === workspaceKey
  );
}

function selectPreferredSharedSession(items, state) {
  const candidates = sessionsForWorkspace(items, state?.workspaceDir);
  if (!candidates.length) {
    return null;
  }
  return candidates[0];
}

function applySharedSessionBinding(state, item) {
  const sessionId = safeText(item?.session_id);
  if (sessionId) {
    state.sessionId = sessionId;
  }
  const workspaceDir = safeText(item?.workspace_dir);
  if (workspaceDir) {
    state.workspaceDir = workspaceDir;
  }
  return sessionId;
}

async function syncPreferredSharedSession(state) {
  const items = await fetchSharedSessions(state?.workspaceDir);
  const pinnedSessionId = safeText(state?.sessionId);
  if (state?.followLatest === false && pinnedSessionId) {
    const pinned = items.find((item) => safeText(item?.session_id) === pinnedSessionId);
    if (pinned) {
      applySharedSessionBinding(state, pinned);
      return { items, preferred: pinned };
    }
    state.followLatest = true;
    state.sessionId = "";
  }
  const preferred = selectPreferredSharedSession(items, state);
  if (!preferred) {
    state.sessionId = "";
    return { items, preferred: null };
  }
  applySharedSessionBinding(state, preferred);
  return { items, preferred };
}

async function fetchSharedSessionDetail(sessionId, recentLimit = 10) {
  const response = await gatewayRequest(
    `/api/v1/agent/sessions/${encodeURIComponent(sessionId)}?recent_limit=${Math.max(1, Number(recentLimit) || 1)}`
  );
  const envelope = await response.json();
  if (!envelope?.ok || !envelope?.data || typeof envelope.data !== "object") {
    throw new Error("Invalid session detail response from gateway");
  }
  return envelope.data;
}

async function fetchSharedModelCatalog() {
  const response = await gatewayRequest("/api/v1/agent/models");
  const envelope = await response.json();
  const items = Array.isArray(envelope?.data?.items) ? envelope.data.items : [];
  if (!Array.isArray(items)) {
    throw new Error("Invalid model catalog response from gateway");
  }
  return items;
}

function formatSharedModelCatalog(items, currentDetail) {
  const providers = Array.isArray(items) ? items : [];
  if (!providers.length) {
    return "No models available.";
  }
  const selected = normalizeRemoteModelIdentity(currentDetail, "selected_");
  const pending = normalizeRemoteModelIdentity(currentDetail, "pending_");
  const lines = ["Available models:"];
  for (const provider of providers) {
    const providerId = safeText(provider?.provider_id) || "provider";
    const source = safeText(provider?.source) || "custom";
    const providerName = safeText(provider?.provider_name) || providerId;
    lines.push(`${providerName} [${source}] | ${providerId}`);
    const models = Array.isArray(provider?.models) ? provider.models : [];
    for (const model of models) {
      const modelId = safeText(model?.model_id);
      if (!modelId) {
        continue;
      }
      const displayName = safeText(model?.display_name) || modelId;
      const tags = [];
      if (selected && selected.source === source && selected.providerId === providerId && selected.modelId === modelId) {
        tags.push("selected");
      }
      if (pending && pending.source === source && pending.providerId === providerId && pending.modelId === modelId) {
        tags.push("queued");
      }
      const tagText = tags.length ? ` [${tags.join(", ")}]` : "";
      lines.push(`- ${modelId} (${displayName})${tagText}`);
    }
  }
  return lines.join("\n");
}

async function controlSharedSession(event, state, action, reason) {
  return postSharedSessionEnvelope(
    event,
    state,
    "control",
    {
      action,
      reason: safeText(reason) || undefined
    },
    "Invalid session control response from gateway"
  );
}

async function updateSharedSessionModel(event, state, payload) {
  return postSharedSessionEnvelope(
    event,
    state,
    "model",
    {
      provider_source: safeText(payload?.provider_source) || undefined,
      provider_id: safeText(payload?.provider_id) || undefined,
      model_id: safeText(payload?.model_id) || undefined
    },
    "Invalid session model response from gateway"
  );
}

async function updateSharedSessionContext(event, state, payload) {
  return postSharedSessionEnvelope(
    event,
    state,
    "context",
    {
      action: safeText(payload?.action) || undefined,
      sources: Array.isArray(payload?.sources) ? payload.sources : [],
      max_items: payload?.max_items ?? null,
      max_total_chars: payload?.max_total_chars ?? null,
      max_items_per_source: payload?.max_items_per_source ?? null
    },
    "Invalid session context response from gateway"
  );
}

async function manageSharedSessionMemory(event, state, payload) {
  return postSharedSessionEnvelope(
    event,
    state,
    "memory",
    {
      action: safeText(payload?.action) || undefined,
      engram_id: safeText(payload?.engram_id) || undefined,
      content: safeText(payload?.content) || undefined,
      query: safeText(payload?.query) || undefined,
      day: safeText(payload?.day) || undefined,
      export_format: safeText(payload?.export_format) || undefined,
      detail_mode: safeText(payload?.detail_mode) || undefined
    },
    "Invalid session memory response from gateway"
  );
}

async function manageSharedSessionSkill(event, state, payload) {
  return postSharedSessionEnvelope(
    event,
    state,
    "skill",
    {
      action: safeText(payload?.action) || undefined,
      skill_name: safeText(payload?.skill_name) || undefined,
      path: safeText(payload?.path) || undefined,
      query: safeText(payload?.query) || undefined,
      mode: safeText(payload?.mode) || undefined
    },
    "Invalid session skill response from gateway"
  );
}

async function resolveSharedSessionApproval(event, state, approved, token) {
  return postSharedSessionEnvelope(
    event,
    state,
    "approval",
    {
      approved: Boolean(approved),
      token: safeText(token) || undefined
    },
    "Invalid session approval response from gateway"
  );
}

async function updateSharedSessionRuntimePolicy(event, state, payload) {
  return postSharedSessionEnvelope(
    event,
    state,
    "policy",
    {
      approval_profile: safeText(payload?.approval_profile) || undefined,
      access_level: safeText(payload?.access_level) || undefined
    },
    "Invalid runtime policy response from gateway"
  );
}

function formatSharedSessionRuntimePolicyResult(data) {
  const execution = safeText(data?.approval_profile) || "build";
  const access = safeText(data?.access_level) || "default";
  return [
    `Runtime policy updated: ${execution} / ${access}`,
    `sessionId: ${safeText(data?.session_id) || "(unknown)"}`,
    `surface: ${safeText(data?.active_surface) || "unknown"}`
  ].join("\n");
}

function formatApprovalArgumentValue(value, maxLength = 120) {
  if (Array.isArray(value)) {
    const joined = value
      .map((item) => compactText(item, Math.max(24, Math.floor(maxLength / 3))))
      .filter(Boolean)
      .join(", ");
    return compactText(joined || "(empty)", maxLength);
  }
  if (value && typeof value === "object") {
    try {
      return compactText(JSON.stringify(value), maxLength);
    } catch {
      return "(object)";
    }
  }
  return compactText(String(value ?? ""), maxLength);
}

function formatApprovalArgumentsSummary(argumentsPayload) {
  const payload = argumentsPayload && typeof argumentsPayload === "object" ? argumentsPayload : {};
  const entries = Object.entries(payload);
  if (!entries.length) {
    return ["arguments: (none)"];
  }

  const priorityKeys = [
    "command",
    "workdir",
    "path",
    "paths",
    "url",
    "query",
    "pattern",
    "target",
    "filename",
    "location",
    "model",
    "provider",
  ];
  const ordered = [];
  const seen = new Set();

  for (const key of priorityKeys) {
    if (Object.prototype.hasOwnProperty.call(payload, key)) {
      ordered.push([key, payload[key]]);
      seen.add(key);
    }
  }
  for (const [key, value] of entries) {
    if (seen.has(key)) {
      continue;
    }
    ordered.push([key, value]);
  }

  const visible = ordered.slice(0, 5).map(
    ([key, value]) => `- ${key}: ${formatApprovalArgumentValue(value)}`
  );
  if (ordered.length > visible.length) {
    visible.push(`- more: ${ordered.length - visible.length} field(s) hidden`);
  }
  return ["arguments:", ...visible];
}

function formatApprovalRequestedMessage(data, state) {
  const toolName = safeText(data?.tool_name) || "tool";
  const token = safeText(data?.token) || "(missing token)";
  const reason = safeText(data?.reason) || "No reason provided.";
  const argumentLines = formatApprovalArgumentsSummary(data?.arguments);
  return [
    `Approval required: ${toolName}`,
    `sessionId: ${state.sessionId || "(binding pending)"}`,
    `token: ${token}`,
    `reason: ${reason}`,
    ...argumentLines,
    `approve: /approve ${token}`,
    `deny: /deny ${token}`
  ].join("\n");
}

function formatSessionControlResult(data) {
  const applied = Boolean(data?.applied);
  const action = safeText(data?.action);
  const stats = data?.stats && typeof data.stats === "object" ? data.stats : {};
  if (action === "mcp_status" || action === "mcp_list" || action === "mcp_reload") {
    const summary = safeText(stats.summary);
    const details = String(stats.details || "").trim();
    if (summary && details) {
      return `${summary}\n\n${details}`;
    }
    return details || summary || "MCP command completed.";
  }
  const title =
    action === "compact"
      ? applied
        ? "Context compacted."
        : "Context already compact."
      : applied
        ? "Older memories dropped."
        : "No older memories to drop.";
  const lines = [
    title,
    `sessionId: ${safeText(data?.session_id) || "(unknown)"}`,
    `messages: ${Number(data?.message_count_before || 0)} -> ${Number(data?.message_count_after || 0)}`,
    `tokens: ${Number(data?.token_count_before || 0)} -> ${Number(data?.token_count_after || 0)}`
  ];
  if (safeText(data?.reason)) {
    lines.push(`reason: ${safeText(data.reason)}`);
  }
  if (stats && typeof stats === "object") {
    lines.push(
      `stats: masked=${Number(stats.masked_messages || 0)}, snipped=${Number(
        stats.snipped_messages || 0
      )}, merged=${Number(stats.merged_messages || 0)}`
    );
  }
  return lines.join("\n");
}

function formatSharedSessionMemoryResult(data) {
  const result = data?.result && typeof data.result === "object" ? data.result : {};
  const summary = safeText(result.summary);
  const details = String(result.details || "").trim();
  if (summary && details) {
    return `${summary}\n\n${details}`;
  }
  return details || summary || "Memory command completed.";
}

function formatSharedSessionSkillResult(data) {
  const result = data?.result && typeof data.result === "object" ? data.result : {};
  const summary = safeText(result.summary);
  const details = String(result.details || "").trim();
  const queuedOther = Number(result?.reload_queued_other_sessions || 0);
  const queuedCurrent = Boolean(result?.reload_queued_current_session);
  const extra = [];
  if (queuedCurrent) {
    extra.push("current session reload is queued and will auto-apply after the running turn");
  }
  if (queuedOther > 0) {
    extra.push(`${queuedOther} other workspace session(s) are waiting for skill reload`);
  }
  const extraText = extra.join("\n");
  if (summary && details && extraText) {
    return `${summary}\n\n${details}\n\n${extraText}`;
  }
  if (summary && details) {
    return `${summary}\n\n${details}`;
  }
  if (summary && extraText) {
    return `${summary}\n\n${extraText}`;
  }
  if (details && extraText) {
    return `${details}\n\n${extraText}`;
  }
  return extraText || details || summary || "Skill command completed.";
}

function resolveSharedSessionSelector(items, selector) {
  const target = safeText(selector);
  if (!target) {
    return null;
  }
  if (/^\d+$/.test(target)) {
    const ordinal = Number(target);
    if (ordinal >= 1 && ordinal <= items.length) {
      return { item: items[ordinal - 1], ordinal };
    }
    return null;
  }
  const exact = items.find((item) => safeText(item?.session_id) === target);
  if (exact) {
    return { item: exact, ordinal: items.indexOf(exact) + 1 };
  }
  const prefix = items.find((item) => safeText(item?.session_id).startsWith(target));
  if (prefix) {
    return { item: prefix, ordinal: items.indexOf(prefix) + 1 };
  }
  return null;
}

async function replySafe(event, text) {
  const chunks = splitLongText(text || "", maxReplyChunkSize);
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

function invocationArgs(invocation) {
  return Array.isArray(invocation?.args) ? invocation.args : [];
}

function invocationJoinedArgs(invocation, start = 0) {
  return invocationArgs(invocation).slice(start).join(" ").trim();
}

async function ensureSharedSessionBound(event, state, { notifyWhenMissing = true } = {}) {
  try {
    const synced = await syncPreferredSharedSession(state);
    if (safeText(synced?.preferred?.session_id)) {
      return true;
    }
  } catch {
    // best effort only; fall back to the local binding below
  }
  if (state.sessionId) {
    return true;
  }
  if (notifyWhenMissing) {
    await replySafe(event, "No shared session is currently bound.");
  }
  return false;
}

async function handleHelpCommand({ event }) {
  await replySafe(event, buildSharedHelpText("qq"));
}

async function handleStatusCommand({ event, state }) {
  if (await ensureSharedSessionBound(event, state, { notifyWhenMissing: false })) {
    const detail = await fetchSharedSessionDetail(state.sessionId, 6);
    await replySafe(
      event,
      [
        formatSharedSessionRecovery(detail),
        "",
        `workspace: ${state.workspaceDir}`,
        `dryRun: ${state.dryRun}`
      ].join("\n")
    );
    return;
  }
  await replySafe(
    event,
    `Session status:\nsessionId: ${state.sessionId || "(none)"}\nworkspace: ${state.workspaceDir}\ndryRun: ${state.dryRun}`
  );
}

async function handlePingCommand({ event }) {
  await replySafe(event, "pong");
}

async function handleWorkspaceCommand({ event, state, invocation }) {
  const value = invocationJoinedArgs(invocation);
  if (!value) {
    await replySafe(event, buildCommandUsageText("qq", "workspace", "Usage: /workspace <path>"));
    return;
  }
  try {
    state.workspaceDir = ensureWorkspaceInAllowed(value, allowedWorkspaceRoots);
  } catch (error) {
    await replySafe(event, `Workspace rejected: ${String(error?.message || error)}`);
    return;
  }
  state.sessionId = "";
  state.followLatest = true;
  await replySafe(event, `Workspace set to: ${state.workspaceDir}`);
}

async function handleDryrunCommand({ event, state, invocation }) {
  const value = invocationJoinedArgs(invocation);
  if (!value) {
    await replySafe(event, buildCommandUsageText("qq", "dryrun", "Usage: /dryrun <on|off>"));
    return;
  }
  state.dryRun = toBool(value);
  await replySafe(event, `Dry run set to: ${state.dryRun}`);
}

async function handleSessionCommand({ event, state, invocation }) {
  const selector = invocationJoinedArgs(invocation);
  let items = [];
  try {
    const syncResult = await syncPreferredSharedSession(state);
    items = Array.isArray(syncResult?.items) ? syncResult.items : [];
  } catch {
    items = await fetchSharedSessions(state?.workspaceDir);
  }
  if (!selector) {
    await replySafe(event, formatSharedSessionList(items, state.sessionId));
    return;
  }
  const normalizedSelector = safeText(selector).toLowerCase();
  if (normalizedSelector === "auto" || normalizedSelector === "latest") {
    state.followLatest = true;
    const syncResult = await syncPreferredSharedSession(state);
    const preferred = syncResult?.preferred;
    if (!preferred) {
      await replySafe(event, "No shared sessions available.");
      return;
    }
    await replySafe(
      event,
      [
        "Following latest shared session.",
        buildSharedSessionLabel(preferred),
        `sessionId: ${safeText(preferred?.session_id) || "(none)"}`,
        `workspace: ${safeText(preferred?.workspace_dir) || state.workspaceDir}`
      ].join("\n")
    );
    return;
  }
  const resolved = resolveSharedSessionSelector(items, selector);
  if (!resolved || !resolved.item) {
    await replySafe(
      event,
      `Session not found: ${selector}\n\n${formatSharedSessionList(items, state.sessionId)}`
    );
    return;
  }
  const targetSessionId = safeText(resolved.item.session_id);
  if (!targetSessionId) {
    await replySafe(event, "Target session is missing session_id.");
    return;
  }
  state.sessionId = targetSessionId;
  state.followLatest = false;
  const targetWorkspace = safeText(resolved.item.workspace_dir);
  if (targetWorkspace) {
    state.workspaceDir = targetWorkspace;
  }
  await replySafe(
    event,
    [
      `Bound to shared session #${resolved.ordinal}`,
      buildSharedSessionLabel(resolved.item),
      `sessionId: ${state.sessionId}`,
      `workspace: ${state.workspaceDir}`
    ].join("\n")
  );
}

async function handleResetCommand({ event, state }) {
  await gatewayRequest(`/api/v1/agent/sessions/${encodeURIComponent(state.sessionId)}/reset`, {
    method: "POST"
  });
  await replySafe(event, `Session reset: ${state.sessionId}`);
}

async function handleCancelCommand({ event, state }) {
  try {
    await gatewayRequest(`/api/v1/agent/sessions/${encodeURIComponent(state.sessionId)}/cancel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(
        qqSessionMutationPayload(event, state, {
          reason: "user_cancel"
        })
      )
    });
  } catch (error) {
    if (String(error).includes("HTTP 409")) {
      await replySafe(event, gatewayErrorDetail(error));
      return;
    }
    throw error;
  }
  await replySafe(event, `Cancellation requested: ${state.sessionId}`);
}

async function handleContinueCommand({ event, state }) {
  const detail = await fetchSharedSessionDetail(state.sessionId, 10);
  await replySafe(event, formatSharedSessionRecovery(detail, { includeMessages: true }));
}

async function handleModelCommand({ event, state, invocation }) {
  const args = invocationArgs(invocation);
  const action = safeText(args[0] || "").toLowerCase() || "show";
  if (action === "show") {
    if (args.length > 1) {
      await replySafe(event, buildCommandUsageText("qq", "model", { action: "show" }));
      return;
    }
    const detail = await fetchSharedSessionDetail(state.sessionId, 10);
    await replySafe(event, formatRemoteModelStatus(detail));
    return;
  }
  if (action === "list") {
    if (args.length > 1) {
      await replySafe(event, buildCommandUsageText("qq", "model", { action: "list" }));
      return;
    }
    const [items, detail] = await Promise.all([
      fetchSharedModelCatalog(),
      fetchSharedSessionDetail(state.sessionId, 10)
    ]);
    await replySafe(event, formatSharedModelCatalog(items, detail));
    return;
  }
  if (action === "use") {
    if (args.length < 3) {
      await replySafe(event, buildCommandUsageText("qq", "model", { action: "use" }));
      return;
    }
    const providerId = safeText(args[1]);
    const modelId = safeText(args[2]);
    const result = await updateSharedSessionModel(event, state, {
      provider_id: providerId,
      model_id: modelId
    });
    const selected = normalizeRemoteModelIdentity(result, "selected_");
    const pending = normalizeRemoteModelIdentity(result, "pending_");
    const lines = [];
    if (Boolean(result?.queued)) {
      lines.push(
        `Queued model: ${formatModelIdentity(
          pending || { source: safeText(result?.pending_model_source) || "custom", providerId, modelId }
        )}`
      );
    } else {
      lines.push(
        `Selected model: ${formatModelIdentity(
          selected || { source: safeText(result?.selected_model_source) || "custom", providerId, modelId }
        )}`
      );
    }
    lines.push(`sessionId: ${safeText(result?.session_id) || state.sessionId}`);
    await replySafe(event, lines.join("\n"));
    return;
  }
  await replySafe(
    event,
    buildUnknownActionText("qq", "model", action, buildCommandUsageText("qq", "model"))
  );
}

async function handleApprovalCommand({ event, state, invocation }) {
  const resolvedToken = invocationJoinedArgs(invocation) || undefined;
  try {
    const result = await resolveSharedSessionApproval(
      event,
      state,
      invocation.name === "/approve",
      resolvedToken
    );
    await replySafe(
      event,
      `${result.decision}: ${result.tool_name}\nsessionId: ${result.session_id}\ntoken: ${result.token}`
    );
  } catch (error) {
    await replySafe(event, gatewayErrorDetail(error));
  }
}

async function handleRuntimePolicyCommand({ event, state, entry }) {
  const payload =
    entry?.runtimePolicyPayload && typeof entry.runtimePolicyPayload === "object"
      ? entry.runtimePolicyPayload
      : {};
  try {
    const result = await updateSharedSessionRuntimePolicy(event, state, payload);
    await replySafe(event, formatSharedSessionRuntimePolicyResult(result));
  } catch (error) {
    await replySafe(event, gatewayErrorDetail(error));
  }
}

async function handleContextCommand({ event, state, invocation }) {
  const args = invocationArgs(invocation);
  let action = safeText(args[0] || "").toLowerCase() || "show";
  if (action === "brief" || action === "full") {
    action = "show";
  }
  if (action === "show") {
    const detailMode = (() => {
      const candidate = safeText(args[1] || args[0] || "").toLowerCase();
      if (candidate === "brief" || candidate === "full") {
        return candidate;
      }
      return "full";
    })();
    if (
      args.length > 2 ||
      (args.length > 1 && !["brief", "full"].includes(safeText(args[1]).toLowerCase()))
    ) {
      await replySafe(event, buildCommandUsageText("qq", "context", { action: "show" }));
      return;
    }
    const detail = await fetchSharedSessionDetail(state.sessionId, 10);
    await replySafe(event, formatRemoteContextShow(detail, detailMode));
    return;
  }
  if (action === "stats") {
    if (args.length > 1) {
      await replySafe(event, buildCommandUsageText("qq", "context", { action: "stats" }));
      return;
    }
    const detail = await fetchSharedSessionDetail(state.sessionId, 10);
    await replySafe(event, formatRemoteContextStats(detail));
    return;
  }
  const usageText = buildCommandUsageText("qq", "context", { action });
  const payload = {};
  if (action === "include" || action === "exclude") {
    payload.action = action;
    payload.sources = args.slice(1).map((item) => safeText(item)).filter(Boolean);
  } else if (action === "budget") {
    if (args.length > 4) {
      await replySafe(event, usageText);
      return;
    }
    const maxItems = Number(args[1]);
    const maxTotalChars = Number(args[2]);
    const maxItemsPerSource = Number(args[3]);
    payload.action = "budget";
    payload.max_items = Number.isFinite(maxItems) && maxItems > 0 ? Math.trunc(maxItems) : undefined;
    payload.max_total_chars =
      Number.isFinite(maxTotalChars) && maxTotalChars > 0 ? Math.trunc(maxTotalChars) : undefined;
    payload.max_items_per_source =
      Number.isFinite(maxItemsPerSource) && maxItemsPerSource > 0
        ? Math.trunc(maxItemsPerSource)
        : undefined;
  } else if (action === "reset") {
    if (args.length > 1) {
      await replySafe(event, usageText);
      return;
    }
    payload.action = "reset";
  } else {
    await replySafe(
      event,
      buildUnknownActionText(
        "qq",
        "context",
        action,
        buildCommandUsageText("qq", "context")
      )
    );
    return;
  }

  try {
    await updateSharedSessionContext(event, state, payload);
    const detail = await fetchSharedSessionDetail(state.sessionId, 10);
    const summaryLine =
      action === "reset"
        ? "Context policy reset to defaults."
        : action === "budget"
          ? `Context budget updated: ${contextPolicySummary(detail?.context_policy)}`
          : `Context policy updated: ${contextPolicySummary(detail?.context_policy)}`;
    await replySafe(
      event,
      [
        summaryLine,
        "",
        formatRemoteContextShow(detail, "brief")
      ].join("\n")
    );
  } catch (error) {
    await replySafe(event, gatewayErrorDetail(error));
  }
}

async function handleMemoryCommand({ event, state, invocation }) {
  const args = invocationArgs(invocation);
  let action = safeText(args[0] || "").toLowerCase() || "status";
  if (action === "brief" || action === "full") {
    action = "show";
  }
  const usageText = buildCommandUsageText("qq", "memory", { action });
  const zeroArgDetailModes = new Map([
    ["status", "brief"],
    ["list", "full"],
    ["overview", "full"],
    ["runtime", "full"],
    ["refresh", "full"],
  ]);
  const textQueryActions = new Set(["profile", "notes"]);
  const payload = {};

  if (zeroArgDetailModes.has(action)) {
    if (args.length > 1) {
      await replySafe(event, usageText);
      return;
    }
    payload.action = action;
    payload.detail_mode = zeroArgDetailModes.get(action);
  } else if (action === "show") {
    if (args.length > 2) {
      await replySafe(event, usageText);
      return;
    }
    const selectorOrMode = safeText(args[1]);
    const normalizedSelectorOrMode = selectorOrMode.toLowerCase();
    if (!selectorOrMode || normalizedSelectorOrMode === "brief" || normalizedSelectorOrMode === "full") {
      payload.action = "show";
      payload.detail_mode =
        normalizedSelectorOrMode === "brief" || normalizedSelectorOrMode === "full"
          ? normalizedSelectorOrMode
          : "full";
    } else {
      payload.action = "session_show";
      payload.engram_id = selectorOrMode;
      payload.detail_mode = "full";
    }
  } else if (action === "export") {
    if (args.length > 2) {
      await replySafe(event, usageText);
      return;
    }
    payload.action = "export";
    payload.export_format = safeText(args[1]).toLowerCase() || undefined;
    payload.detail_mode = "full";
  } else if (action === "consolidated") {
    const consolidatedAction = safeText(args[1] || "").toLowerCase() || "show";
    if (consolidatedAction === "show") {
      if (args.length > 2) {
        await replySafe(event, usageText);
        return;
      }
      payload.action = "consolidated_show";
      payload.detail_mode = "full";
    } else if (consolidatedAction === "search") {
      payload.action = "consolidated_search";
      payload.query = args.slice(2).join(" ").trim() || undefined;
      payload.detail_mode = "full";
    } else {
      await replySafe(
        event,
        `Unknown memory consolidated action: ${consolidatedAction || "(empty)"}.\n${buildCommandUsageText("qq", "memory", {
          action: "consolidated"
        })}`
      );
      return;
    }
  } else if (textQueryActions.has(action)) {
    payload.action = action;
    payload.query = args.slice(1).join(" ").trim() || undefined;
    payload.detail_mode = "full";
  } else if (action === "daily") {
    payload.action = "daily";
    payload.day = safeText(args[1]) || undefined;
    payload.detail_mode = "full";
  } else if (action === "shared") {
    const sharedAction = safeText(args[1] || "").toLowerCase() || "list";
    if (sharedAction === "list" || sharedAction === "clear") {
      if (args.length > 2) {
        await replySafe(event, usageText);
        return;
      }
      payload.action = sharedAction === "list" ? "shared_list" : "shared_clear";
      payload.detail_mode = "full";
    } else if (sharedAction === "show") {
      if (args.length > 3) {
        await replySafe(event, usageText);
        return;
      }
      payload.action = "shared_show";
      payload.engram_id = safeText(args[2]) || undefined;
      payload.detail_mode = "full";
    } else {
      await replySafe(
        event,
        `Unknown memory shared action: ${sharedAction || "(empty)"}.\n${buildCommandUsageText("qq", "memory", {
          action: "shared"
        })}`
      );
      return;
    }
  } else if (action === "promote") {
    const target = safeText(args[1]).toLowerCase();
    const promoteMap = new Map([
      ["shared", "promote_shared"],
      ["note", "promote_note"],
      ["profile", "promote_profile"],
    ]);
    if (!promoteMap.has(target)) {
      await replySafe(event, usageText);
      return;
    }
    payload.action = promoteMap.get(target);
    payload.engram_id = safeText(args[2]) || undefined;
    payload.detail_mode = "full";
  } else if (action === "save") {
    const target = safeText(args[1]).toLowerCase();
    const saveMap = new Map([
      ["note", "save_note"],
      ["profile", "save_profile"],
    ]);
    if (!saveMap.has(target)) {
      await replySafe(event, usageText);
      return;
    }
    payload.action = saveMap.get(target);
    payload.content = args.slice(2).join(" ").trim() || undefined;
    payload.detail_mode = "full";
  } else {
    await replySafe(
      event,
      buildUnknownActionText(
        "qq",
        "memory",
        action,
        buildCommandUsageText("qq", "memory")
      )
    );
    return;
  }

  try {
    const result = await manageSharedSessionMemory(event, state, payload);
    await replySafe(event, formatSharedSessionMemoryResult(result));
  } catch (error) {
    await replySafe(event, gatewayErrorDetail(error));
  }
}

async function handleSkillCommand({ event, state, invocation }) {
  const args = invocationArgs(invocation);
  const action = safeText(args[0] || "").toLowerCase() || "list";
  const usageText = buildCommandUsageText("qq", "skill", { action });
  const textValue = args.slice(1).join(" ").trim();
  const zeroArgActions = new Set(["list", "active", "reset", "refresh"]);
  const fieldByAction = new Map([
    ["show", "skill_name"],
    ["search", "query"],
    ["install", "path"],
    ["uninstall", "skill_name"],
    ["rollback", "skill_name"],
    ["enable", "skill_name"],
    ["disable", "skill_name"],
  ]);

  if (zeroArgActions.has(action) && args.length > 1) {
    await replySafe(event, usageText);
    return;
  }
  if (action === "mode" && args.length > 2) {
    await replySafe(event, usageText);
    return;
  }
  if (!zeroArgActions.has(action) && action !== "mode" && !fieldByAction.has(action)) {
    await replySafe(
      event,
      buildUnknownActionText("qq", "skill", action, buildCommandUsageText("qq", "skill"))
    );
    return;
  }

  const payload = { action };
  const fieldName = fieldByAction.get(action);
  if (fieldName) {
    payload[fieldName] = textValue || undefined;
  }
  if (action === "mode") {
    payload.mode = safeText(args[1]) || undefined;
  }

  try {
    const result = await manageSharedSessionSkill(event, state, payload);
    await replySafe(event, formatSharedSessionSkillResult(result));
  } catch (error) {
    await replySafe(event, gatewayErrorDetail(error));
  }
}

async function handleMcpCommand({ event, state, invocation }) {
  const args = invocationArgs(invocation);
  const action = safeText(args[0] || "").toLowerCase() || "status";
  const mcpActionMap = new Map([
    ["status", "mcp_status"],
    ["list", "mcp_list"],
    ["reload", "mcp_reload"],
  ]);
  if (!mcpActionMap.has(action)) {
    await replySafe(
      event,
      buildUnknownActionText("qq", "mcp", action, buildCommandUsageText("qq", "mcp"))
    );
    return;
  }
  if (args.length > 1) {
    await replySafe(event, buildCommandUsageText("qq", "mcp", { action }));
    return;
  }
  try {
    const result = await controlSharedSession(event, state, mcpActionMap.get(action));
    if (result) {
      await replySafe(event, formatSessionControlResult(result));
    }
  } catch (error) {
    await replySafe(event, gatewayErrorDetail(error));
  }
}

async function handleContextControlCommand({ event, state, invocation, entry }) {
  const action = safeText(entry?.sessionControlAction) || "compact";
  const result = await controlSharedSession(event, state, action, invocationJoinedArgs(invocation));
  if (result) {
    await replySafe(event, formatSessionControlResult(result));
  }
}

async function handleClearCommand({ event, state }) {
  conversationBindings.delete(state.conversationId);
  await replySafe(event, "Local QQ conversation cache cleared.");
}

function qqCommandEntry(
  handler,
  {
    requiresSharedSession = false,
    runtimePolicyPayload = null,
    sessionControlAction = "",
  } = {}
) {
  return {
    handler,
    requiresSharedSession,
    runtimePolicyPayload,
    sessionControlAction,
  };
}

const qqCommandHandlers = new Map([
  ["/help", qqCommandEntry(handleHelpCommand)],
  ["/status", qqCommandEntry(handleStatusCommand)],
  ["/ping", qqCommandEntry(handlePingCommand)],
  ["/workspace", qqCommandEntry(handleWorkspaceCommand)],
  ["/dryrun", qqCommandEntry(handleDryrunCommand)],
  ["/session", qqCommandEntry(handleSessionCommand)],
  ["/reset", qqCommandEntry(handleResetCommand, { requiresSharedSession: true })],
  ["/cancel", qqCommandEntry(handleCancelCommand, { requiresSharedSession: true })],
  ["/continue", qqCommandEntry(handleContinueCommand, { requiresSharedSession: true })],
  ["/model", qqCommandEntry(handleModelCommand, { requiresSharedSession: true })],
  ["/approve", qqCommandEntry(handleApprovalCommand, { requiresSharedSession: true })],
  ["/deny", qqCommandEntry(handleApprovalCommand, { requiresSharedSession: true })],
  [
    "/plan",
    qqCommandEntry(handleRuntimePolicyCommand, {
      requiresSharedSession: true,
      runtimePolicyPayload: { approval_profile: "plan" },
    })
  ],
  [
    "/build",
    qqCommandEntry(handleRuntimePolicyCommand, {
      requiresSharedSession: true,
      runtimePolicyPayload: { approval_profile: "build" },
    })
  ],
  [
    "/default",
    qqCommandEntry(handleRuntimePolicyCommand, {
      requiresSharedSession: true,
      runtimePolicyPayload: { access_level: "default" },
    })
  ],
  [
    "/full_access",
    qqCommandEntry(handleRuntimePolicyCommand, {
      requiresSharedSession: true,
      runtimePolicyPayload: { access_level: "full-access" },
    })
  ],
  ["/context", qqCommandEntry(handleContextCommand, { requiresSharedSession: true })],
  ["/memory", qqCommandEntry(handleMemoryCommand, { requiresSharedSession: true })],
  ["/skill", qqCommandEntry(handleSkillCommand, { requiresSharedSession: true })],
  ["/mcp", qqCommandEntry(handleMcpCommand, { requiresSharedSession: true })],
  [
    "/compact",
    qqCommandEntry(handleContextControlCommand, {
      requiresSharedSession: true,
      sessionControlAction: "compact",
    })
  ],
  [
    "/drop_memories",
    qqCommandEntry(handleContextControlCommand, {
      requiresSharedSession: true,
      sessionControlAction: "drop_memories",
    })
  ],
  ["/clear", qqCommandEntry(handleClearCommand)],
]);

async function handleCommand(event, state, rawText) {
  const invocation = parseCommandText(rawText, {
    aliases: {
      "/drop-memories": "/drop_memories",
      "/fill-access": "/full_access",
    },
  });
  if (!invocation) {
    return false;
  }
  const normalizedCommand = invocation.name;
  const entry = qqCommandHandlers.get(normalizedCommand);
  if (entry) {
    if (entry.requiresSharedSession && !(await ensureSharedSessionBound(event, state))) {
      return true;
    }
    await entry.handler({ event, state, invocation, entry });
    return true;
  }
  const hint = suggestSharedCommandName(normalizedCommand, "qq", ["/status"]);
  await replySafe(event, `Unknown command: ${normalizedCommand}.${hint}\nUse /help to list commands.`);
  return true;
}

async function forwardMessage(event, state, rawText) {
  try {
    await syncPreferredSharedSession(state);
  } catch (error) {
    logLine("WARN", "shared session sync failed before forwarding", {
      sessionId: state.sessionId,
      error: String(error)
    });
  }
  const params = new URLSearchParams();
  params.set("message", rawText);
  params.set("workspace_dir", state.workspaceDir);
  params.set("dry_run", String(Boolean(state.dryRun)));
  params.set("surface", "qq");
  params.set("channel_type", "qq");
  params.set("conversation_id", state.conversationId);
  const senderId = String(event.author?.id || event.user_id || "").trim();
  if (senderId) {
    params.set("sender_id", senderId);
  }
  if (state.sessionId) {
    params.set("session_id", state.sessionId);
  } else {
    params.set("session_title_hint", qqbotName);
  }

  const response = await gatewayRequest(`/api/v1/agent/chat/stream?${params.toString()}`, {
    headers: {
      Accept: "text/event-stream"
    }
  });

  let accumulatedReply = "";
  const notifiedApprovalTokens = new Set();

  for await (const item of iterateSseEvents(response)) {
    const eventType = cleanText(item?.event).toLowerCase() || "message";
    const data = item?.data && typeof item.data === "object" ? item.data : {};
    if (eventType === "session") {
      const sessionId = safeText(data?.session_id);
      if (sessionId) {
        state.sessionId = sessionId;
      }
      const workspaceDir = safeText(data?.workspace_dir);
      if (workspaceDir) {
        state.workspaceDir = workspaceDir;
      }
      continue;
    }
    if (eventType === "approval_requested") {
      const token = safeText(data?.token);
      if (token && !notifiedApprovalTokens.has(token)) {
        notifiedApprovalTokens.add(token);
        await replySafe(event, formatApprovalRequestedMessage(data, state));
      }
      continue;
    }
    if (eventType === "approval_resolved" || eventType === "status" || eventType === "activity" || eventType === "heartbeat") {
      continue;
    }
    if (eventType === "delta") {
      accumulatedReply += String(data?.chunk || "");
      continue;
    }
    if (eventType === "error") {
      throw new Error(safeText(data?.message) || "Agent stream failed.");
    }
    if (eventType === "done") {
      const sessionId = safeText(data?.session_id);
      if (sessionId) {
        state.sessionId = sessionId;
      }
      const finalReply = String(data?.reply || "").trim() || accumulatedReply.trim() || "(empty reply)";
      await replySafe(event, finalReply);
      return;
    }
  }

  const fallbackReply = accumulatedReply.trim();
  if (fallbackReply) {
    await replySafe(event, fallbackReply);
    return;
  }
  throw new Error("No reply received from Mini-Agent stream.");
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

  const content = limitInboundMessage(String(event.content || "").trim(), maxMessageChars);
  if (!content) {
    return;
  }

  const state = getConversationBindingState(event);
  logLine("INFO", "Incoming message", {
    eventName,
    eventId,
    conversationId: state.conversationId,
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
      await replySafe(event, `Handle message failed: ${String(error)}`);
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
  gatewayAuth: Boolean(gatewayAuthToken),
  allowedWorkspaceRoots,
  maxMessageChars,
  maxReplyChunkSize,
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





