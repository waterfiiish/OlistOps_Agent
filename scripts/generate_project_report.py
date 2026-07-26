from __future__ import annotations

import argparse
import html
import json
import re
import struct
import subprocess
import time
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = PROJECT_ROOT / "项目导览与使用指南" / "项目介绍报告"
ASSETS_DIR = REPORT_DIR / "assets"
EVIDENCE_PATH = REPORT_DIR / "actual_evidence.json"
HTML_PATH = REPORT_DIR / "OlistOps_Agent_项目介绍与技术报告.html"
DOCX_PATH = REPORT_DIR / "OlistOps_Agent_项目介绍与技术报告.docx"
PDF_PATH = REPORT_DIR / "OlistOps_Agent_项目介绍与技术报告.pdf"
README_PATH = REPORT_DIR / "README.md"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
EDGE_PROFILE = PROJECT_ROOT / ".runtime" / "report-edge-pdf-profile"

FONT_EAST_ASIA = "宋体"
FONT_LATIN = "Times New Roman"
FONT_HALF_POINTS = 21  # 10.5 pt，中文排版中的五号字。
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


@dataclass(slots=True)
class Block:
    kind: str
    text: str = ""
    level: int = 0
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    image: Path | None = None
    caption: str = ""
    items: list[str] = field(default_factory=list)


class Report:
    def __init__(self) -> None:
        self.blocks: list[Block] = []

    def title(self, text: str) -> None:
        self.blocks.append(Block("title", text=text))

    def subtitle(self, text: str) -> None:
        self.blocks.append(Block("subtitle", text=text))

    def heading(self, text: str, level: int = 1) -> None:
        self.blocks.append(Block("heading", text=text, level=level))

    def paragraph(self, text: str) -> None:
        self.blocks.append(Block("paragraph", text=text))

    def note(self, text: str) -> None:
        self.blocks.append(Block("note", text=text))

    def bullets(self, items: list[str]) -> None:
        self.blocks.append(Block("bullets", items=items))

    def numbered(self, items: list[str]) -> None:
        self.blocks.append(Block("numbered", items=items))

    def code(self, text: str) -> None:
        self.blocks.append(Block("code", text=text))

    def table(self, headers: list[str], rows: list[list[Any]]) -> None:
        normalized = [[str(cell) for cell in row] for row in rows]
        self.blocks.append(Block("table", headers=headers, rows=normalized))

    def figure(self, image: str, caption: str) -> None:
        self.blocks.append(
            Block("figure", image=ASSETS_DIR / image, caption=caption)
        )

    def page_break(self) -> None:
        self.blocks.append(Block("page_break"))


def format_count(value: Any) -> str:
    return f"{int(value):,}"


