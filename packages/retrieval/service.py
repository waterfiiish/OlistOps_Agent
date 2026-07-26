from __future__ import annotations

import time
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from packages.database.connection import get_engine
from packages.retrieval.embeddings import LocalHashEmbedding
from packages.shared.config import get_settings
from packages.shared.security import contains_prompt_injection

RetrievalMode = Literal["hybrid", "fts", "vector"]

DOMAIN_EXPANSIONS: dict[tuple[str, ...], tuple[str, ...]] = {
    ("延期", "延迟", "晚到", "late"): (
        "延期",
        "延迟",
        "配送",
        "送达",
        "delivery",
        "late",
    ),
    ("包装", "破损", "包裹", "packaging"): (
        "包装",
        "发货",
        "破损",
        "检查",
        "packaging",
    ),
    ("差评", "低分", "投诉", "review"): (
        "差评",
        "低分",
        "评论",
        "客户",
        "review",
    ),
    ("卖家", "商家", "seller"): ("卖家", "绩效", "复盘", "seller"),
    ("运费", "物流成本", "freight"): ("运费", "成本", "物流", "freight"),
    ("支付", "信用卡", "分期", "payment"): (
        "支付",
        "付款",
        "信用卡",
        "分期",
        "payment",
    ),
    ("证据", "引用", "报告", "evidence"): (
        "证据",
        "引用",
        "报告",
        "口径",
        "evidence",
    ),
    ("安全", "审批", "越权", "security"): (
        "安全",
        "审批",
        "权限",
        "越权",
        "security",
    ),
}


def expand_query(query: str, *, max_terms: int = 18) -> list[str]:
    normalized = query.lower()
    terms = LocalHashEmbedding.tokenize(normalized)
    expansions: list[str] = []
    for triggers, additions in DOMAIN_EXPANSIONS.items():
        if any(trigger in normalized for trigger in triggers):
            expansions.extend(additions)
    useful_terms = [
        term
        for term in [*expansions, *terms]
        if len(term) >= 2 and not term.isdigit()
    ]
    return list(dict.fromkeys(useful_terms))[:max_terms]


