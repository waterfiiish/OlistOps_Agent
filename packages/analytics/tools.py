from __future__ import annotations

from packages.analytics.schemas import (
    DateRange,
    DeliveryPerformanceRequest,
    FreightAnalysisRequest,
    GeographyPerformanceRequest,
    MonthlyTrendRequest,
    PaymentAnalysisRequest,
    ReviewSampleRequest,
    SellerDiagnosticRequest,
)
from packages.analytics.service import AnalyticsService
from packages.tools.registry import PermissionLevel, ToolDefinition, ToolRegistry


def build_analytics_registry(service: AnalyticsService | None = None) -> ToolRegistry:
    analytics = service or AnalyticsService()
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="olist.get_sales_summary",
            description=(
                "Return delivered-order volume, GMV proxy, order value, freight share and rating "
                "for an inclusive purchase-date range."
            ),
            input_model=DateRange,
            permission=PermissionLevel.READ,
            handler=analytics.get_sales_summary,
        )
    )
    registry.register(
        ToolDefinition(
            name="olist.get_delivery_performance",
            description=(
                "Calculate late-delivery rate with numerator, denominator, sample threshold and "
                "optional grouping by seller or category. Dates filter purchase time."
            ),
            input_model=DeliveryPerformanceRequest,
            permission=PermissionLevel.READ,
            handler=analytics.get_delivery_performance,
        )
    )
    registry.register(
        ToolDefinition(
            name="olist.get_operations_overview",
            description=(
                "Return order-status distribution, exception volume, value, freight and "
                "review score for an inclusive purchase-date range."
            ),
            input_model=DateRange,
            permission=PermissionLevel.READ,
            handler=analytics.get_operations_overview,
        )
    )
    registry.register(
        ToolDefinition(
            name="olist.get_monthly_trend",
            description=(
                "Return monthly order, GMV proxy, freight, delivery, late-rate and review "
                "trends while retaining the eligible-delivery denominator."
            ),
            input_model=MonthlyTrendRequest,
            permission=PermissionLevel.READ,
            handler=analytics.get_monthly_trend,
        )
    )
    registry.register(
        ToolDefinition(
            name="olist.get_geography_performance",
            description=(
                "Compare delivery, review and GMV-proxy performance by anonymized customer "
                "state with minimum-sample and top-k controls."
            ),
            input_model=GeographyPerformanceRequest,
            permission=PermissionLevel.READ,
            handler=analytics.get_geography_performance,
        )
    )
    registry.register(
        ToolDefinition(
            name="olist.get_freight_analysis",
            description=(
                "Analyze freight share and freight per order overall or grouped by customer "
                "state or product category."
            ),
            input_model=FreightAnalysisRequest,
            permission=PermissionLevel.READ,
            handler=analytics.get_freight_analysis,
        )
    )
    registry.register(
        ToolDefinition(
            name="olist.get_payment_analysis",
            description=(
                "Return payment-method value mix, participating order count and installment "
                "characteristics for an inclusive purchase-date range."
            ),
            input_model=PaymentAnalysisRequest,
            permission=PermissionLevel.READ,
            handler=analytics.get_payment_analysis,
        )
    )
    registry.register(
        ToolDefinition(
            name="olist.compare_late_vs_on_time_reviews",
            description=(
                "Compare average review score for late and on-time delivered orders. "
                "The result is associative, not causal."
            ),
            input_model=DateRange,
            permission=PermissionLevel.READ,
            handler=analytics.compare_late_vs_on_time_reviews,
        )
    )
    registry.register(
        ToolDefinition(
            name="olist.get_seller_diagnostic",
            description=(
                "Validate a 32-character seller_id and return scale, value, freight, "
                "late-rate and rating metrics with a peer baseline."
            ),
            input_model=SellerDiagnosticRequest,
            permission=PermissionLevel.READ,
            handler=analytics.get_seller_diagnostic,
        )
    )
    registry.register(
        ToolDefinition(
            name="olist.search_review_samples",
            description=(
                "Return bounded anonymous low-score review excerpts and delivery features. "
                "Never returns customer identifiers."
            ),
            input_model=ReviewSampleRequest,
            permission=PermissionLevel.READ,
            handler=analytics.search_review_samples,
        )
    )
    return registry
