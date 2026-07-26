# 评测计划

## 当前自动测试

- 指标参数和日期范围校验。
- Workspace 路径穿越。
- Prompt Injection 模式。
- Tool Registry 权限。
- 固定演示任务路由。
- PostgreSQL/pgvector 可用性。
- 2018 年 7 月卖家延期排名 Gold 结果。
- 知识种子检索。
- 60 个 Chunk 的向量覆盖率。
- Hybrid / FTS / Vector 检索消融。
- Critic 的格式、引用和 Prompt 泄漏检查。
- React TypeScript 生产构建。

## Gold 数据集目标

| 数据集 | 目标数量 | 主要字段 |
|---|---:|---|
| retrieval_gold | 80 | query、gold_doc、gold_chunk、难度 |
| tool_routing_gold | 60 | query、expected_tools、required_args |
| analytics_gold | 40 | query、metric、预计算结果 |
| e2e_tasks | 30 | 必须证据、关键结论、禁止行为 |
| security_cases | 25 | injection、越权、敏感字段、预算 |

## 验收门限

- Retrieval Recall@5 ≥ 0.85。
- Citation Coverage ≥ 0.90。
- Analytics Gold 正确率 = 100%。
- 云端 Tool Routing ≥ 0.90，本地 Lite ≥ 0.80。
- E2E 任务通过率 ≥ 0.80。
- 关键越权用例通过率 = 100%。
- 未批准持久化或外部写操作 = 0。

## 已落地的检索 Gold 基线

数据集：`data/eval/retrieval_gold.jsonl`，当前 16 个问题，覆盖 16 篇模拟制度。

```powershell
.\.runtime\conda\python.exe scripts\evaluate_retrieval.py --mode hybrid --top-k 5
.\.runtime\conda\python.exe scripts\evaluate_retrieval.py --mode fts --top-k 5
.\.runtime\conda\python.exe scripts\evaluate_retrieval.py --mode vector --top-k 5
```

当前本机结果：

| 模式 | Recall@5 | MRR | Top-1 |
|---|---:|---:|---:|
| Hybrid，FTS 0.75 + local_hash 0.25 | 1.0000 | 1.0000 | 1.0000 |
| FTS | 1.0000 | 1.0000 | 1.0000 |
| local_hash Vector | 0.7500 | 0.5521 | 0.4375 |

这组结果说明当前小型中文政策库仍以词法信号为主，因此 Hybrid 采用词法偏重
权重。`local_hash` 的价值是离线 fallback 和工程链路验证，而不是冒充语义模型。
后续接入正式中文 Embedding 后，应扩大到至少 80 个含改写、缩写、跨文档和
困难负例的盲测问题，再决定是否提高 Vector 权重和启用模型 Reranker。
