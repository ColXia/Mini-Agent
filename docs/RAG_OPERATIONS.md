# 轻量 RAG 运维手册

## 概览

- 存储引擎：本地 JSON Hybrid Store（`BM25 + hash-vector + RRF`）
- 默认存储路径：`workspace/rag/light_hybrid_store.json`
- 核心接口：`/api/knowledge-base/*`

## 配置项

可通过环境变量统一调整：

- `MINI_AGENT_RAG_STORE_PATH`：索引存储文件路径
- `MINI_AGENT_RAG_TOP_K_DEFAULT` / `MINI_AGENT_RAG_TOP_K_MAX`
- `MINI_AGENT_RAG_DEBUG_K_DEFAULT` / `MINI_AGENT_RAG_DEBUG_K_MAX`
- `MINI_AGENT_RAG_RRF_K`：融合参数
- `MINI_AGENT_RAG_MAX_CANDIDATES`：查询候选上限（性能护栏）
- `MINI_AGENT_RAG_CHUNK_SIZE` / `MINI_AGENT_RAG_CHUNK_OVERLAP`
- `MINI_AGENT_RAG_CHUNK_STRATEGY`：`paragraph|sentence|fixed`
- `MINI_AGENT_RAG_INGEST_MAX_CHARS`：单次 ingest 内容字符上限

运行时可通过接口查看生效配置：

```bash
GET /api/knowledge-base/config
```

## 常用流程

### 1) 导入与查询

- 文本导入：`POST /api/knowledge-base/ingest`
- 文件导入：`POST /api/knowledge-base/ingest/file`
- 异步 ingest 作业：`POST /api/knowledge-base/ingest/jobs`
- 作业状态：`GET /api/knowledge-base/ingest/jobs/{job_id}`
- 失败重试：`POST /api/knowledge-base/ingest/jobs/{job_id}/retry`
- 查询：`POST /api/knowledge-base/query`
- 调试查询：`POST /api/knowledge-base/query/debug`

### 2) 重建索引

当需要刷新 token/vector 索引时：

```bash
POST /api/knowledge-base/admin/rebuild
```

请求体可选：

```json
{"knowledge_base_id": "docs"}
```

返回：`affected_chunks`、`affected_documents`、`duration_ms`。

### 3) 清理索引

清理指定知识库：

```bash
DELETE /api/knowledge-base/admin/cleanup
```

请求体：

```json
{"knowledge_base_id": "docs"}
```

不传 `knowledge_base_id` 时会清空全部索引。

## 回滚建议

- 回滚最稳妥方式：备份并替换 `MINI_AGENT_RAG_STORE_PATH` 对应 JSON 文件。
- 重建类问题：优先执行 `admin/rebuild`，再通过 `query/debug` 对比分项分数。
- 清理误操作：用最近备份恢复索引文件，然后重启服务。

## 快速排障

- 查询无结果：先看 `GET /api/knowledge-base/stats` 的 `chunk_count` 是否为 0。
- 结果质量异常：调用 `POST /api/knowledge-base/query/debug` 检查 BM25/向量/RRF 排序。
- ingest 失败：检查是否触发 `MINI_AGENT_RAG_INGEST_MAX_CHARS` 限制。
- 参数错误：400 响应会返回具体字段约束信息。

## 离线评测

可用脚本进行 Top-k 命中与 citation 覆盖率评估：

```bash
python scripts/rag_offline_eval.py --store workspace/rag/light_hybrid_store.json --dataset path/to/eval.jsonl --top-k 5
```

输出包含：`topk_hit_rate`、`citation_coverage`、逐 case 结果。

## Agent 接入模式

- 运行时原生工具：`knowledge_base_query`
- 该工具直接读取内置轻量 RAG store，不再经过旧 wrapper
- 默认策略：
  - `tools.enable_knowledge_base: true`
- 含义：
  - 只提供“显式 KB tool”，agent 需要时自主调用
  - 不再提供内置被动 prepared-context 注入实现
