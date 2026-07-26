from __future__ import annotations

import argparse
import time
from typing import Any

import httpx

OVERVIEW_QUERY = (
    "分析 2018 年全年的经营总览，包括订单状态、取消与不可用订单、"
    "销售代理值、整体延期率和平均评分。"
)


def run(base_url: str, timeout: float) -> dict[str, Any]:
    with httpx.Client(
        base_url=base_url,
        timeout=max(timeout, 30),
        trust_env=False,
    ) as client:
        health = client.get("/healthz").json()
        session_response = client.post(
            "/api/v1/sessions",
            json={"title": "Expanded operations overview smoke test"},
        )
        session_response.raise_for_status()
        session = session_response.json()
        accepted_response = client.post(
            f"/api/v1/sessions/{session['id']}/messages",
            json={"content": OVERVIEW_QUERY},
        )
        accepted_response.raise_for_status()
        run_id = accepted_response.json()["run_id"]

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            response = client.get(f"/api/v1/runs/{run_id}/trace")
            response.raise_for_status()
            trace = response.json()
            if trace["run"]["status"] in {"completed", "failed"}:
                break
            time.sleep(0.25)
        else:
            raise TimeoutError(f"Run {run_id} did not complete within {timeout}s")

    run_record = trace["run"]
    if run_record["status"] != "completed":
        raise RuntimeError(f"Run failed: {run_record.get('error')}")
    if run_record["intent"] != "operations_overview":
        raise AssertionError(f"Unexpected intent: {run_record['intent']}")

    tool_names = {item["tool_name"] for item in trace["tool_calls"]}
    expected_tools = {
        "olist.get_operations_overview",
        "olist.get_sales_summary",
        "olist.get_delivery_performance",
    }
    if tool_names != expected_tools:
        raise AssertionError(f"Unexpected tools: {sorted(tool_names)}")

    answer = "".join(
        event["payload"].get("content", "")
        for event in trace["events"]
        if event["event_type"] == "assistant.delta"
    )
    model_used = run_record["state"].get("model_used")
    if health.get("model", {}).get("status") == "ok" and (
        model_used == "deterministic-template"
        or not answer.startswith("#")
        or "K-001" not in answer
    ):
        raise AssertionError("Expanded scenario failed model or citation validation")

    return {
        "run_id": run_id,
        "status": run_record["status"],
        "intent": run_record["intent"],
        "model_used": model_used,
        "step_count": len(trace["steps"]),
        "tool_names": sorted(tool_names),
        "answer_length": len(answer),
        "has_k001": "K-001" in answer,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the expanded operations-overview E2E scenario"
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    result = run(args.base_url, args.timeout)
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
