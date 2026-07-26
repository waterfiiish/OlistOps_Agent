from __future__ import annotations

import argparse
import re
import time
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TOP_SELLER = "06a2c3af7b3aee5d69171b0e14f0ee87"


def demo_query() -> str:
    document = (PROJECT_ROOT / "docs" / "demo.md").read_text(encoding="utf-8")
    match = re.search(r"```text\s*(.*?)\s*```", document, re.DOTALL)
    if not match:
        raise RuntimeError("Demo query code block is missing")
    return match.group(1).replace("\n", " ")


def run(base_url: str, timeout: float) -> dict[str, Any]:
    with httpx.Client(
        base_url=base_url,
        timeout=max(timeout, 30),
        trust_env=False,
    ) as client:
        health = client.get("/healthz").json()
        if not health.get("database"):
            raise RuntimeError(f"Database is unavailable: {health}")
        session = client.post(
            "/api/v1/sessions",
            json={"title": "Automated smoke test"},
        ).json()
        accepted = client.post(
            f"/api/v1/sessions/{session['id']}/messages",
            json={"content": demo_query()},
        ).json()
        run_id = accepted["run_id"]
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            trace_response = client.get(f"/api/v1/runs/{run_id}/trace")
            trace_response.raise_for_status()
            trace = trace_response.json()
            if trace["run"]["status"] in {"completed", "failed"}:
                break
            time.sleep(0.25)
        else:
            raise TimeoutError(f"Run {run_id} did not complete within {timeout}s")

    run_record = trace["run"]
    if run_record["status"] != "completed":
        raise RuntimeError(f"Run failed: {run_record.get('error')}")
    if run_record["intent"] != "delivery_analysis":
        raise AssertionError(f"Unexpected intent: {run_record['intent']}")
    tool_names = {item["tool_name"] for item in trace["tool_calls"]}
    expected_tools = {
        "olist.get_delivery_performance",
        "olist.compare_late_vs_on_time_reviews",
    }
    if not expected_tools <= tool_names or len(trace["tool_calls"]) != 3:
        raise AssertionError(f"Unexpected tool calls: {tool_names}")
    analytics = run_record["state"]["analytics_results"]
    if analytics[0]["rows"][0]["seller_id"] != EXPECTED_TOP_SELLER:
        raise AssertionError("Fixed-task top seller does not match the Gold result")
    answer = "".join(
        event["payload"].get("content", "")
        for event in trace["events"]
        if event["event_type"] == "assistant.delta"
    )
    model_used = run_record["state"].get("model_used")
    if health.get("model", {}).get("status") == "ok":
        if model_used == "deterministic-template":
            raise AssertionError("Healthy local model unexpectedly fell back to template")
        if not answer.startswith("#") or "K-001" not in answer:
            raise AssertionError("Model answer failed heading or citation validation")
    return {
        "run_id": run_id,
        "status": run_record["status"],
        "intent": run_record["intent"],
        "model_used": model_used,
        "step_count": len(trace["steps"]),
        "tool_count": len(trace["tool_calls"]),
        "top_seller": analytics[0]["rows"][0]["seller_id"],
        "answer_length": len(answer),
        "has_k001": "K-001" in answer,
        "health": health,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the fixed OlistOps E2E smoke task")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    result = run(args.base_url, args.timeout)
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