def build_report(evidence: dict[str, Any]) -> Report:
    report = Report()
    captured = datetime.fromisoformat(evidence["captured_at"])
    captured_text = captured.strftime("%Y-%m-%d %H:%M:%S %z")
    db = evidence["database"]
    knowledge = evidence["knowledge"]
    agent = evidence["agent"]
    critic = agent["critic_report"]
    raw = db["raw_counts"]
    marts = db["mart_counts"]

    report.title("OlistOps Agent 项目介绍与技术报告")
    report.subtitle("本地可运行的企业运营分析 Agent · v0.2.0")
    report.subtitle("数据、RAG、API、工作流、部署、审计与技术面试说明")
    report.note(
        "版式约定：正文中文使用宋体五号（10.5 pt）；英文、数字使用 "
        "Times New Roman 10.5 pt。报告内图片均为本机当前项目的真实页面或实时结果截图。"
    )
    report.table(
        ["文档项", "内容"],
        [
            ["项目目录", str(PROJECT_ROOT)],
            ["证据采集时间", captured_text],
            ["实时 Agent Run ID", agent["run_id"]],
            ["实时运行状态", agent["status"]],
            ["数据库", f"PostgreSQL {evidence['health']['database']['version']}"],
            ["报告生成方式", "同一结构化内容生成 DOCX 与 HTML，再由 Edge 打印为 PDF"],
        ],
    )
    report.paragraph(
        "阅读建议：业务或产品人员先看“项目定位、企业数据与典型场景”；开发人员重点看"
        "“系统架构、API、RAG、工作流”；技术面试官可直接查看“实现细节、质量验证、"
        "安全边界与面试问题”。"
    )

    report.page_break()
    report.heading("目录与快速结论", 1)
    report.table(
        ["章节", "主要回答的问题"],
        [
            ["1. 项目定位", "它解决什么问题，当前做到什么程度？"],
            ["2. 企业数据", "用了什么数据，规模多大，怎样查看，怎样保证口径？"],
            ["3. 系统架构", "前端、API、Agent、工具、数据库、模型如何协作？"],
            ["4. Agent 能力", "支持哪些业务问题，如何规划和调用工具？"],
            ["5. RAG", "如何切块、建向量、混合检索、引用和评测？"],
            ["6. API", "客户端如何连接，会话、异步运行、SSE、Trace 怎样使用？"],
            ["7. 真实运行", "一次请求实际走过哪些节点，有哪些可审计证据？"],
            ["8. 质量与安全", "测试、评测、只读约束、注入防护和限制是什么？"],
            ["9. 部署运维", "从零启动、健康检查、重建数据与知识库怎么做？"],
            ["10. 面试说明", "技术取舍、追问与可扩展方向如何回答？"],
        ],
    )
    report.note(
        "快速结论：项目已经具备可运行的 LangGraph 多阶段工作流、10 个受控分析工具、"
        "7 个 MART、PostgreSQL FTS + pgvector + RRF 混合 RAG、Ollama 本地模型、"
        "Critic、SSE 与 Trace。它是完整的本地工程样例，但不是已经具备租户、鉴权、"
        "审批恢复和高可用队列的生产 SaaS。"
    )

    report.page_break()
    report.heading("1. 项目定位与业务价值", 1)
    report.heading("1.1 一句话定位", 2)
    report.paragraph(
        "OlistOps Agent 是一个面向电商运营人员的“证据驱动分析 Agent”。用户用自然语言"
        "提出订单、销售、履约、卖家、评价、支付、区域或运费问题；系统先把问题归类并生成"
        "计划，再调用白名单中的只读分析工具获取结构化指标，同时从企业知识库检索制度和"
        "操作规范，最后合成带证据引用的报告并执行质量审查。"
    )
    report.heading("1.2 为什么不是普通聊天机器人", 2)
    report.table(
        ["普通问答风险", "OlistOps 的工程控制"],
        [
            ["模型凭记忆给数字", "经营数字只能来自参数化 SQL 与 MART 工具结果"],
            ["模型任意生成 SQL", "Agent 无自由 SQL 工具，只能调用注册表中的只读工具"],
            ["建议缺少制度依据", "RAG 检索知识片段，并生成 K-001 等可核对引用"],
            ["执行过程不可追踪", "记录 Run、Step、Tool Call、Event 和 Checkpoint"],
            ["输出格式不稳定", "Evidence Gate + Critic 校验非空、结构、引用覆盖和泄漏"],
            ["外部模型不可用", "Ollama 可本地推理，并保留确定性模板降级路径"],
        ],
    )
    report.heading("1.3 当前实现边界", 2)
    report.bullets(
        [
            "已实现：数据下载与装载、RAW/STAGING/MART、数据质量报告、10 个分析工具、"
            "10 类意图、9 节点工作流、混合 RAG、Critic、REST/SSE/Trace API 和 React UI。",
            "已实现：本地 PostgreSQL 16.14、pgvector、Ollama qwen2.5:3b，以及无需 API Key "
            "的 local_hash 384 维向量回退。",
            "尚未实现为生产级：正式登录鉴权、租户隔离、细粒度文档 ACL、TLS、可靠任务队列、"
            "分布式限流、审批恢复、完整可观测平台和自动扩缩容。",
            "正式业务使用前仍需替换模拟制度文档、接入组织权限与真实 SLA，并由数据责任人确认"
            "指标口径。",
        ]
    )
    report.figure(
        "01_web_home.png",
        "图 1　当前本地 React 场景工作台。截图同时展示数据库、模型、RAG 状态和可提问场景。",
    )

    report.page_break()
    report.heading("2. 使用了什么企业数据，以及数据怎样看", 1)
    report.heading("2.1 数据来源与合规定位", 2)
    report.paragraph(
        "项目使用 Brazilian E-Commerce Public Dataset by Olist（Olist 巴西电商公开数据集）。"
        "它是经过匿名化处理的公开电商交易数据，覆盖订单、订单商品、支付、评价、客户、卖家、"
        "商品、地理位置和品类翻译。项目把它作为“企业级关系数据建模与运营分析”的训练数据，"
        "不代表 Olist 当前生产系统，也不得用于重新识别个人或商户。"
    )
    report.note(
        "重要区分：交易数据是真实公开、已匿名化的数据；data/knowledge_seed 中的制度、SOP 和"
        "报告规范是为本项目构造的模拟企业知识，用于演示 RAG 与证据引用，不应被描述为 Olist "
        "公司的真实内部政策。"
    )
    report.heading("2.2 当前本地数据库的真实规模", 2)
    report.table(
        ["RAW 表", "当前行数", "业务含义"],
        [
            ["raw.customers", format_count(raw["customers"]), "匿名客户与城市/州"],
            ["raw.geolocation", format_count(raw["geolocation"]), "邮编前缀与经纬度"],
            ["raw.orders", format_count(raw["orders"]), "订单状态和关键时间戳"],
            ["raw.order_items", format_count(raw["order_items"]), "订单商品、卖家、价格、运费"],
            ["raw.order_payments", format_count(raw["order_payments"]), "支付方式、分期和金额"],
            ["raw.order_reviews", format_count(raw["order_reviews"]), "评分、标题、文本和时间"],
            ["raw.products", format_count(raw["products"]), "商品品类和物理属性"],
            ["raw.sellers", format_count(raw["sellers"]), "匿名卖家与地区"],
            ["raw.category_translation", format_count(raw["category_translation"]), "品类葡英翻译"],
        ],
    )
    report.paragraph(
        f"当前订单购买时间范围为 {db['date_range']['start_date']} 至 "
        f"{db['date_range']['end_date']}。这是本次报告直接查询 PostgreSQL 得出的范围；"
        "不是手工写入报告的静态数字。"
    )
    report.figure(
        "06_data_actual.png",
        "图 2　当前 PostgreSQL 实例的 RAW 与 MART 行数实时快照。",
    )

    report.page_break()
    report.heading("2.3 RAW、STAGING、MART 三层怎样分工", 2)
    report.table(
        ["层", "职责", "代表对象", "为什么这样设计"],
        [
            [
                "RAW",
                "保留源 CSV 的原始字段和粒度，原则上只读",
                "raw.orders、raw.order_items",
                "可追溯、可重复装载，防止清洗逻辑污染源数据",
            ],
            [
                "STAGING",
                "类型转换、时间字段解析、基础清洗和统一命名",
                "staging.stg_orders",
                "隔离脏数据与分析模型，集中定义字段语义",
            ],
            [
                "MART",
                "按订单、卖家、品类、评价、支付和月份预聚合",
                "mart.mart_order_fulfillment 等",
                "避免 Agent 临时拼接复杂 JOIN，稳定粒度和指标口径",
            ],
        ],
    )
    report.table(
        ["MART", "当前行数", "主要用途"],
        [
            ["mart_order_fulfillment", format_count(marts["mart_order_fulfillment"]), "订单履约"],
            [
                "mart_seller_order_fulfillment",
                format_count(marts["mart_seller_order_fulfillment"]),
                "卖家-订单履约，消除多商品重复",
            ],
            [
                "mart_category_order_fulfillment",
                format_count(marts["mart_category_order_fulfillment"]),
                "品类-订单履约",
            ],
            [
                "mart_review_analysis_base",
                format_count(marts["mart_review_analysis_base"]),
                "评价分析",
            ],
            [
                "mart_payment_analysis_base",
                format_count(marts["mart_payment_analysis_base"]),
                "支付分析",
            ],
            [
                "mart_seller_performance_monthly",
                format_count(marts["mart_seller_performance_monthly"]),
                "卖家月度表现",
            ],
            [
                "mart_category_performance_monthly",
                format_count(marts["mart_category_performance_monthly"]),
                "品类月度表现",
            ],
        ],
    )
    report.heading("2.4 数据怎么查看", 2)
    report.numbered(
        [
            "最直观：浏览器打开 data/processed/data_quality_report.html，查看行数、主键重复、"
            "孤儿记录、时间缺失和数值范围。",
            "用 Swagger：访问 http://127.0.0.1:8000/docs，展开 analytics 接口并输入日期、"
            "group_by、top_k 等参数。",
            "用 Agent UI：访问 http://127.0.0.1:5173，用自然语言提问，再打开 Trace 看工具参数"
            "和返回摘要。",
            "用 SQL：只查询 mart 或 staging 层；排查源数据时再对 raw 做只读查询。",
            "用 API：适合 Notebook、BI 中间层或其他服务，通过 JSON 获取结构化结果。",
        ]
    )
    report.code(
        """# PowerShell：直接查看一个 MART 的前 10 行
& ".\\.runtime\\pgsql\\bin\\psql.exe" `
  "postgresql://olistops:olistops@127.0.0.1:55432/olistops" `
  -c "SELECT * FROM mart.mart_order_fulfillment LIMIT 10;"

# 查看本地数据质量报告
Start-Process ".\\data\\processed\\data_quality_report.html\""""
    )
    report.heading("2.5 数据质量怎样解释", 2)
    report.paragraph(
        "质量报告执行确定性检查：核心表行数、业务键重复、跨表孤儿、时间字段完整性和数值范围。"
        "例如 order_reviews 允许同一 order_id 存在多条评价记录，因此报告中 "
        "duplicate_review_ids 不应被机械地当作数据库错误；它需要在 MART 建模时通过明确粒度"
        "处理。真正需要阻断的情况是订单主键重复、订单商品找不到订单、订单客户找不到客户等。"
    )
    report.figure(
        "02_data_quality.png",
        "图 3　实际生成的数据质量报告。核心业务键和跨表完整性检查均有可核对结果。",
    )

    report.page_break()
    report.heading("3. 系统架构与端到端数据流", 1)
    report.heading("3.1 分层架构", 2)
    report.table(
        ["层", "主要技术", "职责"],
        [
            ["交互层", "React + TypeScript + Vite", "场景入口、会话、流式进度、报告与 Trace"],
            ["API 层", "FastAPI + Pydantic", "REST、SSE、参数校验、健康检查、OpenAPI"],
            ["运行层", "RunService + LangGraph", "异步运行、状态机、节点编排、Checkpoint"],
            ["工具层", "Tool Registry + AnalyticsService", "白名单工具、参数 Schema、只读 SQL"],
            ["数据层", "PostgreSQL 16 + SQLAlchemy", "RAW/STAGING/MART、Run/Trace、知识库"],
            ["检索层", "FTS + pgvector + Weighted RRF", "关键词与向量候选融合、引用生成"],
            ["模型层", "Ollama qwen2.5:3b", "基于工具事实与知识证据进行文本合成"],
            ["质量层", "Evidence Gate + Critic", "证据门控、引用覆盖、结构和泄漏检查"],
        ],
    )
    report.heading("3.2 一次问题的调用链", 2)
    report.numbered(
        [
            "浏览器先 POST /api/v1/sessions 创建会话。",
            "用户消息 POST 到 /api/v1/sessions/{session_id}/messages，API 返回 202 和 run_id。",
            "RunService 启动 LangGraph，并把运行状态写入 PostgreSQL。",
            "normalize_request 清理输入；route_intent 识别业务意图；build_plan 选择工具计划。",
            "run_analytics 只调用注册表中的分析工具，SQL 参数由 Pydantic 模型验证。",
            "retrieve_knowledge 执行混合 RAG，得到知识片段和 K-xxx 引用。",
            "validate_evidence 确认数据结论、流程建议和引用之间的对应关系。",
            "synthesize 把结构化指标与知识证据交给本地模型；模型不可用时使用模板降级。",
            "critic 检查输出；finalize 保存最终消息并发布 SSE 事件。",
            "前端通过 /events 接收状态与 token，通过 /trace 查看节点、工具、检索和错误。",
        ]
    )
    report.heading("3.3 为什么采用 LangGraph", 2)
    report.paragraph(
        "项目需要的不是单轮 prompt，而是有固定顺序、可持久化状态、可观测节点和明确失败边界的"
        "业务流程。LangGraph 允许把规范化、路由、规划、分析、检索、证据校验、合成、审查和"
        "结束拆成节点；节点输入输出使用 AgentState 传递。这样能单测每个阶段，也能在 Trace 中"
        "回答“模型为什么得到这个结论”。当前检查点已落 PostgreSQL，但审批恢复和跨进程可靠"
        "任务恢复仍列为后续工作。"
    )
    report.figure(
        "03_swagger_api.png",
        "图 4　当前 FastAPI 自动生成的 OpenAPI/Swagger 页面，展示会话、SSE、"
        "Trace、知识库和分析接口。",
    )

    report.page_break()
    report.heading("4. Agent 具体能做什么", 1)
    report.heading("4.1 十类业务意图", 2)
    report.table(
        ["Intent", "典型问题", "主要工具"],
        [
            [
                "operations_overview",
                "整体订单、销售、履约状态如何？",
                "overview + sales + delivery",
            ],
            ["sales_summary", "某时间段 GMV 代理值、客单价如何？", "get_sales_summary"],
            ["delivery_analysis", "哪些卖家或品类延迟率高？", "get_delivery_performance"],
            ["trend_analysis", "月度订单、销售、履约趋势如何？", "get_monthly_trend"],
            ["seller_diagnostic", "一个卖家的综合表现和评论主题？", "get_seller_diagnostic"],
            ["review_analysis", "延迟与低分是否相关，差评说了什么？", "review tools"],
            ["geography_analysis", "不同州的订单、运费和时效怎样？", "get_geography_performance"],
            ["freight_analysis", "运费占比高的地区/品类有哪些？", "get_freight_analysis"],
            ["payment_analysis", "支付方式、分期和客单价怎样？", "get_payment_analysis"],
            ["mixed", "跨多个域的复合问题", "按计划组合白名单工具"],
        ],
    )
    report.heading("4.2 十个只读 Analytics Tools", 2)
    report.table(
        ["工具名", "作用", "关键输入"],
        [
            ["olist.get_operations_overview", "订单状态和经营总览", "日期范围"],
            ["olist.get_sales_summary", "订单数、销售额代理值、客单价", "日期范围"],
            [
                "olist.get_delivery_performance",
                "延迟率、配送天数、分组排名",
                "日期、group_by、top_k",
            ],
            ["olist.get_monthly_trend", "月度经营与履约趋势", "日期范围"],
            ["olist.get_geography_performance", "客户州/卖家州表现", "日期、维度、top_k"],
            ["olist.get_freight_analysis", "运费及运费占比", "日期、group_by、top_k"],
            ["olist.get_payment_analysis", "支付类型、分期、金额", "日期、top_k"],
            ["olist.compare_late_vs_on_time_reviews", "延迟与按时订单评分对比", "日期范围"],
            ["olist.search_review_samples", "匿名低分评论样本", "日期、筛选、limit"],
            ["olist.get_seller_diagnostic", "卖家多指标诊断", "seller_id、日期"],
        ],
    )
    report.paragraph(
        "工具返回的是结构化 JSON，并带有口径、过滤条件和数据新鲜度信息。模型不参与数值计算；"
        "其职责是解释工具结果、连接知识证据并组织报告。多商品和多卖家订单先在 MART 中聚合到"
        "目标粒度，避免直接 JOIN 明细造成评分或订单数重复。"
    )
    report.heading("4.3 建议从这些问题开始", 2)
    report.bullets(
        [
            "分析 2018 年 7 月的配送表现，找出订单量不少于 20 的高延迟卖家与品类。",
            "比较延迟订单与按时订单的平均评分，并给出有证据的改进建议。",
            "按月查看 2017 年至 2018 年的订单量、销售额代理值、延迟率与平均评分。",
            "分析不同客户州的订单量、平均运费、平均配送天数和延迟率。",
            "检查支付方式和分期数的金额分布，但不要把支付记录金额简单当作公司财务收入。",
        ]
    )

    report.page_break()
    report.heading("5. RAG 到底如何实现、如何使用", 1)
    report.heading("5.1 当前知识库是什么", 2)
    report.paragraph(
        f"当前数据库有 {knowledge['document_count']} 篇项目内模拟知识文档，切分为 "
        f"{knowledge['chunk_count']} 个 Chunk，其中 {knowledge['embedded_chunk_count']} 个"
        "已有向量，覆盖率为 "
        f"{float(knowledge['embedding_coverage']) * 100:.0f}%。内容包括配送异常分级、"
        "卖家复盘 SOP、包装发货检查、指标口径、报告证据规范、评论处理和月度趋势规范等。"
        "文档源文件位于 data/knowledge_seed。"
    )
    report.heading("5.2 入库流水线", 2)
    report.numbered(
        [
            "读取 Markdown 文件，提取标题、来源元数据和正文。",
            "按照 Markdown 标题层级维护 heading_path；以约 600 字符为目标切块，尽量不跨语义段。",
            "对规范化后的文档和 Chunk 计算 SHA-256，用于幂等更新和变更识别。",
            "保存 document、chunk、ordinal、heading_path、token 近似值和 tsvector。",
            "调用 EmbeddingProvider 生成 384 维向量；当前默认是 local_hash。",
            "将向量写入 pgvector 列，并用 HNSW cosine 索引支持近邻搜索。",
            "更新文档状态和 embedding 覆盖率；失败文档保留错误信息，便于重建。",
        ]
    )
    report.heading("5.3 local_hash 是什么，为什么必须说清楚", 2)
    report.paragraph(
        "local_hash 是一个确定性、离线、无 API Key 的特征哈希向量器。它把规范化 token 和"
        "字符 n-gram 哈希到固定维度并归一化，优点是安装即用、结果可重复、单元测试稳定；"
        "缺点是它不是经过语义训练的 Embedding 模型，对同义改写、跨语言和复杂语义的泛化能力"
        "有限。因此本项目把它定位为工程回退和离线演示 provider，而不是声称它等价于主流语义"
        "Embedding。生产化时应替换成经业务语料验证的 embedding 服务，并保留相同 Provider 接口。"
    )
    report.heading("5.4 混合检索流程", 2)
    report.table(
        ["分支", "实现", "擅长", "局限"],
        [
            [
                "FTS/词法",
                "PostgreSQL tsvector + tsquery，并结合查询扩展、词元、n-gram、ILIKE 和标题命中",
                "业务术语、ID、明确关键词、短语",
                "同义表达和隐含语义较弱",
            ],
            [
                "Vector",
                "pgvector cosine，相似度为 1 - cosine distance；HNSW 取候选",
                "弱词面匹配、相似片段",
                "当前 local_hash 的语义能力有限",
            ],
            [
                "Fusion",
                "按 Weighted Reciprocal Rank Fusion 合并两路排名",
                "不要求两路分数同尺度，容错稳定",
                "权重和 k 需要用评测集校准",
            ],
        ],
    )
    report.code(
        """score(d) = 0.75 / (60 + rank_fts(d))
         + 0.25 / (60 + rank_vector(d))

cosine_similarity(d, q) = 1 - (embedding_d <=> embedding_q)

当前默认：fts_weight=0.75，vector_weight=0.25，rrf_k=60"""
    )
    report.paragraph(
        "检索时分别扩大 FTS 和 Vector 候选池，再按上述 RRF 分数排序，最后取 top_k。"
        "词法分支权重较高，是因为当前向量 provider 是 local_hash；如果切换到高质量语义"
        "Embedding，应重新跑 Gold Set 并调整权重。reranker 接口已留出，但当前未启用。"
    )
    report.figure(
        "04_rag_actual.png",
        "图 5　实时 Hybrid RAG 查询：16 篇文档、60/60 向量覆盖，以及每条结果的 "
        "FTS Rank、Vector Rank 与 RRF Score。",
    )

    report.page_break()
    report.heading("5.5 引用、证据门控与注入防护", 2)
    report.bullets(
        [
            "检索结果进入 AgentState 后按顺序分配 K-001、K-002 等引用 ID；报告末尾保留标题和"
            "证据摘录，用户可以回溯到具体 Chunk。",
            "数据结论必须来自 Analytics Tool；知识片段只能支持流程、制度和解释，不得代替数据"
            "证明“某个卖家实际延迟”。",
            "Evidence Gate 检查是否有工具事实、是否有知识证据、引用是否与检索集合一致；"
            "缺少必要证据时应降级或明确声明限制。",
            "知识入库和检索阶段标记潜在 prompt injection；进入模型上下文前清理类似"
            "“忽略系统指令”“泄露密钥”等文本，知识文档始终按不可信数据处理。",
            "Critic 检查非空、Markdown 标题、章节结构、引用覆盖、引用有效性和 prompt 泄漏；"
            "当前真实运行得分为 "
            f"{critic['score']:.1f}，passed={critic['passed']}。",
        ]
    )
    report.heading("5.6 RAG 怎么实际使用", 2)
    report.code(
        """# 查看知识库状态
Invoke-RestMethod http://127.0.0.1:8000/api/v1/knowledge/status

# 直接执行混合检索
$body = @{
  query = "配送延期和包装检查应该如何处理？"
  limit = 5
  mode  = "hybrid"
} | ConvertTo-Json
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/knowledge/search `
  -ContentType "application/json; charset=utf-8" `
  -Body $body

# 修改 data/knowledge_seed 后重建
python scripts/build_knowledge.py

# 运行检索 Gold Set 评测
python scripts/evaluate_retrieval.py"""
    )
    report.heading("5.7 当前检索评测怎么读", 2)
    report.table(
        ["模式", "Recall@5", "MRR", "Top-1", "解释"],
        [
            ["Hybrid", "1.0000", "1.0000", "1.0000", "16 个回归问题均在首位命中期望文档"],
            ["FTS", "1.0000", "1.0000", "1.0000", "模拟知识中的关键词区分度较高"],
            ["Vector", "0.7500", "0.5521", "0.4375", "local_hash 能补充召回，但语义泛化有限"],
        ],
    )
    report.note(
        "这些指标只证明当前 16 条项目内 Gold Case 的回归结果，不代表开放世界或生产语料的"
        "通用准确率。下一步应增加同义改写、否定问题、跨语言、相似政策、无答案、注入文本和"
        "时间版本冲突用例，并报告 Recall@k、nDCG、引用正确率与端到端答案忠实度。"
    )

    report.page_break()
    report.heading("6. API 如何连接", 1)
    report.heading("6.1 接口设计", 2)
    report.table(
        ["方法与路径", "用途", "关键返回"],
        [
            ["GET /healthz", "数据库、模型、RAG 健康状态", "status/database/model/rag"],
            ["POST /api/v1/sessions", "创建会话", "session_id"],
            ["GET /api/v1/sessions/{id}", "查看会话与消息", "session/messages"],
            ["POST /api/v1/sessions/{id}/messages", "提交问题", "HTTP 202 + run_id"],
            ["GET /api/v1/runs/{id}/events", "SSE 进度与文本流", "event/data"],
            ["GET /api/v1/runs/{id}/trace", "审计运行详情", "run/steps/tool_calls/events"],
            ["GET /api/v1/tools", "工具目录与输入 Schema", "tool definitions"],
            ["GET /api/v1/knowledge/status", "知识库状态", "文档/Chunk/向量/RRF"],
            ["GET /api/v1/knowledge/documents", "知识文档列表", "documents"],
            ["POST /api/v1/knowledge/search", "直接检索", "rank/score/excerpt"],
            ["POST /api/v1/analytics/*", "直接调用确定性分析", "结构化指标"],
        ],
    )
    report.heading("6.2 为什么提交消息返回 202", 2)
    report.paragraph(
        "Agent 可能需要多次 SQL、检索和本地模型推理，不能让一个普通 HTTP 请求长期阻塞。"
        "因此消息接口只负责验证输入、创建 Run 并返回 202 Accepted；客户端随后用 run_id 建立"
        "SSE 连接。SSE 比 WebSocket 更适合本项目的单向进度流：浏览器原生支持、代理配置简单、"
        "事件可按类型消费。需要双向人机审批时，再评估 WebSocket 或持久化 command API。"
    )
    report.heading("6.3 完整 PowerShell 调用示例", 2)
    report.code(
        """$base = "http://127.0.0.1:8000"

$session = Invoke-RestMethod -Method Post `
  -Uri "$base/api/v1/sessions" `
  -ContentType "application/json; charset=utf-8" `
  -Body (@{ title = "API 演示" } | ConvertTo-Json)

$accepted = Invoke-RestMethod -Method Post `
  -Uri "$base/api/v1/sessions/$($session.id)/messages" `
  -ContentType "application/json; charset=utf-8" `
  -Body (@{
    content = "分析 2018 年 7 月配送表现并给出证据化建议"
  } | ConvertTo-Json)

$runId = $accepted.run_id
Invoke-RestMethod "$base/api/v1/runs/$runId/trace\""""
    )
    report.heading("6.4 Python 客户端示例", 2)
    report.code(
        '''import time
import httpx

base = "http://127.0.0.1:8000"
with httpx.Client(base_url=base, timeout=60, trust_env=False) as client:
    session = client.post(
        "/api/v1/sessions", json={"title": "Python client"}
    ).json()
    accepted = client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"content": "分析 2018 年 7 月的配送表现"},
    ).json()
    run_id = accepted["run_id"]
    while True:
        trace = client.get(f"/api/v1/runs/{run_id}/trace").json()
        if trace["run"]["status"] in {"completed", "failed"}:
            break
        time.sleep(0.5)
    print(trace["run"]["status"], trace["run"]["intent"])'''
    )
    report.heading("6.5 接入其他企业系统时怎么做", 2)
    report.paragraph(
        "BI、运营门户或 Notebook 可直接调用 analytics 接口获得确定性 JSON；需要自然语言报告时"
        "调用 session/message/events。生产接入应在 API 前增加企业身份提供商、TLS、API Gateway、"
        "租户上下文、速率限制和审计主体；工具层必须根据主体权限过滤数据，RAG 文档检索必须在"
        "SQL 中加入 ACL/tenant 条件，不能只在前端隐藏。"
    )

    report.page_break()
    report.heading("7. 一次真实 Agent 运行的证据", 1)
    report.table(
        ["字段", "本次真实值"],
        [
            ["Run ID", agent["run_id"]],
            ["状态", agent["status"]],
            ["识别意图", agent["intent"]],
            ["模型", agent["model_used"]],
            ["节点数", str(len(agent["nodes"]))],
            ["工具调用数", str(len(agent["tools"]))],
            ["知识引用数", str(agent["retrieval"]["result_count"])],
            ["Critic", f"score={critic['score']}; passed={critic['passed']}"],
        ],
    )
    report.paragraph(
        "本次问题要求分析 2018 年 7 月配送表现、找出高延迟卖家与品类、比较延迟和按时订单评分，"
        "并给出改进建议。实际 Trace 顺序为："
    )
    report.code(" → ".join(agent["nodes"]))
    report.paragraph(
        "实际工具调用为：" + "；".join(agent["tools"]) + "。这些调用参数和结果摘要均保存在"
        " Trace 中。最终报告的经营数字来自 SQL 工具，改进流程由检索到的模拟政策支持。"
    )
    report.note(
        "真实运行也暴露了当前模型表达的一个改进点：模型曾把平均评分差值写成 "
        "“late delivery rate”。Trace 与工具结果使这类语义错误可被发现；后续应把 Critic "
        "从格式/引用检查扩展到单位、指标名和数值一致性检查。报告不把该错误数值作为业务结论。"
    )
    report.figure(
        "05_agent_actual.png",
        "图 6　真实 Agent Run 的节点、模型、Critic、引用和最终报告截图。Run ID "
        "可在本机 Trace API 复核。",
    )

    report.page_break()
    report.heading("8. 实现细节：技术面试官通常会追问什么", 1)
    report.heading("8.1 路由和计划是不是让 LLM 随便决定", 2)
    report.paragraph(
        "不是。当前 route_intent 使用受控规则对业务关键词和组合条件分类，build_plan 用"
        " intent→步骤/工具映射生成计划。这样做牺牲一部分开放性，换取演示环境中的可重复性、"
        "低延迟和低成本。LLM 主要负责最终语言组织。更复杂版本可以让模型生成结构化 Plan，"
        "但必须用 JSON Schema 校验、工具 allowlist、步数上限和策略引擎二次审批。"
    )
    report.heading("8.2 怎样防止模型生成危险 SQL", 2)
    report.bullets(
        [
            "Agent 上下文中没有 execute_sql 工具；只能选择 registry 中注册的十个工具。",
            "每个工具有 Pydantic 输入模型，日期、分组维度、top_k、seller_id 都被类型和枚举约束。",
            "SQL 写在 AnalyticsService 中，业务值通过绑定参数传入；动态标识符只来自代码枚举映射。",
            "工具只读取 STAGING/MART；报告和知识库的写入由独立、明确的应用路径负责。",
            "生产环境还应使用数据库只读角色、statement_timeout、行级安全和资源配额形成纵深防御。",
        ]
    )
    report.heading("8.3 模型和 API 的关系", 2)
    report.paragraph(
        "FastAPI 不把用户文本直接转发给模型。RunService 先执行工作流；AnalyticsService 产生"
        "结构化事实，RetrievalService 产生知识证据，Workflow 再构造受约束 prompt 调用 "
        "ModelGateway。当前 ModelGateway 通过 Ollama 的本地 HTTP API 访问 qwen2.5:3b；"
        "模型列表和健康状态在 /healthz 可见。Gateway 隔离了模型供应商细节，因此可扩展到"
        "兼容 OpenAI API 的企业模型服务，但要增加密钥托管、重试、超时、并发和成本治理。"
    )
    report.heading("8.4 为什么同时使用数据库指标和 RAG", 2)
    report.table(
        ["信息类型", "正确来源", "示例"],
        [
            ["事实与数值", "Analytics Tool / MART", "2018-07 某卖家的订单数和延迟率"],
            ["定义与口径", "代码、SQL、知识文档", "延迟分母、销售额代理值含义"],
            ["操作流程", "RAG 知识", "P1/P2/P3 分级、包装复核步骤"],
            ["自然语言表达", "LLM", "把事实与流程组织为可读报告"],
        ],
    )
    report.paragraph(
        "RAG 不适合回答实时聚合数字，SQL 也不适合承载长篇制度和 SOP。两者分工后，既能得到"
        "可复算的指标，又能给出有制度出处的建议；Evidence Gate 负责防止来源串位。"
    )
    report.heading("8.5 Run、Step、Event、Checkpoint 有什么区别", 2)
    report.table(
        ["对象", "粒度", "用途"],
        [
            ["Run", "一次用户消息的完整执行", "状态、意图、最终结果、错误"],
            ["Step", "一个 LangGraph 节点", "开始/结束、输入输出摘要、耗时"],
            ["Tool Call", "一次工具调用", "工具名、验证后参数、结果摘要、错误"],
            ["Event", "面向客户端的时间序列事件", "SSE 进度、token、完成/失败"],
            ["Checkpoint", "工作流状态快照", "持久化状态与未来恢复基础"],
        ],
    )

    report.page_break()
    report.heading("9. 测试、评测、审计与安全", 1)
    report.heading("9.1 当前验证基线", 2)
    report.table(
        ["检查", "当前结果", "覆盖内容"],
        [
            ["pytest", "27 passed", "工具、工作流、安全、Embedding、数据库集成"],
            ["Ruff", "通过", "Python 静态规范"],
            ["Mypy", "通过", "核心 Python 类型检查"],
            ["Frontend build", "通过", "TypeScript/Vite 生产构建"],
            ["E2E smoke", "2 条场景通过", "API、数据库、模型、RAG、Agent 端到端"],
            ["RAG Gold Set", "Hybrid 三项均 1.0", "16 条项目内检索回归"],
        ],
    )
    report.heading("9.2 关键安全控制", 2)
    report.bullets(
        [
            "输入：Pydantic 校验、长度限制、日期和枚举边界；会话与 Run 使用 UUID。",
            "工具：注册表 allowlist、固定 SQL、绑定参数、动态维度映射、结果行数限制。",
            "数据：RAW 原始层只读约定，Analytics 主要查询 MART；Trace 对敏感字段做摘要/脱敏。",
            "知识：潜在注入标记、上下文清洗、知识视为不可信证据而不是系统指令。",
            "输出：Evidence Gate 与 Critic 校验引用集合、章节、泄漏和非空。",
            "审计：Run/Step/Tool/Event 持久化，可通过 Trace API 复核。",
        ]
    )
    report.heading("9.3 仍需补齐的生产安全", 2)
    report.bullets(
        [
            "OIDC/OAuth2 登录、RBAC/ABAC、租户隔离与数据库行级安全。",
            "文档级与 Chunk 级 ACL，并在检索 SQL 内强制执行。",
            "TLS、反向代理、CORS 白名单、CSRF 策略、速率限制和 WAF。",
            "Secrets Manager、密钥轮换、审计日志不可篡改归档和数据保留策略。",
            "依赖漏洞扫描、SBOM、镜像签名、备份恢复演练和灾难恢复目标。",
            "高风险写操作必须建立独立工具、审批节点、幂等键、补偿动作和最小权限身份。",
        ]
    )
    report.heading("9.4 指标和因果解释的边界", 2)
    report.paragraph(
        "本项目把 item price 聚合作为销售额代理值，不等同于会计收入、到账金额或利润；支付表"
        "可能一单多记录；评价表可能一单多评价；延迟率必须只在同时存在实际与预计送达日期的"
        "订单中计算。观察到“延迟订单评分更低”只能说明相关性，不能单凭该数据证明因果。"
        "所有跨期趋势还要检查首末月是否完整、促销、节假日和数据截断。"
    )

    report.page_break()
    report.heading("10. 从零部署、运行与排错", 1)
    report.heading("10.1 本地组成与端口", 2)
    report.table(
        ["组件", "默认地址", "说明"],
        [
            ["React Web", "http://127.0.0.1:5173", "用户工作台"],
            ["FastAPI", "http://127.0.0.1:8000", "REST/SSE/Swagger"],
            ["PostgreSQL", "127.0.0.1:55432", "业务、知识和审计数据"],
            ["Ollama", "http://127.0.0.1:11434", "本地模型服务"],
        ],
    )
    report.heading("10.2 常用命令", 2)
    report.code(
        """# 第一次部署：安装依赖、初始化 PostgreSQL、下载/装载数据、建 MART 和知识库
powershell -ExecutionPolicy Bypass -File .\\scripts\\bootstrap.ps1

# 日常启动与停止
powershell -ExecutionPolicy Bypass -File .\\scripts\\start.ps1
powershell -ExecutionPolicy Bypass -File .\\scripts\\stop.ps1

# 健康检查
Invoke-RestMethod http://127.0.0.1:8000/healthz

# 单独重建数据与知识
python scripts/load_data.py
python scripts/data_quality_report.py
python scripts/build_knowledge.py

# 验证
python -m pytest
python -m ruff check .
python -m mypy packages apps scripts
npm --prefix apps/web run build"""
    )
    report.heading("10.3 故障定位顺序", 2)
    report.numbered(
        [
            "先查看 /healthz，区分 API、数据库、模型和 RAG 哪一层异常。",
            "检查 .runtime 下的服务日志和 PID 文件，不要只看前端提示。",
            "数据库异常时确认 55432 端口、连接串、迁移版本和 pgvector 扩展。",
            "RAG 无结果时确认 document_count、chunk_count、embedded_chunk_count 和 provider 一致。",
            "Agent 失败时用 run_id 请求 /trace，找到最后一个失败 Step 或 Tool Call。",
            "模型超时但工具成功时，检查 Ollama 模型是否已拉取；必要时验证模板降级路径。",
            "数据指标异常时先确认 MART 粒度和日期边界，再检查 RAW，不要直接修改结果表。",
        ]
    )
    report.heading("10.4 项目目录导航", 2)
    report.table(
        ["目录", "内容"],
        [
            ["apps/api", "FastAPI 入口、Schema、RunService"],
            ["apps/web", "React/TypeScript 前端"],
            ["packages/agent_runtime", "LangGraph 状态、节点和编排"],
            ["packages/analytics", "分析 Schema、SQL 服务和工具"],
            ["packages/retrieval", "Embedding Provider 与混合检索"],
            ["packages/model_gateway", "Ollama 模型适配"],
            ["packages/tools", "工具注册表"],
            ["db", "迁移、STAGING、MART SQL"],
            ["data/knowledge_seed", "模拟企业知识 Markdown"],
            ["scripts", "部署、装载、评测、证据和报告生成"],
            ["tests", "单元与集成测试"],
            ["项目导览与使用指南", "从零指南、RAG 说明、技术面试细节和本报告"],
        ],
    )

    report.page_break()
    report.heading("11. 技术取舍、局限与路线图", 1)
    report.heading("11.1 已做的取舍", 2)
    report.table(
        ["取舍", "当前选择", "原因", "何时升级"],
        [
            ["数据库", "单 PostgreSQL", "业务、向量、审计一体，部署简单", "数据量或并发显著增长"],
            ["向量", "local_hash 384d", "离线可重复、无密钥", "接入真实知识和语义查询"],
            ["融合", "Weighted RRF", "不同分支分数无需校准", "有足够标注数据训练融合器"],
            [
                "编排",
                "确定性路由 + LangGraph",
                "稳定、可测、可追踪",
                "场景开放后引入受控 LLM Planner",
            ],
            ["模型", "Ollama qwen2.5:3b", "本地隐私和低成本", "复杂生成质量或吞吐要求提高"],
            ["异步", "进程内任务 + SSE", "本地样例简单", "多实例和可靠恢复需要队列"],
            ["前端", "场景化 React UI", "降低运营人员提问门槛", "接入企业门户和统一身份"],
        ],
    )
    report.heading("11.2 优先路线图", 2)
    report.numbered(
        [
            "P0：修正指标名称/单位一致性 Critic；为每个数值建立 tool_result 路径和断言。",
            "P0：引入正式语义 Embedding，离线对比 recall、nDCG、延迟和资源成本后再切默认。",
            "P1：支持 PDF/DOCX/XLSX/HTML 解析、元数据、版本、有效期、所有者和文档 ACL。",
            "P1：增加 cross-encoder/LLM reranker，特别处理相似政策和否定查询。",
            "P1：把任务执行迁移到可靠队列，支持重试、取消、幂等和恢复。",
            "P1：加入 OIDC、RBAC/ABAC、租户隔离、RLS 和不可篡改审计。",
            "P2：建立人工审批节点与恢复协议，写操作采用专用服务身份和补偿事务。",
            "P2：建设真实标注集、答案忠实度评测、线上反馈和持续回归看板。",
        ]
    )
    report.heading("11.3 参考开源项目后的吸收方式", 2)
    report.paragraph(
        "项目设计参考了 enterprise-knowledge-rag 对企业知识采集、切块、检索、引用、权限与"
        "评测的关注，也参考了 enterprise-workflow-agent-platform 对工作流、工具治理、"
        "运行审计、检查点和人机协同的分层思想。当前实现选择了适合单机演示的最小闭环，"
        "没有直接复制对方代码，也没有声称已覆盖其全部平台能力。"
    )
    report.table(
        ["参考", "地址", "本项目吸收点"],
        [
            [
                "enterprise-knowledge-rag",
                "https://github.com/smlfy/enterprise-knowledge-rag",
                "企业 RAG 的知识生命周期、混合检索、引用、评测与权限意识",
            ],
            [
                "enterprise-workflow-agent-platform",
                "https://github.com/smlfy/enterprise-workflow-agent-platform",
                "工作流节点、工具注册、运行状态、审计与后续 HITL 路线",
            ],
        ],
    )

    report.page_break()
    report.heading("12. 技术面试问答速查", 1)
    qa = [
        (
            "项目最核心的工程价值是什么？",
            "把自然语言、确定性经营指标、企业知识和可审计工作流连接起来。重点不是聊天效果，"
            "而是数字可复算、建议有引用、执行可追踪、边界可治理。",
        ),
        (
            "为什么不用 LLM 直接写 SQL？",
            "生产数据结构复杂，任意 SQL 有注入、越权、性能和口径风险。白名单工具将查询和业务"
            "口径固化，并用参数模型约束输入；开放分析可另建只读沙箱和 SQL 审核器。",
        ),
        (
            "RAG 为什么同时用 FTS 和向量？",
            "FTS 对 ID、术语和精确关键词可靠，向量补充弱词面匹配；RRF 在不校准分数尺度的情况下"
            "融合排名。当前 local_hash 较弱，所以 FTS 权重更高。",
        ),
        (
            "如何证明回答没有幻觉？",
            "不能证明“绝不幻觉”，但能缩小和暴露风险：数值仅来自工具、知识引用可回溯、"
            "Evidence Gate 控制来源、Critic 检查引用，Trace 保存实际调用。下一步增加数值一致性"
            "校验和答案忠实度评测。",
        ),
        (
            "pgvector 的索引怎么选？",
            "当前使用 HNSW cosine，适合读多写少、查询延迟优先的小型知识库；规模扩大后应评估"
            "ef_search、m、ef_construction、内存、召回和构建时间，也可对比 IVFFlat。",
        ),
        (
            "SSE 与 WebSocket 如何取舍？",
            "当前主要是服务器向浏览器推送运行进度和文本，SSE 更简单。需要实时双向审批、协作"
            "控制或高频二进制通信时再使用 WebSocket。",
        ),
        (
            "怎样扩展一个新业务场景？",
            "定义指标口径和 MART；实现 Pydantic 输入与 AnalyticsService 查询；注册工具；加入"
            "意图路由和计划；补知识文档；增加单元、集成、E2E 与检索评测；最后更新 UI 和文档。",
        ),
        (
            "为什么 Gold Set 结果为 1.0 仍不能说 RAG 完美？",
            "只有 16 条、且来自项目模拟文档，存在样本小和关键词明显的问题。它适合回归，不足以"
            "估计生产泛化。需要更大、盲测、含 hard negative 与无答案的集合。",
        ),
        (
            "如何做企业级权限？",
            "身份在 API 入口解析为主体和租户；工具查询强制 tenant/RLS；知识文档和 Chunk 存 ACL；"
            "检索 SQL 先过滤权限再排序；审计记录主体、目的、数据范围和导出。",
        ),
        (
            "一次运行失败怎样排查？",
            "从 run_id 的 Trace 定位失败节点，再看 Tool Call 参数、数据库/模型/RAG 健康和服务"
            "日志。结构化 Step/Event 比只看最终错误更快找到边界。",
        ),
    ]
    for question, answer in qa:
        report.heading(question, 2)
        report.paragraph(answer)

    report.page_break()
    report.heading("附录 A　可复核文件与命令", 1)
    report.table(
        ["证据/文档", "本地路径"],
        [
            ["原始实时证据 JSON", "项目导览与使用指南/项目介绍报告/actual_evidence.json"],
            ["六张真实截图", "项目导览与使用指南/项目介绍报告/assets"],
            ["从零导览", "项目导览与使用指南/01_从零认识OlistOps_Agent.md"],
            ["安装使用", "项目导览与使用指南/02_从零安装启动与使用.md"],
            ["RAG 指南", "项目导览与使用指南/07_混合RAG与评测指南.md"],
            ["技术全细节", "项目导览与使用指南/技术面试官_项目全细节.md"],
            ["证据采集脚本", "scripts/capture_report_evidence.py"],
            ["截图脚本", "scripts/capture_report_screenshots.py"],
            ["本报告生成脚本", "scripts/generate_project_report.py"],
        ],
    )
    report.code(
        """# 重新采集真实证据（服务需已启动）
python scripts/capture_report_evidence.py
python scripts/capture_report_screenshots.py

# 重新生成 Word、HTML 和 PDF
python scripts/generate_project_report.py"""
    )
    report.heading("附录 B　术语", 1)
    report.table(
        ["术语", "含义"],
        [
            ["Agent", "能根据目标执行多阶段计划、调用工具并维护状态的软件运行体"],
            ["RAG", "Retrieval-Augmented Generation，检索增强生成"],
            ["FTS", "Full-Text Search，数据库全文检索"],
            ["Embedding", "把文本映射为向量表示的过程"],
            ["pgvector", "PostgreSQL 向量类型、距离运算与索引扩展"],
            ["RRF", "Reciprocal Rank Fusion，倒数排名融合"],
            ["MART", "面向稳定分析口径设计的数据集市"],
            ["SSE", "Server-Sent Events，服务器单向事件流"],
            ["Evidence Gate", "在生成前检查事实与知识证据是否充分的门控"],
            ["Critic", "在输出后执行结构、引用和安全检查的审查节点"],
            ["HITL", "Human in the Loop，人机协同与审批"],
        ],
    )
    report.note(
        "本报告截至上述证据采集时间反映本地 v0.2.0 实现。代码、数据或配置变化后，应重新运行"
        "证据采集、截图和报告生成脚本，以保证数字与截图继续对应当前系统。"
    )
    return report


