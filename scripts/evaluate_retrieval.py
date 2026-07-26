from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from packages.retrieval.service import RetrievalMode, RetrievalService

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "data" / "eval" / "retrieval_gold.jsonl"
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "data" / "processed" / "retrieval_eval_latest.json"
)


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def evaluate(
    service: RetrievalService,
    cases: list[dict[str, Any]],
    *,
    mode: RetrievalMode,
    top_k: int,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    latencies: list[float] = []
    for case in cases:
        started = time.perf_counter()
        rows = service.search(
            str(case["query"]),
            limit=top_k,
            mode=mode,
            log_search=False,
        )
        latencies.append((time.perf_counter() - started) * 1000)
        titles = [str(row["title"]) for row in rows]
        gold_titles = set(case["gold_titles"])
        first_hit = next(
            (
                rank
                for rank, title in enumerate(titles, 1)
                if title in gold_titles
            ),
            None,
        )
        results.append(
            {
                "id": case["id"],
                "query": case["query"],
                "gold_titles": sorted(gold_titles),
                "retrieved_titles": titles,
                "first_hit_rank": first_hit,
                "passed": first_hit is not None,
            }
        )

    total = len(results)
    hits = sum(bool(result["passed"]) for result in results)
    reciprocal_rank_sum = sum(
        1.0 / int(result["first_hit_rank"])
        for result in results
        if result["first_hit_rank"] is not None
    )
    top1_hits = sum(result["first_hit_rank"] == 1 for result in results)
    return {
        "dataset": "retrieval_gold",
        "configuration": {"mode": mode, "top_k": top_k},
        "metrics": {
            "total": total,
            f"recall_at_{top_k}": round(hits / total, 4) if total else 0.0,
            "mrr": round(reciprocal_rank_sum / total, 4) if total else 0.0,
            "top1_accuracy": round(top1_hits / total, 4) if total else 0.0,
            "mean_latency_ms": (
                round(sum(latencies) / len(latencies), 2) if latencies else 0.0
            ),
        },
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate OlistOps knowledge retrieval")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--mode",
        choices=["hybrid", "fts", "vector"],
        default="hybrid",
    )
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.top_k <= 20:
        parser.error("--top-k must be between 1 and 20")

    report = evaluate(
        RetrievalService(),
        load_cases(args.dataset.resolve()),
        mode=args.mode,
        top_k=args.top_k,
    )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    print(f"Report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
