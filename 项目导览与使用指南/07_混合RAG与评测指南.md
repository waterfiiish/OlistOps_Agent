# 混合 RAG、引用与评测指南

本文件从零解释 OlistOps Agent 的知识检索：文档如何变成 Chunk 和向量，用户问题
如何同时走关键词与向量召回，为什么要做 RRF，引用如何进入最终答案，以及怎样
判断 RAG 是否真的有效。

## 1. 当前 RAG 是什么

当前系统是一个可离线运行的 Hybrid RAG：

```text
Markdown 制度
  -> 按标题和段落切 Chunk
  -> 生成 384 维 local_hash 向量
  -> PostgreSQL knowledge.documents / knowledge.chunks
  -> GIN 全文索引 + HNSW pgvector 索引

用户问题
  -> 领域词扩展
  -> FTS/ILIKE 候选
  -> pgvector cosine 候选
  -> Weighted RRF 融合
  -> Top-K
  -> Prompt Injection 扫描
  -> K-001、K-002 引用
  -> Evidence Gate
  -> 模型或确定性模板
  -> Critic
```

核心实现：

- `scripts/build_knowledge.py`：文档切分、入库和向量生成。
- `packages/retrieval/embeddings.py`：离线特征哈希。
- `packages/retrieval/service.py`：FTS、Vector、RRF、检索日志。
- `packages/agent_runtime/workflow.py`：检索节点、证据门控、生成与 Critic。
- `db/migrations/002_hybrid_rag.sql`：`vector(384)`、HNSW 和检索日志。

## 2. 为什么默认使用 local_hash

项目要求本地部署、无需云 API 也能完成演示。`local_hash` 具有以下特点：

- 同一文本每次生成完全相同的向量。
- 不需要下载额外 Embedding 模型。
- 不需要 API Key，不产生外部费用。
- 能验证 pgvector、向量入库、cosine 检索和混合排序的完整工程链路。
- 中英文词和中文二至四字 n-gram 均可进入特征空间。

它的限制也必须明确：它主要表达词形重叠，不理解真正语义。纯向量 Gold 结果明显
弱于 FTS，这正是默认权重设置为 FTS `0.75`、Vector `0.25` 的原因。面试时不应把
它描述成 BGE、Qwen Embedding 或 OpenAI Embedding。

## 3. 文档入库

重新构建知识库：

```powershell
$env:PYTHONNOUSERSITE = '1'
.\.runtime\conda\python.exe scripts\apply_migrations.py
.\.runtime\conda\python.exe scripts\build_knowledge.py
```

成功输出应包含：

```text
Hybrid knowledge baseline ready: 60 chunks, 60 embeddings
```

入库状态为：

```text
embedding -> ready
```

每次构建都会按 `content_hash` 更新文档，删除该文档旧 Chunk，然后重新写入内容、
标题路径、token 估算、向量和 Embedding metadata。`knowledge.ingestion_jobs`
记录本次处理状态。

## 4. 数据库结构与索引

`knowledge.documents` 保存文档级信息：

- 标题、来源类型和来源 URL。
- 内容 SHA-256。
- `embedding` / `ready` 等状态。
- 是否为项目模拟制度。
- Embedding Provider 与维度。

`knowledge.chunks` 保存检索单元：

- `document_id + ordinal` 唯一定位。
- `heading_path` 保留章节上下文。
- `content` 是送给模型的原始证据。
- `search_vector` 是 PostgreSQL 自动生成的 `tsvector`。
- `embedding` 是 `vector(384)`。

索引：

- `ix_chunks_search_vector`：GIN 全文索引。
- `ix_chunks_embedding_hnsw`：HNSW cosine 向量索引。

## 5. 三种检索模式

### hybrid

默认模式，同时运行 FTS 和 Vector 候选，然后使用 Weighted Reciprocal Rank
Fusion：

```text
score =
  0.75 / (60 + fts_rank)
  + 0.25 / (60 + vector_rank)
```

RRF 使用排名而不是直接混合 `ts_rank` 与 cosine score，避免两个分数尺度不同。

### fts

只使用 PostgreSQL `websearch_to_tsquery`、`ts_rank_cd` 和 `ILIKE` 回退。中文连续
文本在 PostgreSQL `simple` parser 下分词能力有限，因此代码还会使用领域词扩展、
中文 n-gram、标题命中数和内容命中数排序。

