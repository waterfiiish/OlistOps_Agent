from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class DateRange(BaseModel):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_order(self) -> DateRange:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class DeliveryPerformanceRequest(DateRange):
    group_by: Literal["overall", "seller_id", "category"] = "overall"
    min_orders: int = Field(default=1, ge=1, le=100_000)
    top_k: int = Field(default=10, ge=1, le=100)
    delivered_only: bool = True


class SellerDiagnosticRequest(DateRange):
    seller_id: str = Field(pattern=r"^[0-9a-f]{32}$")


class ReviewSampleRequest(DateRange):
    max_score: int = Field(default=2, ge=1, le=5)
    limit: int = Field(default=20, ge=1, le=100)
    late_only: bool | None = None


class MonthlyTrendRequest(DateRange):
    delivered_only: bool = False


class GeographyPerformanceRequest(DateRange):
    min_orders: int = Field(default=20, ge=1, le=100_000)
    top_k: int = Field(default=27, ge=1, le=100)
    delivered_only: bool = True


class FreightAnalysisRequest(DateRange):
    group_by: Literal["overall", "customer_state", "category"] = "overall"
    min_orders: int = Field(default=1, ge=1, le=100_000)
    top_k: int = Field(default=10, ge=1, le=100)
    delivered_only: bool = True


class PaymentAnalysisRequest(DateRange):
    top_k: int = Field(default=10, ge=1, le=20)


class MetricResult(BaseModel):
    metric_name: str
    value: float | int | str | None = None
    numerator: int | float | None = None
    denominator: int | float | None = None
    filters: dict[str, Any]
    definition: str
    rows: list[dict[str, Any]] = Field(default_factory=list)
    data_freshness: str | None = None
    warnings: list[str] = Field(default_factory=list)
