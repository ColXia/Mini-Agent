import { useEffect, useMemo, useState } from "react";

import {
  createStudioProvider,
  deleteStudioProvider,
  getStudioMemoryDaily,
  getStudioMemorySummary,
  getStudioProviderHealth,
  getStudioRuntimeDiagnostics,
  listStudioProviders,
  searchStudioMemory,
  updateStudioProvider
} from "../api";
import type {
  StudioMemoryDailyResponse,
  StudioMemoryNote,
  StudioMemorySummary,
  StudioProviderHealth,
  StudioProviderPayload,
  StudioProviderSummary,
  StudioRuntimeDiagnostics
} from "../types";

const EMPTY_PROVIDER_FORM: StudioProviderPayload = {
  name: "",
  api_type: "openai",
  api_base: "",
  api_key: "",
  models: [],
  enabled: true,
  priority: 0,
  timeout: 60,
  headers: {}
};

function parseCsv(raw: string): string[] {
  return raw
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

type RuntimeAlertLevel = "healthy" | "watch" | "warning" | "critical";

interface RuntimeAlertSignal {
  key: string;
  label: string;
  value: string;
  level: RuntimeAlertLevel;
  hint: string;
}

interface RuntimeAlertAssessment {
  overall: RuntimeAlertLevel;
  summary: string;
  signals: RuntimeAlertSignal[];
}

const ALERT_PRIORITY: Record<RuntimeAlertLevel, number> = {
  healthy: 0,
  watch: 1,
  warning: 2,
  critical: 3
};

function maxAlertLevel(current: RuntimeAlertLevel, candidate: RuntimeAlertLevel): RuntimeAlertLevel {
  return ALERT_PRIORITY[candidate] > ALERT_PRIORITY[current] ? candidate : current;
}

function evaluateRuntimeAlert(runtime: StudioRuntimeDiagnostics): RuntimeAlertAssessment {
  const loadRatio = runtime.max_active_sessions > 0 ? runtime.active_sessions / runtime.max_active_sessions : 0;
  let overall: RuntimeAlertLevel = "healthy";
  const signals: RuntimeAlertSignal[] = [];

  let capacityLevel: RuntimeAlertLevel = "healthy";
  if (loadRatio >= 0.95) {
    capacityLevel = "critical";
  } else if (loadRatio >= 0.8) {
    capacityLevel = "watch";
  }
  overall = maxAlertLevel(overall, capacityLevel);
  signals.push({
    key: "capacity",
    label: "Capacity Pressure",
    value: `${runtime.active_sessions}/${runtime.max_active_sessions} (${(loadRatio * 100).toFixed(1)}%)`,
    level: capacityLevel,
    hint:
      capacityLevel === "critical"
        ? "Near hard limit. Reduce concurrent launches or increase team slots before scale-up."
        : capacityLevel === "watch"
          ? "Approaching limit. Keep an eye on queue saturation in upcoming bursts."
          : "Capacity headroom is healthy."
  });

  let saturationLevel: RuntimeAlertLevel = "healthy";
  if (runtime.team_saturation_rejections >= 5) {
    saturationLevel = "critical";
  } else if (runtime.team_saturation_rejections >= 1) {
    saturationLevel = "warning";
  }
  overall = maxAlertLevel(overall, saturationLevel);
  signals.push({
    key: "saturation",
    label: "Saturation Rejections",
    value: String(runtime.team_saturation_rejections),
    level: saturationLevel,
    hint:
      saturationLevel === "critical"
        ? "Frequent rejections detected. Scale concurrency or smooth request spikes."
        : saturationLevel === "warning"
          ? "Some requests were rejected by team-mode concurrency limits."
          : "No saturation rejections detected."
  });

  let conflictLevel: RuntimeAlertLevel = "healthy";
  if (runtime.team_workspace_conflict_rejections >= 3) {
    conflictLevel = "critical";
  } else if (runtime.team_workspace_conflict_rejections >= 1) {
    conflictLevel = "warning";
  }
  overall = maxAlertLevel(overall, conflictLevel);
  signals.push({
    key: "workspace_conflict",
    label: "Workspace Conflict Rejections",
    value: String(runtime.team_workspace_conflict_rejections),
    level: conflictLevel,
    hint:
      conflictLevel === "critical"
        ? "Repeated same-workspace conflicts. Check session reuse strategy and request routing."
        : conflictLevel === "warning"
          ? "Detected same-workspace conflict rejections. Review caller session_id usage."
          : "No workspace conflicts detected."
  });

  const summary =
    overall === "critical"
      ? "Critical: immediate operator action recommended."
      : overall === "warning"
        ? "Warning: guardrail pressure observed, investigate before rollout expansion."
        : overall === "watch"
          ? "Watch: near capacity threshold, monitor closely."
          : "Healthy: no alert thresholds triggered.";

  return { overall, summary, signals };
}

export function StudioOpsMode() {
  const [catalogPath, setCatalogPath] = useState("");
  const [providers, setProviders] = useState<StudioProviderSummary[]>([]);
  const [selectedProviderId, setSelectedProviderId] = useState("");
  const [providerForm, setProviderForm] = useState<StudioProviderPayload>(EMPTY_PROVIDER_FORM);
  const [providerModelsText, setProviderModelsText] = useState("");
  const [providerHeadersText, setProviderHeadersText] = useState("{}");
  const [providerHealth, setProviderHealth] = useState<StudioProviderHealth | null>(null);
  const [providerError, setProviderError] = useState("");
  const [providerBusy, setProviderBusy] = useState(false);
  const [resolvedCatalogPath, setResolvedCatalogPath] = useState("");

  const [workspaceDir, setWorkspaceDir] = useState("C:/Users/Conli/Mini-Agent");
  const [memorySummary, setMemorySummary] = useState<StudioMemorySummary | null>(null);
  const [memoryQuery, setMemoryQuery] = useState("");
  const [memoryMatches, setMemoryMatches] = useState<StudioMemoryNote[]>([]);
  const [selectedDay, setSelectedDay] = useState("");
  const [dailyView, setDailyView] = useState<StudioMemoryDailyResponse | null>(null);
  const [memoryError, setMemoryError] = useState("");
  const [memoryBusy, setMemoryBusy] = useState(false);
  const [runtimeDiagnostics, setRuntimeDiagnostics] = useState<StudioRuntimeDiagnostics | null>(null);
  const [runtimeError, setRuntimeError] = useState("");
  const [runtimeBusy, setRuntimeBusy] = useState(false);

  const selectedProvider = useMemo(
    () => providers.find((item) => item.id === selectedProviderId) ?? null,
    [providers, selectedProviderId]
  );
  const runtimeAlert = useMemo(
    () => (runtimeDiagnostics ? evaluateRuntimeAlert(runtimeDiagnostics) : null),
    [runtimeDiagnostics]
  );

  const syncFormFromProvider = (provider: StudioProviderSummary | null) => {
    if (!provider) {
      setProviderForm(EMPTY_PROVIDER_FORM);
      setProviderModelsText("");
      setProviderHeadersText("{}");
      setProviderHealth(null);
      return;
    }
    setProviderForm({
      id: provider.id,
      name: provider.name,
      api_type: provider.api_type,
      api_base: provider.api_base,
      api_key: "",
      models: [...provider.models],
      enabled: provider.enabled,
      priority: provider.priority,
      timeout: provider.timeout,
      headers: { ...provider.headers }
    });
    setProviderModelsText(provider.models.join(", "));
    setProviderHeadersText(JSON.stringify(provider.headers, null, 2));
  };

  const loadProviders = async (preferredProviderId?: string) => {
    setProviderBusy(true);
    setProviderError("");
    try {
      const payload = await listStudioProviders(catalogPath || undefined);
      setProviders(payload.items);
      setResolvedCatalogPath(payload.catalog_path);
      const nextSelected =
        preferredProviderId ??
        (payload.items.some((item) => item.id === selectedProviderId)
          ? selectedProviderId
          : payload.items[0]?.id ?? "");
      setSelectedProviderId(nextSelected);
      const provider = payload.items.find((item) => item.id === nextSelected) ?? null;
      syncFormFromProvider(provider);
      if (provider) {
        const health = await getStudioProviderHealth(provider.id, catalogPath || undefined);
        setProviderHealth(health);
      } else {
        setProviderHealth(null);
      }
    } catch (error) {
      setProviderError(String(error));
    } finally {
      setProviderBusy(false);
    }
  };

  const refreshProviderHealth = async (providerId: string) => {
    try {
      const payload = await getStudioProviderHealth(providerId, catalogPath || undefined);
      setProviderHealth(payload);
    } catch (error) {
      setProviderError(String(error));
    }
  };

  const loadMemorySummary = async () => {
    setMemoryBusy(true);
    setMemoryError("");
    try {
      const payload = await getStudioMemorySummary(workspaceDir);
      setMemorySummary(payload);
      if (!selectedDay && payload.daily_files.length > 0) {
        setSelectedDay(payload.daily_files[payload.daily_files.length - 1].replace(".md", ""));
      }
    } catch (error) {
      setMemoryError(String(error));
    } finally {
      setMemoryBusy(false);
    }
  };

  const runMemorySearch = async () => {
    setMemoryBusy(true);
    setMemoryError("");
    try {
      const payload = await searchStudioMemory(memoryQuery, { workspace_dir: workspaceDir, limit: 40 });
      setMemoryMatches(payload.items);
    } catch (error) {
      setMemoryError(String(error));
    } finally {
      setMemoryBusy(false);
    }
  };

  const loadDaily = async (day: string) => {
    setMemoryBusy(true);
    setMemoryError("");
    try {
      const payload = await getStudioMemoryDaily(day, workspaceDir);
      setSelectedDay(day);
      setDailyView(payload);
    } catch (error) {
      setMemoryError(String(error));
    } finally {
      setMemoryBusy(false);
    }
  };

  const loadRuntimeDiagnostics = async () => {
    setRuntimeBusy(true);
    setRuntimeError("");
    try {
      const payload = await getStudioRuntimeDiagnostics();
      setRuntimeDiagnostics(payload);
    } catch (error) {
      setRuntimeError(String(error));
    } finally {
      setRuntimeBusy(false);
    }
  };

  useEffect(() => {
    void loadProviders();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void loadMemorySummary();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void loadRuntimeDiagnostics();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSelectProvider = async (provider: StudioProviderSummary) => {
    setSelectedProviderId(provider.id);
    syncFormFromProvider(provider);
    await refreshProviderHealth(provider.id);
  };

  const handleProviderSave = async () => {
    setProviderBusy(true);
    setProviderError("");
    try {
      const parsedHeaders =
        providerHeadersText.trim() === "" ? {} : (JSON.parse(providerHeadersText) as Record<string, string>);
      const payload: StudioProviderPayload = {
        ...providerForm,
        models: parseCsv(providerModelsText),
        headers: parsedHeaders
      };

      if (selectedProviderId) {
        const updated = await updateStudioProvider(selectedProviderId, payload, catalogPath || undefined);
        await loadProviders(updated.id);
      } else {
        const created = await createStudioProvider(payload, catalogPath || undefined);
        await loadProviders(created.id);
      }
    } catch (error) {
      setProviderError(String(error));
    } finally {
      setProviderBusy(false);
    }
  };

  const handleProviderDelete = async () => {
    if (!selectedProviderId) {
      return;
    }
    const confirmed = window.confirm(`确认删除提供方 ${selectedProviderId} 吗？`);
    if (!confirmed) {
      return;
    }
    setProviderBusy(true);
    setProviderError("");
    try {
      await deleteStudioProvider(selectedProviderId, catalogPath || undefined);
      setSelectedProviderId("");
      syncFormFromProvider(null);
      await loadProviders();
    } catch (error) {
      setProviderError(String(error));
    } finally {
      setProviderBusy(false);
    }
  };

  const handleProviderNew = () => {
    setSelectedProviderId("");
    syncFormFromProvider(null);
  };

  return (
    <section className="mode-panel">
      <header className="card top-card">
        <div className="row between">
          <div>
            <h2>运维面板</h2>
            <p className="muted">用于管理模型提供方与记忆数据。</p>
          </div>
          <div className="pill">{providerBusy || memoryBusy || runtimeBusy ? "处理中..." : "就绪"}</div>
        </div>
      </header>

      <div className="split-grid studio-grid">
        <section className="card">
          <div className="row between">
            <h3>提供方管理</h3>
            <span className="muted">{providers.length} 个提供方</span>
          </div>
          <div className="row wrap">
            <label className="field grow">
              <span>目录文件路径（可选）</span>
              <input value={catalogPath} onChange={(event) => setCatalogPath(event.target.value)} />
            </label>
            <button type="button" className="ghost-button" onClick={() => void loadProviders()} disabled={providerBusy}>
              刷新
            </button>
          </div>
          <p className="muted">实际路径：{resolvedCatalogPath || "-"}</p>
          {providerError ? <p className="error-text">{providerError}</p> : null}
          <div className="runtime-diagnostics-box">
            <div className="row between">
              <h4>Runtime Diagnostics</h4>
              <button
                type="button"
                className="ghost-button"
                onClick={() => void loadRuntimeDiagnostics()}
                disabled={runtimeBusy}
              >
                Refresh
              </button>
            </div>
            {runtimeError ? <p className="error-text">{runtimeError}</p> : null}
            {runtimeDiagnostics ? (
              <div className="runtime-diagnostics-grid">
                <p className="muted">
                  mode=<strong>{runtimeDiagnostics.mode}</strong> | active={runtimeDiagnostics.active_sessions} /{" "}
                  {runtimeDiagnostics.max_active_sessions} | available={runtimeDiagnostics.available_session_slots}
                </p>
                <p className="muted">
                  reserved_team_slots={runtimeDiagnostics.reserved_team_slots} | workspace_required=
                  {String(runtimeDiagnostics.workspace_application_required)}
                </p>
                <p className="muted">
                  team_saturation_rejections={runtimeDiagnostics.team_saturation_rejections} |
                  team_workspace_conflict_rejections={runtimeDiagnostics.team_workspace_conflict_rejections}
                </p>
                <p className="muted">main_workspace={runtimeDiagnostics.main_workspace_dir || "-"}</p>
                {runtimeAlert ? (
                  <div className={`runtime-alert-banner ${runtimeAlert.overall}`}>
                    <p>
                      <strong>Alert Policy:</strong> {runtimeAlert.summary}
                    </p>
                    <ul className="runtime-alert-list">
                      {runtimeAlert.signals.map((signal) => (
                        <li key={signal.key}>
                          <span className={`runtime-alert-chip ${signal.level}`}>{signal.level.toUpperCase()}</span>
                          <strong>{signal.label}</strong>
                          <span>{signal.value}</span>
                          <span className="muted">{signal.hint}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            ) : (
              <p className="empty">No runtime diagnostics loaded.</p>
            )}
          </div>

          <div className="provider-list-scroll">
            {providers.length === 0 ? <p className="empty">暂无提供方，请先创建。</p> : null}
            {providers.map((provider) => (
              <button
                type="button"
                key={provider.id}
                className={`provider-item ${provider.id === selectedProviderId ? "active" : ""}`}
                onClick={() => void handleSelectProvider(provider)}
              >
                <strong>{provider.name}</strong>
                <span>
                  {provider.api_type} | {provider.health_status} | 熔断器 {provider.breaker_state}
                </span>
                <span>{provider.id}</span>
              </button>
            ))}
          </div>

          <div className="row wrap">
            <label className="field grow">
              <span>名称</span>
              <input
                value={providerForm.name}
                onChange={(event) => setProviderForm((prev) => ({ ...prev, name: event.target.value }))}
              />
            </label>
            <label className="field small">
              <span>API 类型</span>
              <select
                value={providerForm.api_type}
                onChange={(event) => setProviderForm((prev) => ({ ...prev, api_type: event.target.value }))}
              >
                <option value="openai">openai</option>
                <option value="anthropic">anthropic</option>
                <option value="gemini">gemini</option>
                <option value="custom">custom</option>
              </select>
            </label>
          </div>

          <div className="row wrap">
            <label className="field grow">
              <span>API 地址</span>
              <input
                value={providerForm.api_base}
                onChange={(event) => setProviderForm((prev) => ({ ...prev, api_base: event.target.value }))}
                placeholder="https://api.openai.com/v1"
              />
            </label>
            <label className="field grow">
              <span>API Key（保存时必填）</span>
              <input
                value={providerForm.api_key}
                onChange={(event) => setProviderForm((prev) => ({ ...prev, api_key: event.target.value }))}
                placeholder={selectedProvider ? "留空将覆盖旧 Key（当前不支持保留）" : "sk-..."}
              />
            </label>
          </div>

          <div className="row wrap">
            <label className="field grow">
              <span>模型列表（逗号分隔）</span>
              <input value={providerModelsText} onChange={(event) => setProviderModelsText(event.target.value)} />
            </label>
            <label className="field small">
              <span>启用状态</span>
              <select
                value={String(providerForm.enabled)}
                onChange={(event) =>
                  setProviderForm((prev) => ({ ...prev, enabled: event.target.value === "true" }))
                }
              >
                <option value="true">启用</option>
                <option value="false">禁用</option>
              </select>
            </label>
            <label className="field small">
              <span>优先级</span>
              <input
                type="number"
                value={providerForm.priority}
                onChange={(event) =>
                  setProviderForm((prev) => ({ ...prev, priority: Number(event.target.value || "0") }))
                }
              />
            </label>
            <label className="field small">
              <span>超时（秒）</span>
              <input
                type="number"
                value={providerForm.timeout}
                onChange={(event) =>
                  setProviderForm((prev) => ({ ...prev, timeout: Number(event.target.value || "60") }))
                }
              />
            </label>
          </div>

          <label className="field">
            <span>请求头 JSON</span>
            <textarea
              rows={3}
              value={providerHeadersText}
              onChange={(event) => setProviderHeadersText(event.target.value)}
              placeholder='{"x-foo":"bar"}'
            />
          </label>

          <div className="row end">
            <button type="button" className="ghost-button" onClick={handleProviderNew} disabled={providerBusy}>
              新建
            </button>
            <button
              type="button"
              className="warn-button"
              onClick={handleProviderDelete}
              disabled={!selectedProviderId || providerBusy}
            >
              删除
            </button>
            <button type="button" className="primary-button" onClick={handleProviderSave} disabled={providerBusy}>
              {selectedProviderId ? "更新" : "创建"}
            </button>
          </div>

          {providerHealth ? (
            <div className="provider-health-box">
              <h4>提供方健康状态</h4>
              <p className="muted">
                状态 {providerHealth.status}，熔断器={providerHealth.breaker_state}，错误率=
                {formatPercent(providerHealth.error_rate)}
              </p>
              <p className="muted">
                请求={providerHealth.total_requests}，成功={providerHealth.total_successes}，失败=
                {providerHealth.total_failures}
              </p>
            </div>
          ) : null}
        </section>

        <section className="card">
          <div className="row between">
            <h3>记忆管理</h3>
            <span className="muted">{memorySummary ? `${memorySummary.notes_count} 条笔记` : "暂无"}</span>
          </div>
          <div className="row wrap">
            <label className="field grow">
              <span>工作目录</span>
              <input value={workspaceDir} onChange={(event) => setWorkspaceDir(event.target.value)} />
            </label>
            <button type="button" className="ghost-button" onClick={() => void loadMemorySummary()} disabled={memoryBusy}>
              刷新
            </button>
          </div>
          {memoryError ? <p className="error-text">{memoryError}</p> : null}

          {memorySummary ? (
            <div className="memory-meta-grid">
              <p className="muted">记忆根目录：{memorySummary.memory_root}</p>
              <p className="muted">长期记忆文件：{memorySummary.long_term_file}</p>
              <p className="muted">每日日志目录：{memorySummary.daily_dir}</p>
              <p className="muted">分类：{memorySummary.categories.join(", ") || "-"}</p>
            </div>
          ) : (
            <p className="empty">暂无记忆摘要数据。</p>
          )}

          <div className="row wrap">
            <label className="field grow">
              <span>搜索关键词</span>
              <input value={memoryQuery} onChange={(event) => setMemoryQuery(event.target.value)} />
            </label>
            <button type="button" className="primary-button" onClick={() => void runMemorySearch()} disabled={memoryBusy}>
              搜索
            </button>
          </div>

          <div className="memory-results">
            {memoryMatches.length === 0 ? <p className="empty">暂无匹配结果。</p> : null}
            {memoryMatches.map((item, index) => (
              <article key={`${item.path}:${index}`} className="memory-item">
                <strong>{item.category}</strong>
                <span>{item.timestamp}</span>
                <small>{item.path}</small>
                <p>{item.content}</p>
              </article>
            ))}
          </div>

          <div className="row wrap daily-header">
            <h4>每日日志</h4>
            <span className="muted">{selectedDay ? `已选择 ${selectedDay}` : "未选择"}</span>
          </div>
          <div className="daily-list-scroll">
            {(memorySummary?.daily_files ?? []).length === 0 ? <p className="empty">暂无每日日志。</p> : null}
            {(memorySummary?.daily_files ?? []).map((filename) => {
              const day = filename.replace(".md", "");
              return (
                <button
                  type="button"
                  key={filename}
                  className={`daily-item ${day === selectedDay ? "active" : ""}`}
                  onClick={() => void loadDaily(day)}
                >
                  {filename}
                </button>
              );
            })}
          </div>

          {dailyView ? (
            <div className="daily-preview">
              <p className="muted">
                {dailyView.path} | {dailyView.note_count} 条笔记
              </p>
              <pre>{dailyView.content}</pre>
            </div>
          ) : (
            <p className="empty">请选择一个日志日期查看详情。</p>
          )}
        </section>
      </div>
    </section>
  );
}
