# OlistOps Agent

基于 Olist 真实匿名电商订单与评论数据的本地履约和客户体验分析 Agent。项目采用确定性指标工具、PostgreSQL/pgvector 知识检索、有限 LangGraph 工作流、证据门控、SSE 和可审计 Trace；本地模型通过 Ollama 运行，模型不可用时自动回退到确定性报告模板。

> 当前阶段：本地可运行的多场景 Agent v0.2。RAW、STAGING、7 个 MART、10 个 Analytics Tools、10 类 Agent 意图、16 篇知识种子、PostgreSQL FTS + pgvector + RRF 混合检索、Critic、检索评测、SSE/Trace API、React 场景界面及项目介绍 DOCX/PDF 均已实现。每次 Agent 运行的审批恢复与正式产物管理、可靠任务队列属于后续增强。

第一次接触项目请从 [项目导览中心](项目导览与使用指南/README.md) 开始；可直接展示和打印的版本见 [项目介绍与技术报告（PDF）](项目导览与使用指南/项目介绍报告/OlistOps_Agent_项目介绍与技术报告.pdf)，技术架构、API 连接、数据口径、面试问答和生产化差距集中在 [技术面试官项目全细节](项目导览与使用指南/技术面试官_项目全细节.md)。

## 真实数据与许可

