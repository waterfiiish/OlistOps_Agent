from datetime import date

import pytest

from packages.analytics.schemas import (
    DateRange,
    DeliveryPerformanceRequest,
    FreightAnalysisRequest,
    GeographyPerformanceRequest,
    MonthlyTrendRequest,
    PaymentAnalysisRequest,
)
from packages.analytics.service import AnalyticsService
from packages.database.connection import check_database
from packages.retrieval.service import RetrievalService

pytestmark = pytest.mark.integration


def test_database_and_pgvector_are_ready() -> None:
    status = check_database()
    assert status["database"] == "olistops"
    assert status["version"].startswith("16.")
    assert status["vector_enabled"] == "true"


def test_july_2018_seller_ranking_is_reproducible() -> None:
    result = AnalyticsService().get_delivery_performance(
        DeliveryPerformanceRequest(
            start_date=date(2018, 7, 1),
            end_date=date(2018, 7, 31),
            group_by="seller_id",
            min_orders=20,
            top_k=3,
        )
    )
    assert result.rows[0]["seller_id"] == "06a2c3af7b3aee5d69171b0e14f0ee87"
    assert result.rows[0]["order_count"] == 71
    assert result.rows[0]["late_order_count"] == 30
    assert result.rows[0]["late_rate"] == pytest.approx(0.42254)


def test_overall_delivery_query_has_one_group() -> None:
    result = AnalyticsService().get_delivery_performance(
        DeliveryPerformanceRequest(
            start_date=date(2018, 7, 1),
            end_date=date(2018, 7, 31),
            group_by="overall",
            min_orders=1,
            top_k=1,
        )
    )
    assert len(result.rows) == 1
    assert result.rows[0]["group_key"] == "overall"
    assert result.rows[0]["eligible_delivery_count"] > 0


def test_policy_retrieval_returns_seed_chunks() -> None:
    rows = RetrievalService().search("配送 延期 包装", limit=5)
    assert rows
    assert all("chunk_id" in row for row in rows)
    assert all(row["retrieval_mode"] == "hybrid" for row in rows)
    assert any(row["fts_rank"] for row in rows)
    assert any(row["vector_rank"] for row in rows)


def test_hybrid_retrieval_embeddings_cover_all_chunks() -> None:
    status = RetrievalService().status()
    assert status["embedding_provider"] == "local_hash"
    assert status["chunk_count"] == 60
    assert status["embedded_chunk_count"] == status["chunk_count"]
    assert status["embedding_coverage"] == 1.0


def test_operations_overview_preserves_status_denominator() -> None:
    result = AnalyticsService().get_operations_overview(
        DateRange(start_date=date(2018, 1, 1), end_date=date(2018, 8, 31))
    )
    assert result.denominator == sum(row["order_count"] for row in result.rows)
    assert {row["order_status"] for row in result.rows} >= {"delivered", "canceled"}


def test_monthly_trend_is_chronological() -> None:
    result = AnalyticsService().get_monthly_trend(
        MonthlyTrendRequest(
            start_date=date(2018, 1, 1),
            end_date=date(2018, 8, 31),
        )
    )
    months = [row["month"] for row in result.rows]
    assert len(months) == 8
    assert months == sorted(months)
    assert all(row["eligible_delivery_count"] >= row["late_order_count"] for row in result.rows)


def test_geography_performance_has_bounded_states() -> None:
    result = AnalyticsService().get_geography_performance(
        GeographyPerformanceRequest(
            start_date=date(2018, 1, 1),
            end_date=date(2018, 8, 31),
            min_orders=100,
            top_k=27,
        )
    )
    assert 1 <= len(result.rows) <= 27
    assert all(row["order_count"] >= 100 for row in result.rows)


def test_overall_freight_share_is_a_ratio() -> None:
    result = AnalyticsService().get_freight_analysis(
        FreightAnalysisRequest(
            start_date=date(2018, 1, 1),
            end_date=date(2018, 8, 31),
            group_by="overall",
        )
    )
    assert len(result.rows) == 1
    assert 0 < result.value < 1


def test_payment_mix_reports_credit_card() -> None:
    result = AnalyticsService().get_payment_analysis(
        PaymentAnalysisRequest(
            start_date=date(2018, 1, 1),
            end_date=date(2018, 8, 31),
        )
    )
    assert result.denominator > 0
    assert any(row["payment_type"] == "credit_card" for row in result.rows)
    assert sum(row["payment_value_share"] for row in result.rows) == pytest.approx(1)
