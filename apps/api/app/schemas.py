from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    title: str = Field(default="New analysis", min_length=1, max_length=160)


class SessionResponse(BaseModel):
    id: UUID
    title: str
    created_at: datetime


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=12_000)


class RunAccepted(BaseModel):
    run_id: UUID
    session_id: UUID
    status: str
    events_url: str


class ApprovalDecision(BaseModel):
    reason: str = Field(default="", max_length=500)


class TraceResponse(BaseModel):
    run: dict[str, Any]
    steps: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    events: list[dict[str, Any]]


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2_000)
    limit: int = Field(default=5, ge=1, le=20)
    mode: Literal["hybrid", "fts", "vector"] = "hybrid"
