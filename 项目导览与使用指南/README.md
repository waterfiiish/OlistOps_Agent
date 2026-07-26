# OlistOps Agent 项目导览中心

这里是整个项目的统一入口。无论是第一次接触 Agent 的业务同学、需要运行演示的使用者、准备二次开发的工程师，还是技术面试官，都应从本页选择对应阅读路线。

## 一句话认识项目

OlistOps Agent 是一个完全在本机运行的电商运营分析 Agent。用户用中文提出经营问题，系统将问题转换为受约束的分析计划，通过 PostgreSQL MART 上的确定性工具计算指标，检索运营规则，经过证据门控后再让本地模型组织报告，并完整保存运行节点、工具参数和结果摘要。

它不是一个“让大模型自己写 SQL”的聊天机器人。数字由代码和 SQL 计算，模型主要负责把通过验证的证据整理成人类可读的报告。

## 推荐阅读路线

### 需要一份可直接展示或打印的完整项目报告

1. [项目介绍与技术报告（Word）](项目介绍报告/OlistOps_Agent_项目介绍与技术报告.docx)
2. [项目介绍与技术报告（PDF）](项目介绍报告/OlistOps_Agent_项目介绍与技术报告.pdf)
3. [报告证据、截图与重建说明](项目介绍报告/README.md)

这份 30 页报告使用本机数据库、API、RAG 和 Agent Run 的真实截图与实时数字，
覆盖企业数据怎么看、RAG 怎么用、API 如何连接、工作流如何审计和技术面试追问。

### 第一次了解项目

1. [01_从零认识OlistOps_Agent.md](01_从零认识OlistOps_Agent.md)
2. [03_功能场景与提问手册.md](03_功能场景与提问手册.md)
3. 打开 Web：<http://127.0.0.1:5173>

### 需要安装、启动和实际使用

1. [02_从零安装启动与使用.md](02_从零安装启动与使用.md)
2. [05_运维排错与数据重建.md](05_运维排错与数据重建.md)
3. [06_术语与指标口径.md](06_术语与指标口径.md)

### 需要修改代码或增加能力

1. [04_项目文件地图.md](04_项目文件地图.md)
2. [07_混合RAG与评测指南.md](07_混合RAG与评测指南.md)
3. [技术面试官_项目全细节.md](技术面试官_项目全细节.md)
4. 项目原始架构文档：[../docs/architecture.md](../docs/architecture.md)

### 准备技术面试

直接阅读 [技术面试官_项目全细节.md](技术面试官_项目全细节.md)。该文件覆盖架构选择、API 连接、数据建模、Agent 工作流、RAG、模型网关、安全、测试、性能、局限和高频追问。

## 当前真实能力

当前 Tool Registry 中有 10 个只读工具：

| 能力 | 工具 | 典型问题 |
|---|---|---|
| 销售摘要 | `olist.get_sales_summary` | 订单量、GMV 代理值、客单价、运费占比、评分 |
| 配送分析 | `olist.get_delivery_performance` | 整体、卖家、类别延期率 |
| 经营总览 | `olist.get_operations_overview` | 订单状态、取消与不可用订单 |
| 月度趋势 | `olist.get_monthly_trend` | 订单、GMV、配送、评分的月度变化 |
| 地区履约 | `olist.get_geography_performance` | 客户州的延期率、配送天数、评分 |
| 运费结构 | `olist.get_freight_analysis` | 整体、地区、类别的运费占比 |
| 支付构成 | `olist.get_payment_analysis` | 支付方式、金额占比、分期特征 |
| 评分对比 | `olist.compare_late_vs_on_time_reviews` | 延期与按时订单评分差 |
| 卖家诊断 | `olist.get_seller_diagnostic` | 指定卖家与同行基线 |
| 评论样本 | `olist.search_review_samples` | 匿名低分评论摘录 |

Agent 当前支持的主要意图包括：

- `operations_overview`
- `trend_analysis`
- `delivery_analysis`
- `geography_analysis`
- `freight_analysis`
- `payment_analysis`
- `review_analysis`
- `seller_diagnostic`
- `sales_summary`
- `mixed`

知识库包含 16 篇项目模拟运营制度，共 60 个可检索片段和 60 个 384 维向量。
默认使用 PostgreSQL FTS + pgvector + 加权 RRF 混合检索。模型默认使用
`qwen2.5:3b`，模型不可用或输出未通过 Critic 时自动回退到确定性模板。

## 当前运行地址

| 服务 | 地址 |
|---|---|
| Web UI | <http://127.0.0.1:5173> |
| API | <http://127.0.0.1:8000> |
| OpenAPI / Swagger | <http://127.0.0.1:8000/docs> |
| 健康检查 | <http://127.0.0.1:8000/healthz> |
| Ollama | <http://127.0.0.1:11434> |
| PostgreSQL | `127.0.0.1:55432` |

## 当前实现边界

为了避免把规划写成已完成功能，以下边界必须明确：

- 当前已实现 PostgreSQL FTS、`local_hash` 向量、pgvector cosine 召回和加权 RRF。`local_hash` 是可离线复现的特征哈希，不是语义 Embedding 模型；正式中文 Embedding 与模型 Reranker 仍是升级项。
- 项目介绍报告的 DOCX/PDF 生成与真实证据采集已实现；`app.approvals`、
  `app.artifacts`、`eval.*` 表也已创建，但“每次 Agent 运行自动形成正式交付件”的
  完整审批恢复、产物管理 API 和批量评测平台尚未实现。
- 当前后台任务使用 FastAPI `BackgroundTasks`，适合本地 MVP，不是可跨进程恢复的生产任务队列。
- SSE 会持续推送节点与工具事件；最终答案当前以一个完整的 `assistant.delta` 事件发送，不是逐 Token 流式生成。
- 数据是 2016—2018 年的匿名历史公开数据，不代表当前业务，也不能用于识别个人。
- 当前 API 仅绑定本机回环地址，没有启用正式认证、TLS 和多租户隔离，不应直接暴露到公网。

## 文档维护规则

增加新功能时至少同步更新：

1. 本页的能力表。
2. [03_功能场景与提问手册.md](03_功能场景与提问手册.md)。
3. [04_项目文件地图.md](04_项目文件地图.md)。
4. [技术面试官_项目全细节.md](技术面试官_项目全细节.md)。
5. 对应自动测试与 OpenAPI Schema。