- 数据集：[Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
- 提供方：Olist
- 数据许可：CC BY-NC-SA 4.0
- 用途：非商业学习与作品集演示
- 范围：约 10 万笔 2016—2018 年匿名订单

`data/raw/` 不应提交到 Git。项目不会提交 Kaggle 凭据，也不会使用匿名历史数据重新识别个人。代码许可与数据许可相互独立；使用数据时必须继续遵守 Olist 数据集许可。

## 已验证的本机配置

- Windows，RTX 4060 8GB，约 32GB RAM
- 项目内 Python 3.12 / PostgreSQL 16.14 / pgvector 0.8.3
- PostgreSQL：`127.0.0.1:55432`
- API：`http://127.0.0.1:8000`
- Web：`http://127.0.0.1:5173`
- Ollama：`http://127.0.0.1:11434`

运行时、数据库、模型、原始数据和日志都保存在本项目目录：

```text
.runtime/           Python、PostgreSQL 与 Ollama 便携运行时
data/postgres/      PostgreSQL 数据目录
data/raw/           Olist 原始 CSV
data/processed/     数据质量报告
models/ollama/      Ollama 模型
workspace/          用户会话和报告产物
```

## 一键初始化

在项目根目录打开 PowerShell：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\bootstrap.ps1
```

该命令会：

1. 在 `.runtime/conda` 创建 Python 3.12 + PostgreSQL 16 + pgvector 环境。
2. 安装 Python 和前端依赖。
3. 初始化并启动项目内 PostgreSQL。
4. 下载 9 份 Olist CSV，导入 RAW/STAGING/MART。
5. 生成 `data/processed/data_quality_report.html`。
6. 导入 16 篇项目模拟政策文档并生成 384 维本地向量。
7. 下载官方便携版 Ollama。

如只需测试数据/API：

```powershell
.\scripts\bootstrap.ps1 -SkipOllama
```

## 启动与停止

首次安装 Ollama 后，先启动服务并拉取本地模型：

```powershell
$env:OLLAMA_MODELS = (Resolve-Path .\models\ollama)
Start-Process -FilePath .\.runtime\ollama\ollama.exe -ArgumentList serve -WindowStyle Hidden
.\.runtime\ollama\ollama.exe pull qwen2.5:3b
```

启动全部服务：

```powershell
.\scripts\start.ps1
```

停止项目内服务：

```powershell
.\scripts\stop.ps1
```

模型尚未下载时，Agent 仍可使用确定性模板完成带指标依据的分析。

## 固定演示任务

```text
分析 2018 年 7 月的配送表现，找出延期率最高且订单量不少于 20
的卖家和商品类别，比较延期订单与按时订单的平均评分，并给出改进建议。
```

系统会把时间范围和最小样本量解析为结构化参数，然后依次执行：

1. 卖家配送表现工具。
2. 商品类别配送表现工具。
3. 延期与按时订单评分对比。
4. 运营政策检索。
5. Evidence Gate。
6. 带口径、样本量、知识引用和限制的报告。

## 多场景能力

除固定配送演示外，Web 场景库和 Agent 还支持：

- 经营总览与订单状态。
- 月度经营趋势。
- 客户州地区履约。
- 整体、地区和类别运费结构。
- 支付方式、金额占比和分期特征。
- 低分评论样本。
- 指定卖家诊断。
- 销售摘要。

Tool Registry 当前注册 10 个 READ 工具，知识库包含 16 篇项目模拟制度、60 个 chunks。

知识检索默认使用 `hybrid` 模式：PostgreSQL FTS/关键词候选与 pgvector
向量候选通过加权 RRF 融合。默认离线 `local_hash` provider 不需要 API Key，
因此从文档入库到向量召回的完整链路可在断网环境运行。它是可复现的工程
fallback，不等同于语义 Embedding 模型；接入正式模型时应在同一 Gold 集上重新
评测并调整权重。

## API

核心端点：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/healthz` | PostgreSQL、pgvector 和 Ollama 状态 |
| GET | `/api/v1/tools` | 10 个工具及其 JSON Schema |
| GET | `/api/v1/knowledge/status` | 文档、Chunk、向量覆盖与 RRF 配置 |
| GET | `/api/v1/knowledge/documents` | 知识文档与入库状态 |
| POST | `/api/v1/knowledge/search` | `hybrid` / `fts` / `vector` 检索调试 |
| POST | `/api/v1/sessions` | 创建会话 |
| POST | `/api/v1/sessions/{id}/messages` | 提交任务并返回 `run_id` |
| GET | `/api/v1/runs/{run_id}/events` | SSE 事件流 |
| GET | `/api/v1/runs/{run_id}/trace` | 节点、工具与事件 Trace |
| POST | `/api/v1/analytics/delivery-performance` | 受约束配送指标 |

另提供经营总览、销售、月度趋势、地区、运费、支付、评论对比、评论样本和卖家诊断等直接 Analytics API，完整列表见 Swagger 和 [从零安装启动与使用](项目导览与使用指南/02_从零安装启动与使用.md)。

OpenAPI 文档：`http://127.0.0.1:8000/docs`

## 数据口径

- 订单量：去重 `order_id`；默认仅统计 `delivered`。
- GMV 代理值：`sum(price)`，不等于会计收入。
- 延期订单：实际送达时间晚于预计送达时间。
- 延期率：延期已送达订单 / 同时存在实际与预计日期的已送达订单。
- 平均延期天数：仅在延期订单上计算。
- 低分评论：`review_score <= 2`。

所有报告必须同时显示过滤条件、样本量和分母。Analytics Tools 只查询 MART，不允许模型对 RAW 任意生成 SQL。

## 开发验证

```powershell
$env:PYTHONNOUSERSITE = '1'
.\.runtime\conda\python.exe -m ruff check .
.\.runtime\conda\python.exe -m mypy apps packages scripts
.\.runtime\conda\python.exe -m pytest
npm run build:web
```

当前为 27 项 pytest；模型端到端验证：

```powershell
.\.runtime\conda\python.exe scripts\smoke_test.py --timeout 180
.\.runtime\conda\python.exe scripts\scenario_smoke_test.py --timeout 180
```

检索 Gold 评测：

```powershell
.\.runtime\conda\python.exe scripts\evaluate_retrieval.py --mode hybrid --top-k 5
```

当前 16 个项目内回归用例的 Hybrid Recall@5、MRR 和 Top-1 均为 `1.0`。
报告写入 `data/processed/retrieval_eval_latest.json`；该小型数据集用于防回归，
不能替代更大规模、盲测和真实用户查询评测。

当前导入行数：

| 表 | 行数 |
|---|---:|
| orders | 99,441 |
| order_items | 112,650 |
| order_payments | 103,886 |
| order_reviews | 99,224 |
| customers | 99,441 |
| geolocation | 1,000,163 |
| products | 32,951 |
| sellers | 3,095 |

## 安全边界

- 工具 allowlist 和 Pydantic 参数校验。
- READ / GENERATE / PERSIST / EXTERNAL_WRITE 权限分级。
- PERSIST 及外部写入不能由当前只读工作流直接执行。
- 检索文档被视为不可信数据，不能修改工具权限。
- Trace 默认保存摘要，不把完整 Prompt、评论原文或密钥写入普通日志。
- Workspace 路径必须位于项目内并拒绝 `../` 穿越。
- 有限节点、工具次数、时间和结果行数预算。

详细资料见 [运行手册](docs/runbook.md)、[架构](docs/architecture.md)、[安全](docs/security.md) 与 [评测计划](docs/evaluation.md)。
