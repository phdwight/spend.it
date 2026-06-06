"""Pydantic schemas for API I/O."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ~1 MB cap on the base64 data URL we'll accept. The frontend resizes images
# well below this; the limit just guards against accidental huge uploads.
_MAX_PHOTO_LEN = 1_500_000


class ExpenseCreate(BaseModel):
    amount: float = Field(gt=0, description="Spending amount, must be positive")
    category: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=255)
    photo: str | None = Field(
        default=None,
        max_length=_MAX_PHOTO_LEN,
        description="Optional base64 data URL of a small attached image.",
    )
    spent_at: date | None = Field(
        default=None,
        description="Date the spending occurred. Defaults to today if omitted.",
    )

    @field_validator("photo")
    @classmethod
    def _validate_photo(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not v.startswith("data:image/"):
            raise ValueError("photo must be a data:image/* URL")
        return v


class ExpenseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount: float
    category: str
    note: str | None
    photo: str | None = None
    spent_at: date
    created_at: datetime


class CategoryTotal(BaseModel):
    category: str
    total: float


class PeriodTotal(BaseModel):
    period: str  # "YYYY-MM-DD" | "YYYY-MM" | "YYYY"
    total: float


class PeriodCategoryTotal(BaseModel):
    period: str
    category: str
    total: float


class SummaryReport(BaseModel):
    period: str  # "daily" | "monthly" | "yearly"
    by_category: list[CategoryTotal]
    by_period: list[PeriodTotal]
    by_period_category: list[PeriodCategoryTotal]
    grand_total: float
