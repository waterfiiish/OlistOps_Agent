from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import markdown  # type: ignore[import-untyped]
from sqlalchemy import text

from packages.database.connection import get_engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "项目导览与使用指南" / "项目介绍报告"

DEMO_QUERY = (
    "分析 2018 年 7 月的配送表现，找出延期率最高且订单量不少于 20 "
    "的卖家和商品类别，比较延期订单与按时订单的平均评分，并给出改进建议。"
)
RAG_QUERY = "配送延期和包装检查应该如何处理，并且报告需要怎样引用证据？"


def _escape(value: Any) -> str:
    import html

    return html.escape(str(value), quote=True)


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_escape(title)}</title>
<style>
:root {{
  font-family: "Times New Roman", SimSun, serif;
  color: #10233e;
  background: #f4f0e8;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background:
    linear-gradient(rgba(21,57,95,.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(21,57,95,.05) 1px, transparent 1px),
    #f4f0e8;
  background-size: 28px 28px;
}}
main {{ width: min(1320px, calc(100% - 56px)); margin: 0 auto; padding: 36px 0 72px; }}
header {{ display:flex; justify-content:space-between; align-items:flex-end;
  border-bottom:3px solid #173b64; padding:22px 0; margin-bottom:28px; }}
.eyebrow {{ color:#e85b3c; font-weight:700; letter-spacing:.12em; }}
h1 {{ margin:6px 0 0; font-size:38px; font-weight:500; }}
h2 {{ margin:28px 0 12px; font-size:23px; }}
.stamp {{ color:#65758a; font-size:13px; text-align:right; }}
.grid {{ display:grid; grid-template-columns:repeat(4,1fr); border:2px solid #173b64; }}
.card {{
  padding:18px; min-height:104px; border-right:1px solid #173b64;
  background:rgba(255,255,255,.6);
}}
.card:last-child {{ border-right:0; }}
.card small {{ display:block; color:#6a7888; text-transform:uppercase; letter-spacing:.08em; }}
.card strong {{ display:block; margin-top:9px; font-size:23px; color:#173b64; }}
table {{ width:100%; border-collapse:collapse; background:rgba(255,255,255,.66); }}
th,td {{ border:1px solid #aeb9c5; padding:9px 12px; text-align:left; vertical-align:top; }}
th {{ background:#173b64; color:white; }}
pre {{ white-space:pre-wrap; word-break:break-word; background:#10233e; color:#eef5ff;
  padding:18px; border-left:7px solid #e85b3c; line-height:1.55; }}
.report {{ background:rgba(255,255,255,.78); border:2px solid #173b64; padding:28px 34px; }}
.report h1 {{ font-size:30px; }}
.report h2 {{ border-bottom:1px solid #9facba; padding-bottom:6px; }}
.trace {{ display:flex; flex-wrap:wrap; gap:7px; }}
.trace span {{ background:#173b64; color:#fff; padding:7px 10px; font-size:13px; }}
.notice {{ margin:18px 0; padding:14px 16px; border:1px solid #e85b3c; background:#fff6ed; }}
</style>
</head>
<body><main>{body}</main></body></html>"""


def _collect_database() -> dict[str, Any]:
    raw_tables = [
        "customers",
        "geolocation",
        "orders",
        "order_items",
        "order_payments",
        "order_reviews",
        "products",
        "sellers",
        "category_translation",
    ]
    marts = [
        "mart_order_fulfillment",
        "mart_seller_order_fulfillment",
        "mart_category_order_fulfillment",
        "mart_review_analysis_base",
        "mart_payment_analysis_base",
        "mart_seller_performance_monthly",
        "mart_category_performance_monthly",
    ]
    with get_engine().connect() as connection:
        raw_counts = {
            table: int(
                connection.execute(text(f"SELECT count(*) FROM raw.{table}")).scalar_one()
            )
            for table in raw_tables
        }
        mart_counts = {
            table: int(
                connection.execute(text(f"SELECT count(*) FROM mart.{table}")).scalar_one()
            )
            for table in marts
        }
        date_range = connection.execute(
            text(
                """
                SELECT
                    min(purchased_at)::date AS start_date,
                    max(purchased_at)::date AS end_date
                FROM staging.stg_orders
                """
            )
        ).mappings().one()
    return {
        "raw_counts": raw_counts,
        "mart_counts": mart_counts,
        "date_range": {key: str(value) for key, value in date_range.items()},
    }


def _run_agent(client: httpx.Client, timeout: float) -> tuple[dict[str, Any], str]:
    session = client.post(
        "/api/v1/sessions",
        json={"title": "项目介绍报告真实运行证据"},
    )
    session.raise_for_status()
    session_id = session.json()["id"]
    accepted = client.post(
        f"/api/v1/sessions/{session_id}/messages",
        json={"content": DEMO_QUERY},
    )
    accepted.raise_for_status()
    run_id = accepted.json()["run_id"]
    deadline = time.monotonic() + timeout
    trace: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/runs/{run_id}/trace")
        response.raise_for_status()
        trace = response.json()
        if trace["run"]["status"] in {"completed", "failed"}:
            break
        time.sleep(0.5)
    if trace is None or trace["run"]["status"] != "completed":
        raise RuntimeError(f"Agent run did not complete: {trace}")
    answer = "".join(
        event["payload"].get("content", "")
        for event in trace["events"]
        if event["event_type"] == "assistant.delta"
    )
    return trace, answer


def capture(base_url: str, output_dir: Path, timeout: float) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    assets = output_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    database = _collect_database()
    with httpx.Client(base_url=base_url, timeout=max(timeout, 30), trust_env=False) as client:
        health_response = client.get("/healthz")
        health_response.raise_for_status()
        health = health_response.json()
        knowledge_response = client.get("/api/v1/knowledge/status")
        knowledge_response.raise_for_status()
        knowledge = knowledge_response.json()
        search_response = client.post(
            "/api/v1/knowledge/search",
            json={"query": RAG_QUERY, "limit": 5, "mode": "hybrid"},
        )
        search_response.raise_for_status()
        search = search_response.json()
        trace, answer = _run_agent(client, timeout)

    run_state = trace["run"]["state"]
    retrieval_event = next(
        event
        for event in trace["events"]
        if event["event_type"] == "retrieval.completed"
    )
    evidence = {
        "captured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "base_url": base_url,
        "health": health,
        "knowledge": knowledge,
        "search": search,
        "database": database,
        "agent": {
            "run_id": trace["run"]["id"],
            "status": trace["run"]["status"],
            "intent": trace["run"]["intent"],
            "model_used": run_state.get("model_used"),
            "critic_report": run_state.get("critic_report"),
            "nodes": [step["node_name"] for step in trace["steps"]],
            "tools": [call["tool_name"] for call in trace["tool_calls"]],
            "retrieval": retrieval_event["payload"],
            "answer": answer,
            "answer_length": len(answer),
        },
    }
    (output_dir / "actual_evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    raw_rows = "".join(
        f"<tr><td>raw.{_escape(name)}</td><td>{count:,}</td></tr>"
        for name, count in database["raw_counts"].items()
    )
    mart_rows = "".join(
        f"<tr><td>mart.{_escape(name)}</td><td>{count:,}</td></tr>"
        for name, count in database["mart_counts"].items()
    )
    data_html = _page(
        "OlistOps 真实数据库快照",
        f"""
<header><div><div class="eyebrow">LIVE DATABASE EVIDENCE</div>
<h1>OlistOps 真实数据库快照</h1></div>
<div class="stamp">采集时间<br>{_escape(evidence["captured_at"])}</div></header>
<div class="grid">
  <div class="card"><small>PostgreSQL</small>
    <strong>{_escape(health["database"]["version"])}</strong></div>
  <div class="card"><small>订单</small><strong>{database["raw_counts"]["orders"]:,}</strong></div>
  <div class="card"><small>订单明细</small>
    <strong>{database["raw_counts"]["order_items"]:,}</strong></div>
  <div class="card"><small>数据期间</small>
    <strong>{_escape(database["date_range"]["start_date"])}—
    {_escape(database["date_range"]["end_date"])}</strong></div>
</div>
<h2>RAW 原始层</h2><table><thead><tr><th>表</th><th>当前行数</th></tr></thead>
<tbody>{raw_rows}</tbody></table>
<h2>MART 分析层</h2><table><thead><tr><th>表/物化视图</th><th>当前行数</th></tr></thead>
<tbody>{mart_rows}</tbody></table>
""",
    )
    (assets / "data_actual.html").write_text(data_html, encoding="utf-8")

    search_rows = "".join(
        "<tr>"
        f"<td>K-{index:03d}</td>"
        f"<td>{_escape(row['title'])}</td>"
        f"<td>{_escape(row.get('fts_rank'))}</td>"
        f"<td>{_escape(row.get('vector_rank'))}</td>"
        f"<td>{float(row.get('rrf_score') or 0):.8f}</td>"
        f"<td>{_escape(row.get('excerpt', '')[:180])}</td>"
        "</tr>"
        for index, row in enumerate(search["results"], 1)
    )
    rag_html = _page(
        "OlistOps Hybrid RAG 实测",
        f"""
<header><div><div class="eyebrow">LIVE HYBRID RAG EVIDENCE</div>
<h1>Hybrid RAG 检索实测</h1></div>
<div class="stamp">查询<br>{_escape(RAG_QUERY)}</div></header>
<div class="grid">
  <div class="card"><small>模式</small><strong>{_escape(knowledge["retrieval_mode"])}</strong></div>
  <div class="card"><small>文档</small><strong>{knowledge["document_count"]}</strong></div>
  <div class="card"><small>向量覆盖</small>
    <strong>{knowledge["embedded_chunk_count"]}/{knowledge["chunk_count"]}</strong></div>
  <div class="card"><small>Embedding</small>
    <strong>{_escape(knowledge["embedding_provider"])} /
    {knowledge["embedding_dimensions"]}d</strong></div>
</div>
<div class="notice">Weighted RRF：FTS {knowledge["rrf"]["fts_weight"]}，
Vector {knowledge["rrf"]["vector_weight"]}，k={knowledge["rrf"]["k"]}。
以下结果来自当前运行中的真实 API。</div>
<table><thead><tr><th>引用</th><th>文档</th><th>FTS Rank</th>
<th>Vector Rank</th><th>RRF Score</th><th>证据摘录</th></tr></thead>
<tbody>{search_rows}</tbody></table>
""",
    )
    (assets / "rag_actual.html").write_text(rag_html, encoding="utf-8")

    nodes = "".join(
        f"<span>{index:02d} {_escape(node)}</span>"
        for index, node in enumerate(evidence["agent"]["nodes"], 1)
    )
    answer_html = markdown.markdown(
        answer,
        extensions=["tables", "fenced_code"],
    )
    critic = evidence["agent"]["critic_report"]
    agent_html = _page(
        "OlistOps Agent 真实运行报告",
        f"""
<header><div><div class="eyebrow">LIVE AGENT RUN</div>
<h1>Agent 真实运行与证据报告</h1></div>
<div class="stamp">run_id<br>{_escape(evidence["agent"]["run_id"])}</div></header>
<div class="grid">
  <div class="card"><small>Intent</small>
    <strong>{_escape(evidence["agent"]["intent"])}</strong></div>
  <div class="card"><small>Model</small>
    <strong>{_escape(evidence["agent"]["model_used"])}</strong></div>
  <div class="card"><small>Critic</small>
    <strong>{_escape(critic["score"])} / {_escape(critic["passed"])}</strong></div>
  <div class="card"><small>Citations</small>
    <strong>{len(run_state.get("retrieved_chunks", []))}</strong></div>
</div>
<h2>真实 LangGraph Trace</h2><div class="trace">{nodes}</div>
<h2>最终报告</h2><article class="report">{answer_html}</article>
""",
    )
    (assets / "agent_actual.html").write_text(agent_html, encoding="utf-8")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture live evidence for the project report")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    evidence = capture(args.base_url, args.output_dir.resolve(), args.timeout)
    print(
        json.dumps(
            {
                "run_id": evidence["agent"]["run_id"],
                "status": evidence["agent"]["status"],
                "critic": evidence["agent"]["critic_report"]["score"],
                "rag_chunks": evidence["knowledge"]["chunk_count"],
                "embedded_chunks": evidence["knowledge"]["embedded_chunk_count"],
                "output": str(args.output_dir.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
