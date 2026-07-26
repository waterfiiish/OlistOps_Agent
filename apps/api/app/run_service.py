from __future__ import annotations

import json
import traceback
from collections.abc import Mapping
from typing import Any, cast
from uuid import UUID

from sqlalchemy import text

from packages.agent_runtime.state import AgentState
from packages.agent_runtime.workflow import OlistOpsWorkflow
from packages.database.connection import get_engine
from packages.shared.config import get_settings
from packages.shared.security import redact_text


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


class RunService:
    def __init__(self, workflow: OlistOpsWorkflow | None = None) -> None:
        self.engine = get_engine()
        self.workflow = workflow or OlistOpsWorkflow()
        self.settings = get_settings()

    def close(self) -> None:
        self.workflow.close()

    def create_run(self, session_id: UUID, content: str) -> UUID:
        with self.engine.begin() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM app.chat_sessions WHERE id = :session_id"),
                {"session_id": session_id},
            ).scalar_one_or_none()
            if not exists:
                raise LookupError("Session not found")
            connection.execute(
                text(
                    """
                    INSERT INTO app.chat_messages(session_id, role, content)
                    VALUES (:session_id, 'user', :content)
                    """
                ),
                {"session_id": session_id, "content": content},
            )
            run_id = connection.execute(
                text(
                    """
                    INSERT INTO app.agent_runs(session_id, status, model_profile)
                    VALUES (:session_id, 'queued', :profile)
                    RETURNING id
                    """
                ),
                {
                    "session_id": session_id,
                    "profile": self.settings.model_default_profile,
                },
            ).scalar_one()
            self._event(
                connection,
                run_id,
                "run.queued",
                {"status": "queued"},
            )
        return run_id

    @staticmethod
    def _event(
        connection: Any, run_id: UUID | str, event_type: str, payload: dict[str, Any]
    ) -> None:
        connection.execute(
            text(
                """
                INSERT INTO app.agent_events(run_id, event_type, payload)
                VALUES (:run_id, :event_type, CAST(:payload AS jsonb))
                """
            ),
            {"run_id": run_id, "event_type": event_type, "payload": _json(payload)},
        )

    def execute(self, run_id: UUID, session_id: UUID, content: str) -> None:
        aggregate: AgentState = {
            "run_id": str(run_id),
            "session_id": str(session_id),
            "user_query": content,
        }
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE app.agent_runs
                    SET status = 'running', started_at = now()
                    WHERE id = :run_id
                    """
                ),
                {"run_id": run_id},
            )
            self._event(
                connection,
                run_id,
                "run.started",
                {"run_id": str(run_id), "session_id": str(session_id)},
            )

        try:
            for update in self.workflow.stream(aggregate, thread_id=str(run_id)):
                for node_name, node_output in update.items():
                    if not isinstance(node_output, dict):
                        node_output = {"output": str(node_output)}
                    input_summary = {
                        "query": redact_text(content),
                        "intent": aggregate.get("intent"),
                    }
                    aggregate.update(cast(AgentState, node_output))
                    output_summary = self._step_summary(node_name, node_output)
                    with self.engine.begin() as connection:
                        self._event(
                            connection,
                            run_id,
                            "node.started",
                            {"node": node_name},
                        )
                        step_id = connection.execute(
                            text(
                                """
                                INSERT INTO app.agent_steps(
                                    run_id, node_name, status, input_summary,
                                    output_summary, completed_at
                                )
                                VALUES (
                                    :run_id, :node_name, 'completed',
                                    CAST(:input_summary AS jsonb),
                                    CAST(:output_summary AS jsonb),
                                    now()
                                )
                                RETURNING id
                                """
                            ),
                            {
                                "run_id": run_id,
                                "node_name": node_name,
                                "input_summary": _json(input_summary),
                                "output_summary": _json(output_summary),
                            },
                        ).scalar_one()
                        if node_name == "run_analytics":
                            for tool_call in node_output.get("tool_calls", []):
                                connection.execute(
                                    text(
                                        """
                                        INSERT INTO app.tool_calls(
                                            run_id, step_id, tool_name, permission,
                                            arguments, result_summary, completed_at
                                        )
                                        VALUES (
                                            :run_id, :step_id, :tool_name, :permission,
                                            CAST(:arguments AS jsonb),
                                            CAST(:result_summary AS jsonb),
                                            now()
                                        )
                                        """
                                    ),
                                    {
                                        "run_id": run_id,
                                        "step_id": step_id,
                                        "tool_name": tool_call["tool_name"],
                                        "permission": tool_call["permission"],
                                        "arguments": _json(tool_call["arguments"]),
                                        "result_summary": _json(
                                            tool_call["result_summary"]
                                        ),
                                    },
                                )
                                self._event(
                                    connection,
                                    run_id,
                                    "tool.completed",
                                    {
                                        "tool_name": tool_call["tool_name"],
                                        "permission": tool_call["permission"],
                                        "result_summary": tool_call["result_summary"],
                                    },
                                )
                        if node_name == "retrieve_knowledge":
                            chunks = node_output.get("retrieved_chunks", [])
                            self._event(
                                connection,
                                run_id,
                                "retrieval.completed",
                                {
                                    "query": redact_text(
                                        node_output.get("retrieval_query", "")
                                    ),
                                    "mode": (
                                        chunks[0].get("retrieval_mode")
                                        if chunks
                                        else self.settings.retrieval_mode
                                    ),
                                    "result_count": len(chunks),
                                    "results": [
                                        {
                                            "citation": f"K-{index:03d}",
                                            "title": chunk.get("title"),
                                            "fts_rank": chunk.get("fts_rank"),
                                            "vector_rank": chunk.get("vector_rank"),
                                            "rrf_score": chunk.get("rrf_score"),
                                        }
                                        for index, chunk in enumerate(chunks, 1)
                                    ],
                                },
                            )
                        self._event(
                            connection,
                            run_id,
                            "node.completed",
                            {"node": node_name, "summary": output_summary},
                        )

            answer = aggregate.get("draft_answer", "")
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO app.chat_messages(
                            session_id, role, content, metadata
                        )
                        VALUES (
                            :session_id, 'assistant', :content,
                            CAST(:metadata AS jsonb)
                        )
                        """
                    ),
                    {
                        "session_id": session_id,
                        "content": answer,
                        "metadata": _json(
                            {
                                "run_id": str(run_id),
                                "model_used": aggregate.get("model_used"),
                                "evidence_status": aggregate.get("evidence_status"),
                            }
                        ),
                    },
                )
                connection.execute(
                    text(
                        """
                        UPDATE app.agent_runs
                        SET status = 'completed',
                            intent = :intent,
                            state = CAST(:state AS jsonb),
                            warning_count = :warning_count,
                            completed_at = now()
                        WHERE id = :run_id
                        """
                    ),
                    {
                        "run_id": run_id,
                        "intent": aggregate.get("intent"),
                        "state": _json(self._persistable_state(aggregate)),
                        "warning_count": len(aggregate.get("warnings", [])),
                    },
                )
                self._event(
                    connection,
                    run_id,
                    "assistant.delta",
                    {"content": answer},
                )
                self._event(
                    connection,
                    run_id,
                    "run.completed",
                    {
                        "status": "completed",
                        "model_used": aggregate.get("model_used"),
                        "evidence_status": aggregate.get("evidence_status"),
                        "critic_score": aggregate.get("critic_report", {}).get(
                            "score"
                        ),
                    },
                )
        except Exception as exc:
            error = {
                "type": type(exc).__name__,
                "message": str(exc)[:1000],
                "traceback": traceback.format_exc(limit=8),
            }
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        UPDATE app.agent_runs
                        SET status = 'failed',
                            error = CAST(:error AS jsonb),
                            completed_at = now()
                        WHERE id = :run_id
                        """
                    ),
                    {"run_id": run_id, "error": _json(error)},
                )
                self._event(
                    connection,
                    run_id,
                    "run.failed",
                    {"status": "failed", "error": error},
                )

    @staticmethod
    def _step_summary(node_name: str, output: dict[str, Any]) -> dict[str, Any]:
        if node_name == "run_analytics":
            return {
                "metrics": [
                    {
                        "metric_name": item.get("metric_name"),
                        "row_count": len(item.get("rows", [])),
                        "definition": item.get("definition"),
                    }
                    for item in output.get("analytics_results", [])
                ],
                "tool_count": len(output.get("tool_calls", [])),
            }
        if node_name == "retrieve_knowledge":
            chunks = output.get("retrieved_chunks", [])
            return {
                "query": redact_text(output.get("retrieval_query", "")),
                "mode": (
                    chunks[0].get("retrieval_mode")
                    if chunks
                    else get_settings().retrieval_mode
                ),
                "chunk_ids": [
                    item.get("chunk_id") for item in chunks
                ],
                "scores": [
                    {
                        "chunk_id": item.get("chunk_id"),
                        "fts_rank": item.get("fts_rank"),
                        "vector_rank": item.get("vector_rank"),
                        "rrf_score": item.get("rrf_score"),
                    }
                    for item in chunks
                ],
            }
        if node_name == "critic":
            return output.get("critic_report", {})
        if node_name in {"synthesize", "finalize"}:
            return {
                "answer_length": len(output.get("draft_answer", "")),
                "model_used": output.get("model_used"),
            }
        return {
            key: value
            for key, value in output.items()
            if key not in {"user_query", "draft_answer", "analytics_results", "retrieved_chunks"}
        }

    @staticmethod
    def _persistable_state(state: Mapping[str, Any]) -> dict[str, Any]:
        keep = {
            "run_id",
            "session_id",
            "intent",
            "time_range",
            "entity_filters",
            "plan",
            "analytics_results",
            "tool_calls",
            "retrieved_chunks",
            "evidence_status",
            "model_used",
            "critic_report",
            "approval_required",
            "artifacts",
            "warnings",
            "errors",
            "budgets",
        }
        persisted = {key: value for key, value in state.items() if key in keep}
        if "retrieved_chunks" in persisted:
            persisted["retrieved_chunks"] = [
                {
                    key: value
                    for key, value in chunk.items()
                    if key != "content"
                }
                for chunk in persisted["retrieved_chunks"]
            ]
        return persisted

    def events_after(self, run_id: UUID, sequence: int) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT sequence, event_type, payload, created_at
                    FROM app.agent_events
                    WHERE run_id = :run_id AND sequence > :sequence
                    ORDER BY sequence
                    LIMIT 100
                    """
                ),
                {"run_id": run_id, "sequence": sequence},
            ).mappings()
            return [
                {
                    "sequence": row["sequence"],
                    "event_type": row["event_type"],
                    "payload": row["payload"],
                    "created_at": row["created_at"].isoformat(),
                }
                for row in rows
            ]

    def run_status(self, run_id: UUID) -> str | None:
        with self.engine.connect() as connection:
            return connection.execute(
                text("SELECT status FROM app.agent_runs WHERE id = :run_id"),
                {"run_id": run_id},
            ).scalar_one_or_none()
