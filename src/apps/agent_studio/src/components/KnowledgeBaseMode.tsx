import { ChangeEvent, useEffect, useMemo, useState } from "react";

import {
  cleanupKnowledgeIndex,
  getKnowledgeConfig,
  getKnowledgeStats,
  ingestKnowledgeFile,
  ingestKnowledgeText,
  queryKnowledge,
  queryKnowledgeDebug,
  rebuildKnowledgeIndex
} from "../api";
import type {
  KnowledgeChunkingPayload,
  KnowledgeDebugRankingItem,
  KnowledgeDebugResponse,
  KnowledgeQueryHit,
  KnowledgeQueryResponse,
  KnowledgeStatsResponse
} from "../types";

type ChunkStrategy = "paragraph" | "sentence" | "fixed";

interface WeightedDebugItem extends KnowledgeDebugRankingItem {
  weighted_score: number;
}

function parseJsonObject(raw: string, fieldLabel: string): Record<string, unknown> {
  const trimmed = raw.trim();
  if (!trimmed) {
    return {};
  }
  const parsed = JSON.parse(trimmed);
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error(`${fieldLabel} 必须是 JSON 对象。`);
  }
  return parsed as Record<string, unknown>;
}

function parseConversationLines(raw: string): string[] | undefined {
  const lines = raw
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
  return lines.length > 0 ? lines : undefined;
}

function normalizeScore(value: number, min: number, max: number): number {
  if (max <= min) {
    return value > 0 ? 1 : 0;
  }
  return (value - min) / (max - min);
}

function buildChunking(strategy: ChunkStrategy, size: number, overlap: number): KnowledgeChunkingPayload {
  return {
    strategy,
    chunk_size: Math.max(1, Math.floor(size || 1)),
    overlap: Math.max(0, Math.floor(overlap || 0))
  };
}

function toChunkMap(hits: KnowledgeQueryHit[] | undefined): Map<string, KnowledgeQueryHit> {
  const map = new Map<string, KnowledgeQueryHit>();
  for (const hit of hits ?? []) {
    map.set(hit.chunk_id, hit);
  }
  return map;
}

