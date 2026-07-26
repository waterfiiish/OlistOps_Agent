from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

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
from packages.database.connection import get_engine


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date,)):
        return value.isoformat()
    return value


def _rows(result: Any) -> list[dict[str, Any]]:
    return [
        {key: _json_value(value) for key, value in row.items()}
        for row in result.mappings().all()
    ]


class AnalyticsService:
    """Schema-constrained analytics over MART views only."""

    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or get_engine()

    @staticmethod
    def _date_params(request: DateRange) -> dict[str, Any]:
        return {
            "start_date": request.start_date,
            "end_exclusive": request.end_date + timedelta(days=1),
        }

    def _freshness(self) -> str | None:
        with self.engine.connect() as connection:
            value = connection.execute(
                text("SELECT max(purchased_at)::date FROM mart.mart_order_fulfillment")
            ).scalar_one_or_none()
        return value.isoformat() if value else None

    def get_sales_summary(self, request: DateRange) -> MetricResult:
        sql = text(
            """
            SELECT
                count(DISTINCT order_id) AS order_count,
                sum(item_value)::numeric(16, 2) AS gmv_proxy,
                avg(item_value)::numeric(16, 2) AS avg_order_value,
                (
                    sum(freight_value) /
                    nullif(sum(item_value + freight_value), 0)
                )::numeric(10, 5) AS freight_share,
                avg(review_score)::numeric(5, 2) AS avg_review_score
            FROM mart.mart_order_fulfillment
            WHERE purchased_at >= :start_date
              AND purchased_at < :end_exclusive
              AND order_status = 'delivered'
            """
        )
        with self.engine.connect() as connection:
            rows = _rows(connection.execute(sql, self._date_params(request)))
        row = rows[0]
        return MetricResult(
            metric_name="sales_summary",
            value=row["gmv_proxy"],
            denominator=row["order_count"],
            filters={
                "start_date": request.start_date.isoformat(),
                "end_date": request.end_date.isoformat(),
                "order_status": "delivered",
            },
            definition=(
                "GMV proxy=sum(item price); average order value is calculated at order grain"
            ),
            rows=rows,
            data_freshness=self._freshness(),
            warnings=["GMV proxy is not accounting revenue."],
        )

    def get_operations_overview(self, request: DateRange) -> MetricResult:
        sql = text(
            """
            WITH grouped AS (
                SELECT
                    coalesce(order_status, 'unknown') AS order_status,
                    count(DISTINCT order_id) AS order_count,
                    sum(item_value)::numeric(16, 2) AS item_value,
                    sum(freight_value)::numeric(16, 2) AS freight_value,
                    avg(review_score)::numeric(5, 2) AS avg_review_score
                FROM mart.mart_order_fulfillment
                WHERE purchased_at >= :start_date
                  AND purchased_at < :end_exclusive
                GROUP BY coalesce(order_status, 'unknown')
            )
            SELECT
                order_status,
                order_count,
                (
                    order_count::numeric / nullif(sum(order_count) OVER (), 0)
                )::numeric(10, 5) AS order_share,
                item_value,
                freight_value,
                avg_review_score
            FROM grouped
            ORDER BY order_count DESC, order_status
            """
        )
        with self.engine.connect() as connection:
            rows = _rows(connection.execute(sql, self._date_params(request)))
        total_orders = sum(row["order_count"] for row in rows)
        exception_orders = sum(
            row["order_count"]
            for row in rows
            if row["order_status"] in {"canceled", "unavailable"}
        )
        return MetricResult(
            metric_name="operations_overview",
            value=total_orders,
            numerator=exception_orders,
            denominator=total_orders,
            filters={
                "start_date": request.start_date.isoformat(),
                "end_date": request.end_date.isoformat(),
            },
            definition=(
                "order status distribution at order grain; exception orders are "
                "canceled + unavailable"
            ),
            rows=rows,
            data_freshness=self._freshness(),
            warnings=[
                "Order status describes the historical snapshot in the public dataset."
            ],
        )

    def get_monthly_trend(self, request: MonthlyTrendRequest) -> MetricResult:
        delivered_filter = "AND order_status = 'delivered'" if request.delivered_only else ""
        sql = text(
            f"""
            SELECT
                date_trunc('month', purchased_at)::date AS month,
                count(DISTINCT order_id) AS order_count,
                count(DISTINCT order_id) FILTER (WHERE order_status = 'delivered')
                    AS delivered_order_count,
                sum(item_value)::numeric(16, 2) AS gmv_proxy,
                sum(freight_value)::numeric(16, 2) AS freight_value,
                count(DISTINCT order_id) FILTER (WHERE is_late IS NOT NULL)
                    AS eligible_delivery_count,
                count(DISTINCT order_id) FILTER (WHERE is_late) AS late_order_count,
                (
                    count(DISTINCT order_id) FILTER (WHERE is_late)::numeric /
                    nullif(
                        count(DISTINCT order_id) FILTER (WHERE is_late IS NOT NULL),
                        0
                    )
                )::numeric(10, 5) AS late_rate,
                avg(delivery_days) FILTER (WHERE order_status = 'delivered')
                    ::numeric(10, 3) AS avg_delivery_days,
                avg(review_score)::numeric(5, 2) AS avg_review_score
            FROM mart.mart_order_fulfillment
            WHERE purchased_at >= :start_date
              AND purchased_at < :end_exclusive
              {delivered_filter}
            GROUP BY date_trunc('month', purchased_at)::date
            ORDER BY month
            """
        )
        with self.engine.connect() as connection:
            rows = _rows(connection.execute(sql, self._date_params(request)))
        return MetricResult(
            metric_name="monthly_operations_trend",
            value=len(rows),
            denominator=sum(row["order_count"] for row in rows),
            filters={
                "start_date": request.start_date.isoformat(),
                "end_date": request.end_date.isoformat(),
                "grain": "month",
                "delivered_only": request.delivered_only,
            },
            definition=(
                "monthly order-grain trend; GMV proxy=sum(item price), "
                "late rate keeps its eligible denominator"
            ),
            rows=rows,
            data_freshness=self._freshness(),
            warnings=[
                "The first and last month may be partial depending on the selected dates.",
                "GMV proxy is not accounting revenue.",
            ],
        )

    def get_geography_performance(
        self, request: GeographyPerformanceRequest
    ) -> MetricResult:
        delivered_filter = "AND order_status = 'delivered'" if request.delivered_only else ""
        sql = text(
            f"""
            SELECT
                coalesce(customer_state, 'unknown') AS customer_state,
                count(DISTINCT order_id) AS order_count,
                count(DISTINCT order_id) FILTER (WHERE is_late IS NOT NULL)
                    AS eligible_delivery_count,
                count(DISTINCT order_id) FILTER (WHERE is_late) AS late_order_count,
                (
                    count(DISTINCT order_id) FILTER (WHERE is_late)::numeric /
                    nullif(
                        count(DISTINCT order_id) FILTER (WHERE is_late IS NOT NULL),
                        0
                    )
                )::numeric(10, 5) AS late_rate,
                avg(late_days) FILTER (WHERE is_late)::numeric(10, 3) AS avg_late_days,
                avg(delivery_days)::numeric(10, 3) AS avg_delivery_days,
                avg(review_score)::numeric(5, 2) AS avg_review_score,
                sum(item_value)::numeric(16, 2) AS gmv_proxy
            FROM mart.mart_order_fulfillment
            WHERE purchased_at >= :start_date
              AND purchased_at < :end_exclusive
              {delivered_filter}
            GROUP BY coalesce(customer_state, 'unknown')
            HAVING count(DISTINCT order_id) >= :min_orders
            ORDER BY late_rate DESC NULLS LAST, order_count DESC
            LIMIT :top_k
            """
        )
        params = self._date_params(request) | {
            "min_orders": request.min_orders,
            "top_k": request.top_k,
        }
        with self.engine.connect() as connection:
            rows = _rows(connection.execute(sql, params))
        return MetricResult(
            metric_name="customer_state_delivery_performance",
            value=len(rows),
            denominator=sum(row["order_count"] for row in rows),
            filters={
                "start_date": request.start_date.isoformat(),
                "end_date": request.end_date.isoformat(),
                "min_orders": request.min_orders,
                "top_k": request.top_k,
                "delivered_only": request.delivered_only,
            },
            definition=(
                "delivery and review metrics grouped by anonymized customer state"
            ),
            rows=rows,
            data_freshness=self._freshness(),
            warnings=[
                "State-level differences are descriptive and do not identify root cause."
            ],
        )

    def get_freight_analysis(self, request: FreightAnalysisRequest) -> MetricResult:
        source_map = {
            "overall": (
                "mart.mart_order_fulfillment",
                "'overall'",
                "group_key",
                "",
            ),
            "customer_state": (
                "mart.mart_order_fulfillment",
                "coalesce(customer_state, 'unknown')",
                "customer_state",
                "GROUP BY coalesce(customer_state, 'unknown')",
            ),
            "category": (
                "mart.mart_category_order_fulfillment",
                "category",
                "category",
                "GROUP BY category",
            ),
        }
        source, group_expression, group_alias, group_clause = source_map[request.group_by]
        delivered_filter = "AND order_status = 'delivered'" if request.delivered_only else ""
        sql = text(
            f"""
            SELECT
                {group_expression} AS {group_alias},
                count(DISTINCT order_id) AS order_count,
                sum(item_value)::numeric(16, 2) AS item_value,
                sum(freight_value)::numeric(16, 2) AS freight_value,
                (
                    sum(freight_value) /
                    nullif(sum(item_value + freight_value), 0)
                )::numeric(10, 5) AS freight_share,
                (
                    sum(freight_value) / nullif(count(DISTINCT order_id), 0)
                )::numeric(16, 2) AS avg_freight_per_order,
                avg(review_score)::numeric(5, 2) AS avg_review_score,
                avg(is_late::integer) FILTER (WHERE is_late IS NOT NULL)
                    ::numeric(10, 5) AS late_rate
            FROM {source}
            WHERE purchased_at >= :start_date
              AND purchased_at < :end_exclusive
              {delivered_filter}
            {group_clause}
            HAVING count(DISTINCT order_id) >= :min_orders
            ORDER BY freight_share DESC NULLS LAST, order_count DESC
            LIMIT :top_k
            """
        )
        params = self._date_params(request) | {
            "min_orders": request.min_orders,
            "top_k": request.top_k,
        }
        with self.engine.connect() as connection:
            rows = _rows(connection.execute(sql, params))
        overall = request.group_by == "overall" and bool(rows)
        return MetricResult(
            metric_name="freight_cost_structure",
            value=rows[0]["freight_share"] if overall else None,
            denominator=rows[0]["order_count"] if overall else None,
            filters={
                "start_date": request.start_date.isoformat(),
                "end_date": request.end_date.isoformat(),
                "group_by": request.group_by,
                "min_orders": request.min_orders,
                "top_k": request.top_k,
                "delivered_only": request.delivered_only,
            },
            definition="freight share = freight / (item value + freight)",
            rows=rows,
            data_freshness=self._freshness(),
            warnings=[
                "Freight is an order/item allocation proxy and is not a carrier invoice."
            ],
        )

    def get_payment_analysis(self, request: PaymentAnalysisRequest) -> MetricResult:
        sql = text(
            """
            WITH grouped AS (
                SELECT
                    payment_type,
                    count(DISTINCT order_id) AS participating_order_count,
                    sum(payment_value)::numeric(16, 2) AS payment_value,
                    avg(max_installments)::numeric(10, 2) AS avg_max_installments,
                    avg(payment_sequence_count)::numeric(10, 2)
                        AS avg_payment_sequences
                FROM mart.mart_payment_analysis_base
                WHERE purchased_at >= :start_date
                  AND purchased_at < :end_exclusive
                GROUP BY payment_type
            )
            SELECT
                payment_type,
                participating_order_count,
                payment_value,
                (
                    payment_value / nullif(sum(payment_value) OVER (), 0)
                )::numeric(10, 5) AS payment_value_share,
                avg_max_installments,
                avg_payment_sequences
            FROM grouped
            ORDER BY payment_value DESC, payment_type
            LIMIT :top_k
            """
        )
        params = self._date_params(request) | {"top_k": request.top_k}
        with self.engine.connect() as connection:
            rows = _rows(connection.execute(sql, params))
            total_orders = connection.execute(
                text(
                    """
                    SELECT count(DISTINCT order_id)
                    FROM mart.mart_payment_analysis_base
                    WHERE purchased_at >= :start_date
                      AND purchased_at < :end_exclusive
                    """
                ),
                self._date_params(request),
            ).scalar_one()
        return MetricResult(
            metric_name="payment_method_mix",
            value=rows[0]["payment_type"] if rows else None,
            denominator=total_orders,
            filters={
                "start_date": request.start_date.isoformat(),
                "end_date": request.end_date.isoformat(),
                "top_k": request.top_k,
            },
            definition=(
                "payment value and participating-order distribution by payment type"
            ),
            rows=rows,
            data_freshness=self._freshness(),
            warnings=[
                "An order can use multiple payment types, so participating-order counts "
                "are not mutually exclusive.",
                "Payment value is a dataset field and is not a settled-cash ledger.",
            ],
        )

    def get_delivery_performance(
        self, request: DeliveryPerformanceRequest
    ) -> MetricResult:
        source_map = {
            "overall": (
                "mart.mart_order_fulfillment",
                "'overall'",
                "group_key",
                "",
            ),
            "seller_id": (
                "mart.mart_seller_order_fulfillment",
                "seller_id",
                "seller_id",
                "GROUP BY seller_id",
            ),
            "category": (
                "mart.mart_category_order_fulfillment",
                "category",
                "category",
                "GROUP BY category",
            ),
        }
        source, group_expression, group_alias, group_clause = source_map[request.group_by]
        delivered_filter = "AND order_status = 'delivered'" if request.delivered_only else ""
        sql = text(
            f"""
            SELECT
                {group_expression} AS {group_alias},
                count(DISTINCT order_id) AS order_count,
                count(DISTINCT order_id) FILTER (WHERE is_late IS NOT NULL)
                    AS eligible_delivery_count,
                count(DISTINCT order_id) FILTER (WHERE is_late) AS late_order_count,
                (
                    count(DISTINCT order_id) FILTER (WHERE is_late)::numeric /
                    nullif(
                        count(DISTINCT order_id) FILTER (WHERE is_late IS NOT NULL),
                        0
                    )
                )::numeric(10, 5) AS late_rate,
                avg(late_days) FILTER (WHERE is_late)::numeric(10, 3) AS avg_late_days,
                avg(review_score) FILTER (WHERE is_late)::numeric(5, 2)
                    AS late_avg_review_score,
                avg(review_score) FILTER (WHERE is_late = false)::numeric(5, 2)
                    AS on_time_avg_review_score
            FROM {source}
            WHERE purchased_at >= :start_date
              AND purchased_at < :end_exclusive
              {delivered_filter}
            {group_clause}
            HAVING count(DISTINCT order_id) >= :min_orders
            ORDER BY late_rate DESC NULLS LAST, order_count DESC
            LIMIT :top_k
            """
        )
        params = self._date_params(request) | {
            "min_orders": request.min_orders,
            "top_k": request.top_k,
        }
        with self.engine.connect() as connection:
            rows = _rows(connection.execute(sql, params))
        numerator = rows[0]["late_order_count"] if request.group_by == "overall" and rows else None
        denominator = (
            rows[0]["eligible_delivery_count"]
            if request.group_by == "overall" and rows
            else None
        )
        return MetricResult(
            metric_name="late_delivery_rate",
            value=rows[0]["late_rate"] if request.group_by == "overall" and rows else None,
            numerator=numerator,
            denominator=denominator,
            filters={
                "start_date": request.start_date.isoformat(),
                "end_date": request.end_date.isoformat(),
                "group_by": request.group_by,
                "min_orders": request.min_orders,
                "delivered_only": request.delivered_only,
            },
            definition=(
                "late delivered orders / delivered orders with both actual and estimated dates"
            ),
            rows=rows,
            data_freshness=self._freshness(),
        )

    def compare_late_vs_on_time_reviews(self, request: DateRange) -> MetricResult:
        sql = text(
            """
            SELECT
                CASE WHEN is_late THEN 'late' ELSE 'on_time' END AS delivery_group,
                count(DISTINCT order_id) AS reviewed_order_count,
                avg(review_score)::numeric(5, 2) AS avg_review_score,
                avg(late_days)::numeric(10, 3) AS avg_late_days
            FROM mart.mart_order_fulfillment
            WHERE purchased_at >= :start_date
              AND purchased_at < :end_exclusive
              AND order_status = 'delivered'
              AND is_late IS NOT NULL
              AND review_score IS NOT NULL
            GROUP BY is_late
            ORDER BY is_late DESC
            """
        )
        with self.engine.connect() as connection:
            rows = _rows(connection.execute(sql, self._date_params(request)))
        score_by_group = {row["delivery_group"]: row["avg_review_score"] for row in rows}
        difference = None
        if {"late", "on_time"} <= score_by_group.keys():
            difference = round(score_by_group["late"] - score_by_group["on_time"], 3)
        return MetricResult(
            metric_name="late_vs_on_time_review_score",
            value=difference,
            denominator=sum(row["reviewed_order_count"] for row in rows),
            filters={
                "start_date": request.start_date.isoformat(),
                "end_date": request.end_date.isoformat(),
                "order_status": "delivered",
            },
            definition="average review score(late) - average review score(on-time)",
            rows=rows,
            data_freshness=self._freshness(),
            warnings=["This comparison is associative and does not prove causality."],
        )

    def get_seller_diagnostic(self, request: SellerDiagnosticRequest) -> MetricResult:
        sql = text(
            """
            WITH target AS (
                SELECT
                    seller_id,
                    count(DISTINCT order_id) AS order_count,
                    sum(item_value)::numeric(16, 2) AS item_value,
                    avg(item_value)::numeric(16, 2) AS avg_order_value,
                    (
                        sum(freight_value) /
                        nullif(sum(item_value + freight_value), 0)
                    )::numeric(10, 5) AS freight_share,
                    avg(is_late::integer) FILTER (WHERE is_late IS NOT NULL)
                        ::numeric(10, 5) AS late_rate,
                    avg(review_score)::numeric(5, 2) AS avg_review_score
                FROM mart.mart_seller_order_fulfillment
                WHERE seller_id = :seller_id
                  AND purchased_at >= :start_date
                  AND purchased_at < :end_exclusive
                GROUP BY seller_id
            ),
            baseline AS (
                SELECT
                    avg(late_rate)::numeric(10, 5) AS baseline_late_rate,
                    avg(avg_review_score)::numeric(5, 2) AS baseline_review_score
                FROM (
                    SELECT
                        seller_id,
                        avg(is_late::integer) FILTER (WHERE is_late IS NOT NULL) AS late_rate,
                        avg(review_score) AS avg_review_score
                    FROM mart.mart_seller_order_fulfillment
                    WHERE purchased_at >= :start_date
                      AND purchased_at < :end_exclusive
                    GROUP BY seller_id
                    HAVING count(DISTINCT order_id) >= 5
                ) peer
            )
            SELECT target.*, baseline.*
            FROM target CROSS JOIN baseline
            """
        )
        params = self._date_params(request) | {"seller_id": request.seller_id}
        with self.engine.connect() as connection:
            rows = _rows(connection.execute(sql, params))
        if not rows:
            return MetricResult(
                metric_name="seller_diagnostic",
                filters={
                    "seller_id": request.seller_id,
                    "start_date": request.start_date.isoformat(),
                    "end_date": request.end_date.isoformat(),
                },
                definition="seller metrics compared with sellers having at least five orders",
                data_freshness=self._freshness(),
                warnings=["seller_id does not exist in the selected time range."],
            )
        return MetricResult(
            metric_name="seller_diagnostic",
            value=rows[0]["late_rate"],
            denominator=rows[0]["order_count"],
            filters={
                "seller_id": request.seller_id,
                "start_date": request.start_date.isoformat(),
                "end_date": request.end_date.isoformat(),
            },
            definition="seller metrics at order/seller grain; peer baseline requires >=5 orders",
            rows=rows,
            data_freshness=self._freshness(),
            warnings=["Peer baseline is descriptive and is not a causal benchmark."],
        )

    def search_review_samples(self, request: ReviewSampleRequest) -> MetricResult:
        late_filter = ""
        if request.late_only is True:
            late_filter = "AND is_late = true"
        elif request.late_only is False:
            late_filter = "AND is_late = false"
        sql = text(
            f"""
            SELECT
                review_id,
                order_id,
                review_score,
                is_late,
                late_days,
                left(regexp_replace(
                    coalesce(review_comment_message, ''),
                    E'[\\n\\r\\t]+',
                    ' ',
                    'g'
                ), 280) AS comment_excerpt
            FROM mart.mart_review_analysis_base
            WHERE purchased_at >= :start_date
              AND purchased_at < :end_exclusive
              AND review_score <= :max_score
              AND review_comment_message IS NOT NULL
              {late_filter}
            ORDER BY review_score ASC, review_created_at DESC
            LIMIT :limit
            """
        )
        params = self._date_params(request) | {
            "max_score": request.max_score,
            "limit": request.limit,
        }
        with self.engine.connect() as connection:
            rows = _rows(connection.execute(sql, params))
        return MetricResult(
            metric_name="low_score_review_samples",
            value=len(rows),
            denominator=len(rows),
            filters={
                "start_date": request.start_date.isoformat(),
                "end_date": request.end_date.isoformat(),
                "max_score": request.max_score,
                "late_only": request.late_only,
            },
            definition="bounded excerpts from reviews at or below max_score",
            rows=rows,
            data_freshness=self._freshness(),
            warnings=[
                "Only a bounded excerpt is returned; do not infer customer identity.",
                "Samples are evidence, not a prevalence estimate.",
            ],
        )