def render_html(report: Report, output: Path) -> None:
    parts: list[str] = []
    for block in report.blocks:
        if block.kind == "title":
            parts.append(f'<h1 class="document-title">{html.escape(block.text)}</h1>')
        elif block.kind == "subtitle":
            parts.append(f'<p class="subtitle">{html.escape(block.text)}</p>')
        elif block.kind == "heading":
            parts.append(
                f'<h{block.level} class="h{block.level}">{html.escape(block.text)}</h{block.level}>'
            )
        elif block.kind == "paragraph":
            parts.append(f"<p>{html.escape(block.text)}</p>")
        elif block.kind == "note":
            parts.append(f'<div class="note">{html.escape(block.text)}</div>')
        elif block.kind in {"bullets", "numbered"}:
            tag = "ul" if block.kind == "bullets" else "ol"
            items = "".join(f"<li>{html.escape(item)}</li>" for item in block.items)
            parts.append(f"<{tag}>{items}</{tag}>")
        elif block.kind == "code":
            parts.append(f"<pre><code>{html.escape(block.text)}</code></pre>")
        elif block.kind == "table":
            head = "".join(f"<th>{html.escape(cell)}</th>" for cell in block.headers)
            body = "".join(
                "<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>"
                for row in block.rows
            )
            parts.append(
                f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'
            )
        elif block.kind == "figure" and block.image is not None:
            relative = block.image.relative_to(output.parent).as_posix()
            parts.append(
                '<figure>'
                f'<img src="{html.escape(relative)}" alt="{html.escape(block.caption)}">'
                f"<figcaption>{html.escape(block.caption)}</figcaption>"
                "</figure>"
            )
        elif block.kind == "page_break":
            parts.append('<div class="page-break"></div>')

    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OlistOps Agent 项目介绍与技术报告</title>
