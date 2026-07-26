from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    run_id: str
    session_id: str
    user_id: str
    user_query: str
    intent: str
    time_range: dict[str, str]
    entity_filters: dict[str, Any]
    plan: list[dict[str, Any]]
    analytics_results: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    retrieval_query: str
    retrieved_chunks: list[dict[str, Any]]
    evidence_status: str
    draft_answer: str
    model_used: str
    critic_report: dict[str, Any]
    approval_required: bool
    approval_id: str | None
    approval_status: str | None
    artifacts: list[dict[str, Any]]
    warnings: list[str]
    errors: list[dict[str, Any]]
    budgets: dict[str, Any]
