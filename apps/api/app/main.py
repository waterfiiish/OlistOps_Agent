from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import anyio
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sse_starlette.sse import EventSourceResponse

from apps.api.app.run_service import RunService
from apps.api.app.schemas import (
    KnowledgeSearchRequest,
    MessageCreate,
    RunAccepted,
    SessionCreate,
    SessionResponse,
    TraceResponse,
)
from packages.analytics.schemas import (
    DateRange,
    DeliveryPerformanceRequest,
    FreightAnalysisRequest,
    GeographyPerformanceRequest,
    MetricResult,
    MonthlyTrendRequest,
    PaymentAnalysisRequest,
    ReviewSampleRequest,
    SellerDiagnosticRequest,
)
from packages.analytics.service import AnalyticsService
from packages.analytics.tools import build_analytics_registry
from packages.database.connection import check_database, get_engine
from packages.model_gateway.ollama import OllamaProvider
from packages.retrieval.service import RetrievalService
from packages.shared.config import get_settings

settings = get_settings()
run_service: RunService | None = None
analytics_service: AnalyticsService | None = None
retrieval_service: RetrievalService | None = None


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global run_service, analytics_service, retrieval_service
    run_service = RunService()
    analytics_service = AnalyticsService()
    retrieval_service = RetrievalService()
    try:
        yield
    finally:
        run_service.close()


app = FastAPI(
    title="OlistOps Agent API",
    version="0.2.0",
    description=(
        "Deterministic Olist analytics, evidence-aware LangGraph workflow, "
        "SSE events and trace inspection."
    ),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class HealthResponse(BaseModel):
    status: str
    database: dict[str, str] | None
    model: dict[str, Any]
    rag: dict[str, Any] | None = None
    error: str | None = None


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "OlistOps Agent API",
        "docs": "/docs",
        "health": "/healthz",
    }


@app.get("/healthz", response_model=HealthResponse)
def health() -> HealthResponse:
    try:
        database = check_database()
        status = "ok"
        error = None
    except Exception as exc:
        database = None
        status = "degraded"
        error = f"{type(exc).__name__}: {str(exc)[:300]}"
    model = OllamaProvider().health()
    try:
        rag = RetrievalService().status()
    except Exception:
        rag = None
    if model["status"] != "ok" and status == "ok":
        status = "degraded"
    return HealthResponse(
        status=status,
        database=database,
        model=model,
        rag=rag,
        error=error,
    )


@app.post("/api/v1/sessions", response_model=SessionResponse, status_code=201)
def create_session(payload: SessionCreate) -> SessionResponse:
    with get_engine().begin() as connection:
        row = connection.execute(
            text(
                """
                INSERT INTO app.chat_sessions(title)
                VALUES (:title)
                RETURNING id, title, created_at
                """
            ),
            {"title": payload.title},
        ).mappings().one()
    return SessionResponse.model_validate(dict(row))


@app.get("/api/v1/sessions/{session_id}")
def get_session(session_id: UUID) -> dict[str, Any]:
    with get_engine().connect() as connection:
        session = connection.execute(
            text(
                """
                SELECT id, title, created_at, updated_at
                FROM app.chat_sessions
                WHERE id = :session_id
                """
            ),
            {"session_id": session_id},
        ).mappings().one_or_none()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        messages = connection.execute(
            text(
                """
                SELECT id, role, content, metadata, created_at
                FROM app.chat_messages
                WHERE session_id = :session_id
                ORDER BY created_at, id
                """
            ),
            {"session_id": session_id},
        ).mappings()
        return {
            "session": dict(session),
            "messages": [dict(message) for message in messages],
        }


@app.post(
    "/api/v1/sessions/{session_id}/messages",
    response_model=RunAccepted,
    status_code=202,
)
def submit_message(
    session_id: UUID,
    payload: MessageCreate,
    background_tasks: BackgroundTasks,
) -> RunAccepted:
    assert run_service is not None
    try:
        run_id = run_service.create_run(session_id, payload.content)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    background_tasks.add_task(
        run_service.execute,
        run_id,
        session_id,
        payload.content,
    )
    return RunAccepted(
        run_id=run_id,
        session_id=session_id,
        status="queued",
        events_url=f"/api/v1/runs/{run_id}/events",
    )


@app.get("/api/v1/runs/{run_id}/events")
async def stream_events(
    run_id: UUID,
    after: int = Query(default=0, ge=0),
) -> EventSourceResponse:
    assert run_service is not None

    async def generator() -> AsyncIterator[dict[str, str]]:
        sequence = after
        idle_cycles = 0
        while True:
            events = await anyio.to_thread.run_sync(
                run_service.events_after, run_id, sequence
            )
            if events:
                idle_cycles = 0
                for event in events:
                    sequence = event["sequence"]
                    yield {
                        "id": str(sequence),
                        "event": event["event_type"],
                        "data": json.dumps(
                            event["payload"], ensure_ascii=False, default=str
                        ),
                    }
                    if event["event_type"] in {"run.completed", "run.failed"}:
                        return
            else:
                idle_cycles += 1
                status = await anyio.to_thread.run_sync(run_service.run_status, run_id)
                if status is None:
                    yield {
                        "event": "run.failed",
                        "data": json.dumps({"error": "Run not found"}),
                    }
                    return
                if status in {"completed", "failed", "cancelled"}:
                    return
                if idle_cycles % 40 == 0:
                    yield {"event": "heartbeat", "data": "{}"}
            await asyncio.sleep(0.25)

    return EventSourceResponse(generator(), ping=15)