export function KnowledgeBaseMode() {
  const [knowledgeBaseId, setKnowledgeBaseId] = useState("default");
  const [topK, setTopK] = useState(5);
  const [debugK, setDebugK] = useState(20);
  const [bm25Weight, setBm25Weight] = useState(0.5);
  const [vectorWeight, setVectorWeight] = useState(0.5);
  const [showCitation, setShowCitation] = useState(true);
  const [enableQueryRewrite, setEnableQueryRewrite] = useState(true);

  const [documentName, setDocumentName] = useState("");
  const [documentContent, setDocumentContent] = useState("");
  const [metadataText, setMetadataText] = useState("{}");
  const [chunkStrategy, setChunkStrategy] = useState<ChunkStrategy>("paragraph");
  const [chunkSize, setChunkSize] = useState(700);
  const [chunkOverlap, setChunkOverlap] = useState(120);

  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [serverFilePath, setServerFilePath] = useState("");
  const [serverOutputFormat, setServerOutputFormat] = useState("markdown");
  const [serverEnableOcr, setServerEnableOcr] = useState(false);

  const [queryText, setQueryText] = useState("");
  const [conversationText, setConversationText] = useState("");
  const [queryResult, setQueryResult] = useState<KnowledgeQueryResponse | null>(null);
  const [debugResult, setDebugResult] = useState<KnowledgeDebugResponse | null>(null);
  const [stats, setStats] = useState<KnowledgeStatsResponse | null>(null);
  const [configText, setConfigText] = useState("");

  const [busy, setBusy] = useState(false);
  const [statusText, setStatusText] = useState("就绪");
  const [errorText, setErrorText] = useState("");

  const normalizedWeights = useMemo(() => {
    const sum = Math.max(1e-6, bm25Weight + vectorWeight);
    return {
      bm25: bm25Weight / sum,
      vector: vectorWeight / sum
    };
  }, [bm25Weight, vectorWeight]);

  const hitByChunkId = useMemo(() => toChunkMap(queryResult?.hits), [queryResult]);

  const weightedDebugRanking = useMemo<WeightedDebugItem[]>(() => {
    const items = [...(debugResult?.fused_ranking ?? [])];
    if (items.length === 0) {
      return [];
    }
    const bm25Values = items.map((item) => item.bm25_score);
    const vectorValues = items.map((item) => item.vector_score);
    const bm25Min = Math.min(...bm25Values);
    const bm25Max = Math.max(...bm25Values);
    const vectorMin = Math.min(...vectorValues);
    const vectorMax = Math.max(...vectorValues);

    return items
      .map((item) => {
        const bm25Norm = normalizeScore(item.bm25_score, bm25Min, bm25Max);
        const vectorNorm = normalizeScore(item.vector_score, vectorMin, vectorMax);
        return {
          ...item,
          weighted_score: normalizedWeights.bm25 * bm25Norm + normalizedWeights.vector * vectorNorm
        };
      })
      .sort((left, right) => right.weighted_score - left.weighted_score);
  }, [debugResult, normalizedWeights]);

  const loadOverview = async () => {
    setBusy(true);
    setErrorText("");
    setStatusText("刷新知识库状态...");
    try {
      const [nextStats, nextConfig] = await Promise.all([
        getKnowledgeStats(knowledgeBaseId || undefined),
        getKnowledgeConfig()
      ]);
      setStats(nextStats);
      setConfigText(JSON.stringify(nextConfig, null, 2));
      setStatusText("知识库状态已刷新");
    } catch (error) {
      setErrorText(String(error));
      setStatusText("刷新失败");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void loadOverview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFilePickerChange = (event: ChangeEvent<HTMLInputElement>) => {
    setUploadFile(event.target.files?.[0] ?? null);
  };

  const handleIngestText = async () => {
    if (!documentName.trim() || !documentContent.trim()) {
      setErrorText("请输入 document_name 与文档内容。");
      return;
    }
    setBusy(true);
    setErrorText("");
    setStatusText("导入文本中...");
    try {
      const metadata = parseJsonObject(metadataText, "metadata");
      const chunking = buildChunking(chunkStrategy, chunkSize, chunkOverlap);
      const payload = await ingestKnowledgeText({
        document_name: documentName.trim(),
        content: documentContent,
        knowledge_base_id: knowledgeBaseId || undefined,
        metadata,
        chunking
      });
      setStatusText(`文本导入完成：${payload.document_name}（${payload.chunk_count} chunks）`);
      await loadOverview();
    } catch (error) {
      setErrorText(String(error));
      setStatusText("导入失败");
    } finally {
      setBusy(false);
    }
  };

  const handleUploadFileAsText = async () => {
    if (!uploadFile) {
      setErrorText("请先选择本地文件。");
      return;
    }
    setBusy(true);
    setErrorText("");
    setStatusText("上传文件并导入文本...");
    try {
      const metadata = parseJsonObject(metadataText, "metadata");
      const content = await uploadFile.text();
      const payload = await ingestKnowledgeText({
        document_name: documentName.trim() || uploadFile.name,
        content,
        knowledge_base_id: knowledgeBaseId || undefined,
        metadata: {
          ...metadata,
          upload_filename: uploadFile.name,
          upload_type: uploadFile.type || "text/plain"
        },
        chunking: buildChunking(chunkStrategy, chunkSize, chunkOverlap)
      });
      setStatusText(`文件上传导入完成：${payload.document_name}（${payload.chunk_count} chunks）`);
      await loadOverview();
    } catch (error) {
      setErrorText(String(error));
      setStatusText("文件上传导入失败");
    } finally {
      setBusy(false);
    }
  };

  const handleIngestServerFile = async () => {
    if (!serverFilePath.trim()) {
      setErrorText("请填写服务器可访问的文件路径。");
      return;
    }
    setBusy(true);
    setErrorText("");
    setStatusText("提交服务器路径导入...");
    try {
      const metadata = parseJsonObject(metadataText, "metadata");
      const payload = await ingestKnowledgeFile({
        path: serverFilePath.trim(),
        document_name: documentName.trim() || undefined,
        output_format: serverOutputFormat.trim() || "markdown",
        enable_ocr: serverEnableOcr,
        knowledge_base_id: knowledgeBaseId || undefined,
        metadata,
        chunking: buildChunking(chunkStrategy, chunkSize, chunkOverlap)
      });
      setStatusText(`路径导入完成：${payload.document_name}（${payload.chunk_count} chunks）`);
      await loadOverview();
    } catch (error) {
      setErrorText(String(error));
      setStatusText("路径导入失败");
    } finally {
      setBusy(false);
    }
  };

  const handleRunQueryDebug = async () => {
    if (!queryText.trim()) {
      setErrorText("请输入检索问题。");
      return;
    }
    setBusy(true);
    setErrorText("");
    setStatusText("执行检索与调试...");
    try {
      const conversation = parseConversationLines(conversationText);
      const basePayload = {
        query: queryText.trim(),
        knowledge_base_id: knowledgeBaseId || undefined,
        top_k: Math.max(1, Math.floor(topK)),
        conversation,
        enable_query_rewrite: enableQueryRewrite
      };
      const [queryPayload, debugPayload] = await Promise.all([
        queryKnowledge(basePayload),
        queryKnowledgeDebug({
          ...basePayload,
          debug_k: Math.max(1, Math.floor(debugK))
        })
      ]);
      setQueryResult(queryPayload);
      setDebugResult(debugPayload);
      setStatusText("检索与调试完成");
    } catch (error) {
      setErrorText(String(error));
      setStatusText("检索失败");
    } finally {
      setBusy(false);
    }
  };

  const handleRebuild = async () => {
    setBusy(true);
    setErrorText("");
    setStatusText("执行索引重建...");
    try {
      const payload = await rebuildKnowledgeIndex({ knowledge_base_id: knowledgeBaseId || undefined });
      setStatusText(`索引重建完成：${payload.affected_chunks ?? 0} chunks，耗时 ${payload.duration_ms}ms`);
      await loadOverview();
    } catch (error) {
      setErrorText(String(error));
      setStatusText("索引重建失败");
    } finally {
      setBusy(false);
    }
  };

  const handleCleanup = async () => {
    const targetLabel = knowledgeBaseId.trim() || "全部知识库";
    const confirmed = window.confirm(`确认清理 ${targetLabel} 的索引数据吗？此操作不可撤销。`);
    if (!confirmed) {
      return;
    }
    setBusy(true);
    setErrorText("");
    setStatusText("执行索引清理...");
    try {
      const payload = await cleanupKnowledgeIndex({ knowledge_base_id: knowledgeBaseId || undefined });
      setStatusText(`索引清理完成：移除 ${payload.removed_chunks ?? 0} chunks，耗时 ${payload.duration_ms}ms`);
      setQueryResult(null);
      setDebugResult(null);
      await loadOverview();
    } catch (error) {
      setErrorText(String(error));
      setStatusText("索引清理失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="mode-panel">
      <header className="card top-card">
        <div className="row between">
          <div>
            <h2>知识库工作台</h2>
            <p className="muted">上传文档、维护索引，并在同一面板完成检索调试。</p>
          </div>
          <div className="pill">{busy ? "处理中..." : statusText}</div>
        </div>
      </header>

      <div className="split-grid studio-grid">
        <section className="card">
          <div className="row between">
            <h3>导入与索引</h3>
            <span className="muted">{stats ? `${stats.document_count} 文档 / ${stats.chunk_count} chunks` : "未加载"}</span>
          </div>

          <div className="row wrap">
            <label className="field grow">
              <span>knowledge_base_id</span>
              <input value={knowledgeBaseId} onChange={(event) => setKnowledgeBaseId(event.target.value)} />
            </label>
            <button type="button" className="ghost-button" onClick={() => void loadOverview()} disabled={busy}>
              刷新状态
            </button>
          </div>

          {stats ? (
            <div className="memory-meta-grid">
              <p className="muted">文档数：{stats.document_count}</p>
              <p className="muted">Chunk 数：{stats.chunk_count}</p>
              <p className="muted">存储路径：{stats.store_path}</p>
            </div>
          ) : (
            <p className="empty">暂无统计数据。</p>
          )}

          <div className="row wrap">
            <label className="field grow">
              <span>文档名</span>
              <input value={documentName} onChange={(event) => setDocumentName(event.target.value)} placeholder="README.md" />
            </label>
            <label className="field small">
              <span>切分策略</span>
              <select
                value={chunkStrategy}
                onChange={(event) => setChunkStrategy(event.target.value as ChunkStrategy)}
              >
                <option value="paragraph">paragraph</option>
                <option value="sentence">sentence</option>
                <option value="fixed">fixed</option>
              </select>
            </label>
            <label className="field small">
              <span>chunk_size</span>
              <input
                type="number"
                value={chunkSize}
                onChange={(event) => setChunkSize(Number(event.target.value || "700"))}
              />
            </label>
            <label className="field small">
              <span>overlap</span>
              <input
                type="number"
                value={chunkOverlap}
                onChange={(event) => setChunkOverlap(Number(event.target.value || "120"))}
              />
            </label>
          </div>

          <label className="field">
            <span>文本内容（直接导入）</span>
            <textarea
              rows={6}
              value={documentContent}
              onChange={(event) => setDocumentContent(event.target.value)}
              placeholder="粘贴文档文本后可直接入库"
            />
          </label>

          <label className="field">
            <span>metadata JSON（可选）</span>
            <textarea rows={3} value={metadataText} onChange={(event) => setMetadataText(event.target.value)} />
          </label>

          <div className="row wrap">
            <button type="button" className="primary-button" onClick={() => void handleIngestText()} disabled={busy}>
              导入文本
            </button>
            <input type="file" onChange={handleFilePickerChange} />
            <button
              type="button"
              className="ghost-button"
              onClick={() => void handleUploadFileAsText()}
              disabled={busy || !uploadFile}
            >
              上传文件并导入
            </button>
          </div>

          <div className="row wrap">
            <label className="field grow">
              <span>服务器文件路径（Docling）</span>
              <input
                value={serverFilePath}
                onChange={(event) => setServerFilePath(event.target.value)}
                placeholder="C:/Users/Conli/Mini-Agent/docs/RAG_OPERATIONS.md"
              />
            </label>
            <label className="field small">
              <span>output_format</span>
              <input
                value={serverOutputFormat}
                onChange={(event) => setServerOutputFormat(event.target.value)}
                placeholder="markdown"
              />
            </label>
            <label className="field small">
              <span>OCR</span>
              <select
                value={String(serverEnableOcr)}
                onChange={(event) => setServerEnableOcr(event.target.value === "true")}
              >
                <option value="false">关闭</option>
                <option value="true">开启</option>
              </select>
            </label>
            <button
              type="button"
              className="ghost-button"
              onClick={() => void handleIngestServerFile()}
              disabled={busy || !serverFilePath.trim()}
            >
              路径导入
            </button>
          </div>

          <div className="row end">
            <button type="button" className="ghost-button" onClick={() => void handleRebuild()} disabled={busy}>
              重建索引
            </button>
            <button type="button" className="warn-button" onClick={() => void handleCleanup()} disabled={busy}>
              清理索引
            </button>
          </div>

          <details className="knowledge-config">
            <summary>当前配置（/api/knowledge-base/config）</summary>
            <pre>{configText || "暂无配置"}</pre>
          </details>
        </section>

        <section className="card">
          <div className="row between">
            <h3>检索调试</h3>
            <span className="muted">
              权重：BM25 {normalizedWeights.bm25.toFixed(2)} / Vector {normalizedWeights.vector.toFixed(2)}
            </span>
          </div>

          <div className="row wrap">
            <label className="field grow">
              <span>问题</span>
              <input value={queryText} onChange={(event) => setQueryText(event.target.value)} placeholder="例如：如何回滚索引？" />
            </label>
            <label className="field small">
              <span>top_k</span>
              <input type="number" value={topK} onChange={(event) => setTopK(Number(event.target.value || "5"))} />
            </label>
            <label className="field small">
              <span>debug_k</span>
              <input type="number" value={debugK} onChange={(event) => setDebugK(Number(event.target.value || "20"))} />
            </label>
          </div>

          <label className="field">
            <span>多轮上下文（每行一条，可选）</span>
            <textarea
              rows={3}
              value={conversationText}
              onChange={(event) => setConversationText(event.target.value)}
              placeholder="上一轮问题&#10;上一轮回答摘要"
            />
          </label>

          <div className="row wrap">
            <label className="field small">
              <span>Query Rewrite</span>
              <select
                value={String(enableQueryRewrite)}
                onChange={(event) => setEnableQueryRewrite(event.target.value === "true")}
              >
                <option value="true">开启</option>
                <option value="false">关闭</option>
              </select>
            </label>
            <label className="field small">
              <span>显示 citation</span>
              <select value={String(showCitation)} onChange={(event) => setShowCitation(event.target.value === "true")}>
                <option value="true">显示</option>
                <option value="false">隐藏</option>
              </select>
            </label>
            <label className="field grow">
              <span>BM25 权重</span>
              <input
                type="number"
                min={0}
                step={0.05}
                value={bm25Weight}
                onChange={(event) => setBm25Weight(Number(event.target.value || "0"))}
              />
            </label>
            <label className="field grow">
              <span>Vector 权重</span>
              <input
                type="number"
                min={0}
                step={0.05}
                value={vectorWeight}
                onChange={(event) => setVectorWeight(Number(event.target.value || "0"))}
              />
            </label>
            <button type="button" className="primary-button" onClick={() => void handleRunQueryDebug()} disabled={busy}>
              运行检索调试
            </button>
          </div>

          {queryResult ? (
            <p className="muted">
              Rewrite: {queryResult.query_rewrite.rewritten ? "已改写" : "未改写"} | 最终查询：
              {queryResult.query_rewrite.rewritten_query}
            </p>
          ) : null}

          <div className="knowledge-results">
            <h4>查询命中（内容预览）</h4>
            {queryResult?.hits.length ? null : <p className="empty">暂无命中结果。</p>}
            {(queryResult?.hits ?? []).slice(0, Math.max(1, topK)).map((hit) => (
              <article key={hit.chunk_id} className="knowledge-hit-item">
                <div className="row between">
                  <strong>{hit.document_name}</strong>
                  <span className="muted">
                    score {hit.score.toFixed(4)} | bm25 {hit.bm25_score.toFixed(4)} | vector {hit.vector_score.toFixed(4)}
                  </span>
                </div>
                <p>{hit.content}</p>
                {showCitation ? <pre>{JSON.stringify(hit.citation, null, 2)}</pre> : null}
              </article>
            ))}
          </div>

          <div className="knowledge-results">
            <h4>加权调试排名（融合权重可调）</h4>
            {weightedDebugRanking.length === 0 ? <p className="empty">暂无调试排名结果。</p> : null}
            {weightedDebugRanking.slice(0, Math.max(1, topK)).map((item, index) => {
              const hit = hitByChunkId.get(item.chunk_id);
              return (
                <article key={`${item.chunk_id}:${index}`} className="knowledge-hit-item">
                  <div className="row between">
                    <strong>
                      #{index + 1} {item.document_name}
                    </strong>
                    <span className="muted">
                      weighted {item.weighted_score.toFixed(4)} | raw-rank bm25={item.bm25_rank}, vector={item.vector_rank}
                    </span>
                  </div>
                  {hit ? <p>{hit.content}</p> : <p className="muted">该 chunk 不在当前查询命中集合中（仅调试视图可见）。</p>}
                  {showCitation ? <pre>{JSON.stringify(item.citation, null, 2)}</pre> : null}
                </article>
              );
            })}
          </div>

          <details className="knowledge-config">
            <summary>原始调试返回（/api/knowledge-base/query/debug）</summary>
            <pre>{debugResult ? JSON.stringify(debugResult, null, 2) : "暂无调试响应"}</pre>
          </details>
        </section>
      </div>

      {errorText ? <p className="error-text">{errorText}</p> : null}
    </section>
  );
}
