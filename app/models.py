"""ORM models."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Optional small thumbnail image stored as a base64 data URL.
    # Resized client-side before upload, so payloads stay compact.
    photo: Mapped[str | None] = mapped_column(Text, nullable=True)
    spent_at: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