class RetrievalService:
    """PostgreSQL FTS + pgvector retrieval fused with weighted RRF."""

    def __init__(
        self,
        engine: Engine | None = None,
        embedder: LocalHashEmbedding | None = None,
    ) -> None:
        self.engine = engine or get_engine()
        self.settings = get_settings()
        self.embedder = embedder or LocalHashEmbedding(
            self.settings.embedding_dimensions
        )

    def _lexical_candidates(
        self,
        query: str,
        terms: list[str],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        if not terms:
            return []
        patterns = [f"%{term}%" for term in terms]
        sql = text(
            """
            WITH scored AS (
                SELECT
                    c.id AS chunk_id,
                    c.document_id,
                    d.title,
                    d.source_url,
                    c.ordinal,
                    c.heading_path,
                    c.content,
                    ts_rank_cd(
                        c.search_vector,
                        websearch_to_tsquery('simple', :query)
                    ) AS fts_score,
                    (
                        SELECT count(*)
                        FROM unnest(CAST(:patterns AS text[])) pattern
                        WHERE c.content ILIKE pattern
                           OR d.title ILIKE pattern
                    ) AS lexical_hits,
                    (
                        SELECT count(*)
                        FROM unnest(CAST(:patterns AS text[])) pattern
                        WHERE d.title ILIKE pattern
                    ) AS title_hits
                FROM knowledge.chunks c
                JOIN knowledge.documents d ON d.id = c.document_id
                WHERE d.status = 'ready'
            )
            SELECT *
            FROM scored
            WHERE fts_score > 0 OR lexical_hits > 0
            ORDER BY
                title_hits DESC,
                lexical_hits DESC,
                fts_score DESC,
                title,
                ordinal
            LIMIT :limit
            """
        )
        with self.engine.connect() as connection:
            rows = connection.execute(
                sql,
                {
                    "query": " OR ".join(terms),
                    "patterns": patterns,
                    "limit": limit,
                },
            ).mappings()
            return [dict(row) for row in rows]

    def _vector_candidates(
        self,
        query: str,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        embedding = self.embedder.embed(query)
        if not any(embedding):
            return []
        sql = text(
            """
            SELECT
                c.id AS chunk_id,
                c.document_id,
                d.title,
                d.source_url,
                c.ordinal,
                c.heading_path,
                c.content,
                1 - (c.embedding <=> CAST(:embedding AS vector)) AS vector_score
            FROM knowledge.chunks c
            JOIN knowledge.documents d ON d.id = c.document_id
            WHERE d.status = 'ready' AND c.embedding IS NOT NULL
            ORDER BY c.embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
            """
        )
        with self.engine.connect() as connection:
            rows = connection.execute(
                sql,
                {
                    "embedding": self.embedder.to_literal(embedding),
                    "limit": limit,
                },
            ).mappings()
            return [dict(row) for row in rows]

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        mode: RetrievalMode | None = None,
        log_search: bool = True,
    ) -> list[dict[str, Any]]:
        started = time.perf_counter()
        normalized_query = query.strip()
        if not normalized_query:
            return []
        selected_mode = mode or self.settings.retrieval_mode
        if selected_mode not in {"hybrid", "fts", "vector"}:
            raise ValueError(f"Unsupported retrieval mode: {selected_mode}")
        result_limit = max(1, min(limit, 20))
        candidate_limit = max(
            result_limit,
            min(self.settings.retrieval_candidate_k, 200),
        )
        terms = expand_query(normalized_query)

        lexical_rows = (
            self._lexical_candidates(
                normalized_query,
                terms,
                limit=candidate_limit,
            )
            if selected_mode in {"hybrid", "fts"}
            else []
        )
        vector_rows = (
            self._vector_candidates(normalized_query, limit=candidate_limit)
            if selected_mode in {"hybrid", "vector"}
            else []
        )

        candidates: dict[str, dict[str, Any]] = {}
        for rank, row in enumerate(lexical_rows, 1):
            chunk_id = str(row["chunk_id"])
            candidates[chunk_id] = dict(row)
            candidates[chunk_id]["fts_rank"] = rank
        for rank, row in enumerate(vector_rows, 1):
            chunk_id = str(row["chunk_id"])
            existing = candidates.setdefault(chunk_id, dict(row))
            existing["vector_score"] = row.get("vector_score")
            existing["vector_rank"] = rank

        rrf_k = self.settings.retrieval_rrf_k
        for chunk_id, row in candidates.items():
            fts_rank = row.get("fts_rank")
            vector_rank = row.get("vector_rank")
            if selected_mode == "fts":
                fused_score = 1.0 / (rrf_k + int(fts_rank or candidate_limit + 1))
            elif selected_mode == "vector":
                fused_score = 1.0 / (
                    rrf_k + int(vector_rank or candidate_limit + 1)
                )
            else:
                fused_score = 0.0
                if fts_rank:
                    fused_score += self.settings.retrieval_fts_weight / (
                        rrf_k + int(fts_rank)
                    )
                if vector_rank:
                    fused_score += self.settings.retrieval_vector_weight / (
                        rrf_k + int(vector_rank)
                    )
            heading_text = " ".join(row.get("heading_path") or []).lower()
            title_text = str(row.get("title") or "").lower()
            rerank_bonus = 0.0
            if self.settings.reranker_enabled:
                matched = sum(
                    1
                    for term in terms
                    if term.lower() in title_text or term.lower() in heading_text
                )
                rerank_bonus = min(matched, 5) * 0.0001
            row["chunk_id"] = chunk_id
            row["document_id"] = str(row["document_id"])
            row["fts_score"] = float(row.get("fts_score") or 0)
            vector_score = row.get("vector_score")
            row["vector_score"] = (
                round(float(vector_score), 8) if vector_score is not None else None
            )
            row["lexical_hits"] = int(row.get("lexical_hits") or 0)
            row["title_hits"] = int(row.get("title_hits") or 0)
            row["rrf_score"] = round(float(fused_score), 8)
            row["rerank_score"] = round(float(fused_score + rerank_bonus), 8)
            row["retrieval_mode"] = selected_mode
            row["embedding_provider"] = self.embedder.provider
            row["potential_injection"] = contains_prompt_injection(row["content"])

        ranked = sorted(
            candidates.values(),
            key=lambda row: (
                row["rerank_score"],
                row["title_hits"],
                row["lexical_hits"],
                row["vector_score"] if row["vector_score"] is not None else -1.0,
            ),
            reverse=True,
        )[:result_limit]
        duration_ms = (time.perf_counter() - started) * 1000
        if log_search:
            self._log_search(
                query=normalized_query,
                mode=selected_mode,
                terms=terms,
                lexical_count=len(lexical_rows),
                vector_count=len(vector_rows),
                rows=ranked,
                duration_ms=duration_ms,
            )
        return ranked

    def _log_search(
        self,
        *,
        query: str,
        mode: RetrievalMode,
        terms: list[str],
        lexical_count: int,
        vector_count: int,
        rows: list[dict[str, Any]],
        duration_ms: float,
    ) -> None:
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO knowledge.search_logs(
                            query, retrieval_mode, expanded_terms,
                            lexical_candidate_count, vector_candidate_count,
                            result_chunk_ids, duration_ms
                        )
                        VALUES (
                            :query, :mode, CAST(:terms AS text[]),
                            :lexical_count, :vector_count,
                            CAST(:result_ids AS uuid[]), :duration_ms
                        )
                        """
                    ),
                    {
                        "query": query,
                        "mode": mode,
                        "terms": terms,
                        "lexical_count": lexical_count,
                        "vector_count": vector_count,
                        "result_ids": [UUID(row["chunk_id"]) for row in rows],
                        "duration_ms": duration_ms,
                    },
                )
        except SQLAlchemyError:
            # Retrieval must remain available while an older database is being migrated.
            return

    def status(self) -> dict[str, Any]:
        with self.engine.connect() as connection:
            counts = connection.execute(
                text(
                    """
                    SELECT
                        count(*) AS chunk_count,
                        count(embedding) AS embedded_chunk_count,
                        count(DISTINCT document_id) AS document_count
                    FROM knowledge.chunks
                    """
                )
            ).mappings().one()
            statuses = connection.execute(
                text(
                    """
                    SELECT status, count(*) AS count
                    FROM knowledge.documents
                    GROUP BY status
                    ORDER BY status
                    """
                )
            ).mappings()
        chunk_count = int(counts["chunk_count"])
        embedded_count = int(counts["embedded_chunk_count"])
        return {
            "retrieval_mode": self.settings.retrieval_mode,
            "embedding_provider": self.embedder.provider,
            "embedding_dimensions": self.embedder.dimensions,
            "document_count": int(counts["document_count"]),
            "chunk_count": chunk_count,
            "embedded_chunk_count": embedded_count,
            "embedding_coverage": (
                round(embedded_count / chunk_count, 4) if chunk_count else 0.0
            ),
            "document_statuses": {
                str(row["status"]): int(row["count"]) for row in statuses
            },
            "rrf": {
                "k": self.settings.retrieval_rrf_k,
                "fts_weight": self.settings.retrieval_fts_weight,
                "vector_weight": self.settings.retrieval_vector_weight,
            },
            "reranker_enabled": self.settings.reranker_enabled,
        }

    def list_documents(self) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT
                        d.id,
                        d.title,
                        d.source_type,
                        d.source_url,
                        d.status,
                        d.metadata,
                        d.updated_at,
                        count(c.id) AS chunk_count,
                        count(c.embedding) AS embedded_chunk_count
                    FROM knowledge.documents d
                    LEFT JOIN knowledge.chunks c ON c.document_id = d.id
                    GROUP BY d.id
                    ORDER BY d.title
                    """
                )
            ).mappings()
            return [dict(row) for row in rows]
