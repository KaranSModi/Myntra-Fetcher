"""Pydantic schemas for API requests and responses."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ProductResultStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class CategoryAd(BaseModel):
    product_id: str | None = None
    title: str | None = None
    price: float | int | None = None
    mrp: float | int | None = None
    rating: float | None = None
    rating_count: int | None = None
    image: str | None = None
    product_url: str | None = None
    is_sponsored: bool = True


class DeliveryResult(BaseModel):
    city: str
    pincode: str
    serviceable: bool | None = None
    delivery_text: str | None = None
    estimated_days: int | None = None
    error: str | None = None


class ProductData(BaseModel):
    product_id: str
    title: str | None = None
    description: str | None = None
    images: list[str] = Field(default_factory=list)
    price: float | int | None = None
    mrp: float | int | None = None
    rating: float | None = None
    rating_count: int | None = None
    category: str | None = None
    category_slug: str | None = None
    product_url: str | None = None
    category_url: str | None = None


class ProductFetchResult(BaseModel):
    product_id: str
    status: ProductResultStatus
    product: ProductData | None = None
    category_ads: list[CategoryAd] = Field(default_factory=list)
    delivery: list[DeliveryResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class JobSummary(BaseModel):
    job_id: str
    status: JobStatus
    total: int = 0
    processed: int = 0
    success_count: int = 0
    partial_count: int = 0
    failed_count: int = 0
    created_at: datetime
    completed_at: datetime | None = None
    error: str | None = None


class JobResponse(BaseModel):
    success: bool = True
    message: str = "Operation completed."
    data: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