### vector

只执行：

```sql
1 - (embedding <=> query_embedding)
```

适合消融和检查 pgvector 链路，不是当前 `local_hash` 配置下的推荐生产模式。

## 6. 使用知识 API

查看知识库状态：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/knowledge/status
```

查看文档：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/knowledge/documents
```

直接调试检索：

```powershell
$body = @{
  query = "配送延期和包装检查如何处理？"
  limit = 5
  mode = "hybrid"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/knowledge/search `
  -ContentType "application/json; charset=utf-8" `
  -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

结果会返回：

- `fts_rank`：词法候选排名。
- `vector_rank`：向量候选排名。
- `fts_score` / `vector_score`：原始分数。
- `rrf_score`：融合分数。
- `title_hits` / `lexical_hits`：中文回退命中。
- `potential_injection`：是否命中提示注入模式。
- `excerpt`：证据片段摘要。

## 7. Agent 中如何使用 RAG

除纯销售摘要外，工作流会在 Analytics Tools 之后调用 `retrieve_knowledge`：

1. 用原始用户问题检索最多 5 个 Chunk。
2. 对每个 Chunk 扫描 Prompt Injection。
3. 可疑内容被替换为脱敏占位文本，不能修改系统权限。
4. Evidence Gate 检查结构化指标是否存在。
5. Chunk 以 `K-001` 等编号进入模型上下文。
6. 模型缺少引用时，系统补充引用段。
7. Critic 再检查引用覆盖、引用编号、Markdown 结构和 Prompt 泄漏。
8. Critic 不通过时改用确定性证据模板。

SSE 中新增 `retrieval.completed`，前端实时 Trace 会展示模式、命中数和头部文档。
完整 FTS/Vector 排名保存在 Run Trace 的检索节点摘要中。

## 8. 运行 Gold 评测

默认 Hybrid：

```powershell
.\.runtime\conda\python.exe scripts\evaluate_retrieval.py `
  --mode hybrid `
  --top-k 5
```

消融：

```powershell
.\.runtime\conda\python.exe scripts\evaluate_retrieval.py `
  --mode fts `
  --top-k 5 `
  --output data/processed/retrieval_eval_fts.json

.\.runtime\conda\python.exe scripts\evaluate_retrieval.py `
  --mode vector `
  --top-k 5 `
  --output data/processed/retrieval_eval_vector.json
```

当前 16 条项目内 Gold：

| 模式 | Recall@5 | MRR | Top-1 |
|---|---:|---:|---:|
| Hybrid | 1.0000 | 1.0000 | 1.0000 |
| FTS | 1.0000 | 1.0000 | 1.0000 |
| Vector | 0.7500 | 0.5521 | 0.4375 |

指标解释：

- Recall@5：正确文档是否出现在前 5。
- MRR：第一个正确结果越靠前越好。
- Top-1：第一名是否正确。
- Mean latency：每次检索的平均本机耗时。

这 16 条主要用于 CI 和功能防回归。正式评估至少还需要同义改写、错别字、跨文档
组合、无答案拒答、难负例、真实用户问题以及与入库文档隔离的盲测集。

## 9. 替换正式 Embedding 模型

推荐保持 Embedding Provider 接口和 384 维存储契约，新增例如
`OllamaEmbedding`、`QwenEmbedding` 或 `OpenAICompatibleEmbedding`：

1. 在入库和查询两端使用同一模型及同一归一化。
2. 模型名、版本、维度写入 metadata。
3. 模型切换必须全量重建向量，不能混用向量空间。
4. 重新跑 Hybrid / FTS / Vector 消融。
5. 根据结果调低或调高 Vector 权重。
6. 再评估是否需要 Cross-Encoder Reranker。

如果模型维度不是 384，需要新增数据库迁移并重建 HNSW 索引。

## 10. 生产化仍缺什么

- 真正的中文语义 Embedding Provider。
- Embedding cache 和按内容 Hash 复用。
- PDF、DOCX、XLSX、OCR 和表格 Parent-Child 解析。
- 文档上传、替换、删除和版本 API。
- 用户、部门、文档 ACL。
- 模型 Reranker。
- 无答案与矛盾证据专项拒答。
- 80 条以上检索 Gold 和 LLM-as-judge。
- 搜索日志看板、P95 延迟与失败告警。

这些是下一阶段路线，不应在当前演示中描述为已经实现。