@app.get("/api/v1/runs/{run_id}/trace", response_model=TraceResponse)
def get_trace(run_id: UUID) -> TraceResponse:
    with get_engine().connect() as connection:
        run = connection.execute(
            text("SELECT * FROM app.agent_runs WHERE id = :run_id"),
            {"run_id": run_id},
        ).mappings().one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        steps = connection.execute(
            text(
                """
                SELECT * FROM app.agent_steps
                WHERE run_id = :run_id ORDER BY id
                """
            ),
            {"run_id": run_id},
        ).mappings()
        tool_calls = connection.execute(
            text(
                """
                SELECT * FROM app.tool_calls
                WHERE run_id = :run_id ORDER BY started_at, id
                """
            ),
            {"run_id": run_id},
        ).mappings()
        events = connection.execute(
            text(
                """
                SELECT * FROM app.agent_events
                WHERE run_id = :run_id ORDER BY sequence
                """
            ),
            {"run_id": run_id},
        ).mappings()
        return TraceResponse(
            run=dict(run),
            steps=[dict(row) for row in steps],
            tool_calls=[dict(row) for row in tool_calls],
            events=[dict(row) for row in events],
        )


@app.post(
    "/api/v1/analytics/delivery-performance",
    response_model=MetricResult,
)
def delivery_performance(payload: DeliveryPerformanceRequest) -> MetricResult:
    assert analytics_service is not None
    return analytics_service.get_delivery_performance(payload)


@app.get("/api/v1/tools")
def list_tools() -> dict[str, Any]:
    assert analytics_service is not None
    registry = build_analytics_registry(analytics_service)
    return {
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "permission": tool.permission.value,
                "input_schema": tool.input_model.model_json_schema(),
            }
            for tool in registry.list()
        ]
    }


@app.get("/api/v1/knowledge/status")
def knowledge_status() -> dict[str, Any]:
    assert retrieval_service is not None
    return retrieval_service.status()


@app.get("/api/v1/knowledge/documents")
def knowledge_documents() -> dict[str, Any]:
    assert retrieval_service is not None
    documents = retrieval_service.list_documents()
    return {"count": len(documents), "documents": documents}


@app.post("/api/v1/knowledge/search")
def knowledge_search(payload: KnowledgeSearchRequest) -> dict[str, Any]:
    assert retrieval_service is not None
    rows = retrieval_service.search(
        payload.query,
        limit=payload.limit,
        mode=payload.mode,
    )
    results = [
        {
            key: value
            for key, value in row.items()
            if key != "content"
        }
        | {"excerpt": " ".join(row["content"].split())[:800]}
        for row in rows
    ]
    return {
        "query": payload.query,
        "mode": payload.mode,
        "count": len(results),
        "results": results,
    }


@app.post("/api/v1/analytics/sales-summary", response_model=MetricResult)
def sales_summary(payload: DateRange) -> MetricResult:
    assert analytics_service is not None
    return analytics_service.get_sales_summary(payload)


@app.post("/api/v1/analytics/operations-overview", response_model=MetricResult)
def operations_overview(payload: DateRange) -> MetricResult:
    assert analytics_service is not None
    return analytics_service.get_operations_overview(payload)


@app.post("/api/v1/analytics/monthly-trend", response_model=MetricResult)
def monthly_trend(payload: MonthlyTrendRequest) -> MetricResult:
    assert analytics_service is not None
    return analytics_service.get_monthly_trend(payload)


@app.post("/api/v1/analytics/geography-performance", response_model=MetricResult)
def geography_performance(payload: GeographyPerformanceRequest) -> MetricResult:
    assert analytics_service is not None
    return analytics_service.get_geography_performance(payload)


@app.post("/api/v1/analytics/freight-analysis", response_model=MetricResult)
def freight_analysis(payload: FreightAnalysisRequest) -> MetricResult:
    assert analytics_service is not None
    return analytics_service.get_freight_analysis(payload)


@app.post("/api/v1/analytics/payment-analysis", response_model=MetricResult)
def payment_analysis(payload: PaymentAnalysisRequest) -> MetricResult:
    assert analytics_service is not None
    return analytics_service.get_payment_analysis(payload)


@app.post("/api/v1/analytics/review-comparison", response_model=MetricResult)
def review_comparison(payload: DateRange) -> MetricResult:
    assert analytics_service is not None
    return analytics_service.compare_late_vs_on_time_reviews(payload)


@app.post("/api/v1/analytics/seller-diagnostic", response_model=MetricResult)
def seller_diagnostic(payload: SellerDiagnosticRequest) -> MetricResult:
    assert analytics_service is not None
    return analytics_service.get_seller_diagnostic(payload)


@app.post("/api/v1/analytics/review-samples", response_model=MetricResult)
def review_samples(payload: ReviewSampleRequest) -> MetricResult:
    assert analytics_service is not None
    return analytics_service.search_review_samples(payload)