<style>
@page {{
  size: A4;
  margin: 17mm 16mm 18mm 17mm;
}}
* {{
  box-sizing: border-box;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}}
html, body {{
  margin: 0;
  padding: 0;
  color: #15263d;
  background: #ffffff;
  font-family: "{FONT_LATIN}", "{FONT_EAST_ASIA}", serif;
  font-size: 10.5pt;
  line-height: 1.58;
}}
body {{
  max-width: 178mm;
  margin: 0 auto;
}}
p {{
  margin: 0 0 7pt;
  text-align: justify;
  text-indent: 2em;
  orphans: 2;
  widows: 2;
}}
.document-title {{
  margin: 52mm 0 8pt;
  padding: 12pt 0;
  border-top: 2.2pt solid #173b64;
  border-bottom: 2.2pt solid #173b64;
  color: #173b64;
  font-size: 10.5pt;
  line-height: 1.5;
  font-weight: bold;
  text-align: center;
}}
.subtitle {{
  margin: 7pt 0;
  text-indent: 0;
  text-align: center;
}}
h1, h2, h3 {{
  break-after: avoid-page;
  page-break-after: avoid;
  font-size: 10.5pt;
  font-weight: bold;
  line-height: 1.45;
  color: #173b64;
}}
h1 {{
  margin: 0 0 12pt;
  padding: 5pt 7pt;
  border-left: 5pt solid #e05a3f;
  background: #e9eff6;
}}
h2 {{
  margin: 11pt 0 5pt;
  padding-bottom: 2pt;
  border-bottom: 0.6pt solid #a9b7c7;
}}
h3 {{ margin: 9pt 0 4pt; }}
table {{
  width: 100%;
  margin: 7pt 0 10pt;
  border-collapse: collapse;
  break-inside: avoid;
  page-break-inside: avoid;
  font-size: 10.5pt;
}}
thead {{ display: table-header-group; }}
th, td {{
  border: 0.6pt solid #8394a8;
  padding: 4.5pt 5pt;
  text-align: left;
  vertical-align: top;
  overflow-wrap: anywhere;
}}
th {{
  color: #ffffff;
  background: #173b64;
  font-weight: bold;
}}
tr:nth-child(even) td {{ background: #f5f7fa; }}
ul, ol {{
  margin: 4pt 0 9pt 22pt;
  padding: 0;
}}
li {{
  margin: 0 0 4pt;
  text-align: justify;
}}
.note {{
  margin: 8pt 0 10pt;
  padding: 7pt 9pt;
  border-left: 4pt solid #e05a3f;
  background: #fff4e8;
  text-align: justify;
}}
pre {{
  margin: 7pt 0 10pt;
  padding: 8pt 9pt;
  color: #12233b;
  background: #eef2f7;
  border: 0.6pt solid #9eacba;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-family: "{FONT_LATIN}", "{FONT_EAST_ASIA}", serif;
  font-size: 10.5pt;
  line-height: 1.45;
  break-inside: avoid;
}}
figure {{
  margin: 10pt 0 12pt;
  break-inside: avoid;
  page-break-inside: avoid;
}}
figure img {{
  display: block;
  width: 100%;
  max-height: 226mm;
  object-fit: contain;
  border: 0.6pt solid #8394a8;
}}
figcaption {{
  margin-top: 4pt;
  text-align: center;
  font-weight: bold;
}}
.page-break {{
  break-before: page;
  page-break-before: always;
}}
@media screen {{
  body {{
    padding: 18mm 16mm;
    box-shadow: 0 0 18px rgba(0,0,0,.12);
  }}
}}
</style>
</head>
<body>
{''.join(parts)}
</body>
</html>
"""
    output.write_text(document, encoding="utf-8")


def _rpr(*, bold: bool = False, color: str | None = None) -> str:
    bold_xml = "<w:b/><w:bCs/>" if bold else ""
    color_xml = f'<w:color w:val="{color}"/>' if color else ""
    return (
        "<w:rPr>"
        f'<w:rFonts w:ascii="{FONT_LATIN}" w:hAnsi="{FONT_LATIN}" '
        f'w:eastAsia="{FONT_EAST_ASIA}" w:cs="{FONT_LATIN}"/>'
        f"{bold_xml}{color_xml}"
        f'<w:sz w:val="{FONT_HALF_POINTS}"/>'
        f'<w:szCs w:val="{FONT_HALF_POINTS}"/>'
        '<w:lang w:val="en-US" w:eastAsia="zh-CN"/>'
        "</w:rPr>"
    )


def _run(text: str, *, bold: bool = False, color: str | None = None) -> str:
    chunks = text.split("\n")
    content: list[str] = []
    for index, chunk in enumerate(chunks):
        if index:
            content.append("<w:br/>")
        preserve = ' xml:space="preserve"' if chunk[:1].isspace() or chunk[-1:].isspace() else ""
        content.append(f"<w:t{preserve}>{xml_escape(chunk)}</w:t>")
    return f"<w:r>{_rpr(bold=bold, color=color)}{''.join(content)}</w:r>"


def _paragraph(
    text: str,
    *,
    bold: bool = False,
    align: str | None = None,
    first_line: int | None = 420,
    before: int = 0,
    after: int = 120,
    keep_next: bool = False,
    shading: str | None = None,
    border_left: str | None = None,
) -> str:
    props = [
        f'<w:spacing w:before="{before}" w:after="{after}" w:line="360" w:lineRule="auto"/>'
    ]
    if align:
        props.append(f'<w:jc w:val="{align}"/>')
    if first_line is not None:
        props.append(f'<w:ind w:firstLine="{first_line}"/>')
    if keep_next:
        props.append("<w:keepNext/>")
    if shading:
        props.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{shading}"/>')
    if border_left:
        props.append(
            '<w:pBdr><w:left w:val="single" w:sz="24" w:space="6" '
            f'w:color="{border_left}"/></w:pBdr>'
        )
    return f"<w:p><w:pPr>{''.join(props)}</w:pPr>{_run(text, bold=bold)}</w:p>"


def _page_break_paragraph() -> str:
    return f"<w:p><w:r>{_rpr()}<w:br w:type=\"page\"/></w:r></w:p>"


def _table_xml(headers: list[str], rows: list[list[str]]) -> str:
    column_count = max(1, len(headers))
    width = 9280 // column_count

    def cell(value: str, *, header: bool = False) -> str:
        fill = "173B64" if header else "FFFFFF"
        color = "FFFFFF" if header else None
        paragraph = (
            "<w:p><w:pPr>"
            '<w:spacing w:after="40" w:line="300" w:lineRule="auto"/>'
            "</w:pPr>"
            f"{_run(value, bold=header, color=color)}</w:p>"
        )
        return (
            "<w:tc><w:tcPr>"
            f'<w:tcW w:w="{width}" w:type="dxa"/>'
            f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>'
            '<w:vAlign w:val="top"/>'
            "</w:tcPr>"
            f"{paragraph}</w:tc>"
        )

    header_row = (
        "<w:tr><w:trPr><w:tblHeader/></w:trPr>"
        + "".join(cell(value, header=True) for value in headers)
        + "</w:tr>"
    )
    body_rows = "".join(
        "<w:tr>" + "".join(cell(value) for value in row) + "</w:tr>" for row in rows
    )
    return (
        "<w:tbl>"
        "<w:tblPr>"
        '<w:tblW w:w="9280" w:type="dxa"/>'
        '<w:tblLayout w:type="fixed"/>'
        "<w:tblBorders>"
        '<w:top w:val="single" w:sz="4" w:color="8394A8"/>'
        '<w:left w:val="single" w:sz="4" w:color="8394A8"/>'
        '<w:bottom w:val="single" w:sz="4" w:color="8394A8"/>'
        '<w:right w:val="single" w:sz="4" w:color="8394A8"/>'
        '<w:insideH w:val="single" w:sz="4" w:color="B4C0CD"/>'
        '<w:insideV w:val="single" w:sz="4" w:color="B4C0CD"/>'
        "</w:tblBorders>"
        '<w:tblCellMar><w:top w:w="80" w:type="dxa"/>'
        '<w:left w:w="100" w:type="dxa"/><w:bottom w:w="80" w:type="dxa"/>'
        '<w:right w:w="100" w:type="dxa"/></w:tblCellMar>'
        "</w:tblPr>"
        f"{header_row}{body_rows}</w:tbl>"
        '<w:p><w:pPr><w:spacing w:after="60"/></w:pPr></w:p>'
    )


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Only PNG images are supported: {path}")
    return struct.unpack(">II", data[16:24])


def _image_xml(path: Path, rel_id: str, doc_pr_id: int) -> str:
    pixel_width, pixel_height = _png_size(path)
    max_width = int(6.25 * 914400)
    max_height = int(8.6 * 914400)
    width = max_width
    height = int(width * pixel_height / pixel_width)
    if height > max_height:
        height = max_height
        width = int(height * pixel_width / pixel_height)
    return f"""
<w:p>
  <w:pPr><w:jc w:val="center"/><w:spacing w:after="60"/></w:pPr>
  <w:r>{_rpr()}<w:drawing>
    <wp:inline distT="0" distB="0" distL="0" distR="0">
      <wp:extent cx="{width}" cy="{height}"/>
      <wp:effectExtent l="0" t="0" r="0" b="0"/>
      <wp:docPr id="{doc_pr_id}" name="Picture {doc_pr_id}"/>
      <wp:cNvGraphicFramePr>
        <a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
          noChangeAspect="1"/>
      </wp:cNvGraphicFramePr>
      <a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
        <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
          <pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
            <pic:nvPicPr>
              <pic:cNvPr id="{doc_pr_id}" name="{xml_escape(path.name)}"/>
              <pic:cNvPicPr/>
            </pic:nvPicPr>
            <pic:blipFill>
              <a:blip r:embed="{rel_id}"/>
              <a:stretch><a:fillRect/></a:stretch>
            </pic:blipFill>
            <pic:spPr>
              <a:xfrm><a:off x="0" y="0"/><a:ext cx="{width}" cy="{height}"/></a:xfrm>
              <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
            </pic:spPr>
          </pic:pic>
        </a:graphicData>
      </a:graphic>
    </wp:inline>
  </w:drawing></w:r>
</w:p>"""


def _content_types() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Override PartName="/word/document.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/settings.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
  <Override PartName="/word/fontTable.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.fontTable+xml"/>
  <Override PartName="/word/footer1.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>
  <Override PartName="/docProps/core.xml"
    ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml"
    ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""


def _styles_xml() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{WORD_NS}">
  <w:docDefaults>
    <w:rPrDefault>{_rpr()}</w:rPrDefault>
    <w:pPrDefault>
      <w:pPr><w:spacing w:after="120" w:line="360" w:lineRule="auto"/></w:pPr>
    </w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:qFormat/>
    <w:rPr>
      <w:rFonts w:ascii="{FONT_LATIN}" w:hAnsi="{FONT_LATIN}"
        w:eastAsia="{FONT_EAST_ASIA}" w:cs="{FONT_LATIN}"/>
      <w:sz w:val="{FONT_HALF_POINTS}"/>
      <w:szCs w:val="{FONT_HALF_POINTS}"/>
    </w:rPr>
  </w:style>
</w:styles>"""


def _settings_xml() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="{WORD_NS}">
  <w:zoom w:percent="100"/>
  <w:defaultTabStop w:val="420"/>
  <w:characterSpacingControl w:val="doNotCompress"/>
  <w:compat><w:compatSetting w:name="compatibilityMode"
    w:uri="http://schemas.microsoft.com/office/word" w:val="15"/></w:compat>
</w:settings>"""


def _font_table_xml() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:fonts xmlns:w="{WORD_NS}">
  <w:font w:name="{FONT_EAST_ASIA}">
    <w:family w:val="roman"/><w:charset w:val="86"/>
  </w:font>
  <w:font w:name="{FONT_LATIN}">
    <w:family w:val="roman"/><w:charset w:val="00"/>
  </w:font>
</w:fonts>"""


def render_docx(report: Report, output: Path) -> None:
    body: list[str] = []
    relationships: list[str] = [
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>',
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" '
        'Target="settings.xml"/>',
        '<Relationship Id="rId3" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/fontTable" '
        'Target="fontTable.xml"/>',
        '<Relationship Id="rId4" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" '
        'Target="footer1.xml"/>',
    ]
    images: list[tuple[str, Path]] = []
    next_rel = 5
    doc_pr_id = 1

    for block in report.blocks:
        if block.kind == "title":
            body.append(
                _paragraph(
                    block.text,
                    bold=True,
                    align="center",
                    first_line=None,
                    before=1800,
                    after=260,
                    shading="E9EFF6",
                    border_left="173B64",
                )
            )
        elif block.kind == "subtitle":
            body.append(
                _paragraph(
                    block.text,
                    align="center",
                    first_line=None,
                    after=140,
                )
            )
        elif block.kind == "heading":
            before = 180 if block.level == 1 else 120
            shading = "E9EFF6" if block.level == 1 else None
            body.append(
                _paragraph(
                    block.text,
                    bold=True,
                    first_line=None,
                    before=before,
                    after=100,
                    keep_next=True,
                    shading=shading,
                    border_left="E05A3F" if block.level == 1 else None,
                )
            )
        elif block.kind == "paragraph":
            body.append(_paragraph(block.text))
        elif block.kind == "note":
            body.append(
                _paragraph(
                    block.text,
                    first_line=None,
                    before=80,
                    after=120,
                    shading="FFF4E8",
                    border_left="E05A3F",
                )
            )
        elif block.kind in {"bullets", "numbered"}:
            for index, item in enumerate(block.items, 1):
                prefix = "• " if block.kind == "bullets" else f"{index}. "
                body.append(
                    _paragraph(
                        prefix + item,
                        first_line=None,
                        before=0,
                        after=70,
                    )
                )
        elif block.kind == "code":
            body.append(
                _paragraph(
                    block.text,
                    first_line=None,
                    before=80,
                    after=120,
                    shading="EEF2F7",
                )
            )
        elif block.kind == "table":
            body.append(_table_xml(block.headers, block.rows))
        elif block.kind == "figure" and block.image is not None:
            if not block.image.exists():
                raise FileNotFoundError(block.image)
            rel_id = f"rId{next_rel}"
            media_name = f"image{len(images) + 1}.png"
            relationships.append(
                f'<Relationship Id="{rel_id}" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                f'Target="media/{media_name}"/>'
            )
            images.append((media_name, block.image))
            body.append(_image_xml(block.image, rel_id, doc_pr_id))
            body.append(
                _paragraph(
                    block.caption,
                    bold=True,
                    align="center",
                    first_line=None,
                    after=140,
                )
            )
            next_rel += 1
            doc_pr_id += 1
        elif block.kind == "page_break":
            body.append(_page_break_paragraph())

    section = """
<w:sectPr>
  <w:footerReference w:type="default" r:id="rId4"/>
  <w:pgSz w:w="11906" w:h="16838"/>
  <w:pgMar w:top="964" w:right="907" w:bottom="1020" w:left="964"
    w:header="420" w:footer="420" w:gutter="0"/>
  <w:cols w:space="425"/>
  <w:docGrid w:type="lines" w:linePitch="312"/>
</w:sectPr>"""
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document
  xmlns:w="{WORD_NS}"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
  xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
  xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
  xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
  <w:body>{''.join(body)}{section}</w:body>
</w:document>"""
    document_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(relationships)
        + "</Relationships>"
    )
    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    Target="word/document.xml"/>
  <Relationship Id="rId2"
    Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"
    Target="docProps/core.xml"/>
  <Relationship Id="rId3"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties"
    Target="docProps/app.xml"/>
</Relationships>"""
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    core_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties
  xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:dcterms="http://purl.org/dc/terms/"
  xmlns:dcmitype="http://purl.org/dc/dcmitype/"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>OlistOps Agent 项目介绍与技术报告</dc:title>
  <dc:subject>企业运营分析 Agent、数据、RAG、API、工作流与审计</dc:subject>
  <dc:creator>OlistOps Agent Project</dc:creator>
  <cp:lastModifiedBy>OlistOps Agent Project</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>"""
    app_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
  xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>OlistOps Agent Report Generator</Application>
  <AppVersion>0.2.0</AppVersion>
</Properties>"""
    footer_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="{WORD_NS}">
  <w:p><w:pPr><w:jc w:val="center"/></w:pPr>
    {_run("OlistOps Agent 项目介绍与技术报告　·　第 ")}
    <w:fldSimple w:instr="PAGE">{_run("1")}</w:fldSimple>
    {_run(" 页")}
  </w:p>
</w:ftr>"""

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", _content_types())
        package.writestr("_rels/.rels", root_rels)
        package.writestr("docProps/core.xml", core_xml)
        package.writestr("docProps/app.xml", app_xml)
        package.writestr("word/document.xml", document_xml)
        package.writestr("word/_rels/document.xml.rels", document_rels)
        package.writestr("word/styles.xml", _styles_xml())
        package.writestr("word/settings.xml", _settings_xml())
        package.writestr("word/fontTable.xml", _font_table_xml())
        package.writestr("word/footer1.xml", footer_xml)
        for media_name, source in images:
            package.write(source, f"word/media/{media_name}")


def render_pdf(html_path: Path, output: Path) -> None:
    if not EDGE.exists():
        raise FileNotFoundError(f"Microsoft Edge not found: {EDGE}")
    EDGE_PROFILE.mkdir(parents=True, exist_ok=True)
    temporary = PROJECT_ROOT / ".runtime" / "OlistOps_Agent_project_report.pdf"
    temporary.unlink(missing_ok=True)
    command = [
        str(EDGE),
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        f"--user-data-dir={EDGE_PROFILE.resolve()}",
        "--print-to-pdf-no-header",
        f"--print-to-pdf={temporary.resolve()}",
        html_path.resolve().as_uri(),
    ]
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if temporary.exists() and temporary.stat().st_size > 0:
            break
        time.sleep(0.25)
    if result.returncode != 0 or not temporary.exists():
        raise RuntimeError(
            "Edge PDF generation failed: "
            f"exit={result.returncode}; stderr={result.stderr[-2000:]}"
        )
    output.unlink(missing_ok=True)
    temporary.replace(output)


def write_readme() -> None:
    content = """# OlistOps Agent 项目介绍报告

本目录是面向项目展示、技术面试和从零阅读的正式报告包。

## 主要文件

- `OlistOps_Agent_项目介绍与技术报告.docx`：可编辑 Word 版。
- `OlistOps_Agent_项目介绍与技术报告.pdf`：固定版式 PDF 版。
- `OlistOps_Agent_项目介绍与技术报告.html`：PDF 的同源 HTML。
- `actual_evidence.json`：报告生成前从本地 API 与 PostgreSQL 采集的真实证据。
- `assets/`：本地前端、数据质量、Swagger、RAG、Agent Run 和数据库截图。

## 字体

正文中文为宋体五号（10.5 pt），英文与数字为 Times New Roman 10.5 pt。
DOCX 在 OpenXML 的东亚字体和拉丁字体中分别声明；HTML/PDF 使用相同字体回退顺序。

## 重新生成

服务已启动时，在项目根目录执行：

```powershell
python scripts/capture_report_evidence.py
python scripts/capture_report_screenshots.py
python scripts/generate_project_report.py
```

报告会覆盖本目录中同名的 DOCX、HTML 和 PDF。截图和实时数字应在代码、数据或配置变化后重新采集。
"""
    README_PATH.write_text(content, encoding="utf-8")


def validate_docx(path: Path) -> dict[str, Any]:
    required = {
        "[Content_Types].xml",
        "_rels/.rels",
        "word/document.xml",
        "word/_rels/document.xml.rels",
        "word/styles.xml",
        "word/footer1.xml",
    }
    with zipfile.ZipFile(path) as package:
        names = set(package.namelist())
        missing = required - names
        if missing:
            raise ValueError(f"DOCX missing package parts: {sorted(missing)}")
        import xml.etree.ElementTree as element_tree

        for name in [
            "[Content_Types].xml",
            "_rels/.rels",
            "word/document.xml",
            "word/_rels/document.xml.rels",
            "word/styles.xml",
            "word/settings.xml",
            "word/fontTable.xml",
            "word/footer1.xml",
            "docProps/core.xml",
            "docProps/app.xml",
        ]:
            element_tree.fromstring(package.read(name))
        document = package.read("word/document.xml").decode("utf-8")
        media = [name for name in names if name.startswith("word/media/")]
    return {
        "media_count": len(media),
        "east_asia_font": FONT_EAST_ASIA in document,
        "latin_font": FONT_LATIN in document,
        "font_size_10_5pt": f'w:sz w:val="{FONT_HALF_POINTS}"' in document,
    }


def validate_pdf(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if not data.startswith(b"%PDF-"):
        raise ValueError("Generated file is not a PDF")
    pages = len(re.findall(rb"/Type\s*/Page\b", data))
    return {"page_count": pages, "pdf_header": data[:8].decode("ascii", errors="replace")}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the OlistOps project report")
    parser.add_argument("--skip-pdf", action="store_true")
    args = parser.parse_args()

    if not EVIDENCE_PATH.exists():
        raise FileNotFoundError(
            f"Missing evidence: {EVIDENCE_PATH}. Run capture_report_evidence.py first."
        )
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report(evidence)
    render_html(report, HTML_PATH)
    render_docx(report, DOCX_PATH)
    if not args.skip_pdf:
        render_pdf(HTML_PATH, PDF_PATH)
    write_readme()

    docx_validation = validate_docx(DOCX_PATH)
    pdf_validation = None if args.skip_pdf else validate_pdf(PDF_PATH)
    result = {
        "html": {"path": str(HTML_PATH), "bytes": HTML_PATH.stat().st_size},
        "docx": {
            "path": str(DOCX_PATH),
            "bytes": DOCX_PATH.stat().st_size,
            **docx_validation,
        },
        "pdf": (
            None
            if args.skip_pdf
            else {
                "path": str(PDF_PATH),
                "bytes": PDF_PATH.stat().st_size,
                **(pdf_validation or {}),
            }
        ),
        "blocks": len(report.blocks),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
