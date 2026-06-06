"""Data access layer for expenses (Single Responsibility: persistence)."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Expense
from app.schemas import CategoryTotal, ExpenseCreate, PeriodCategoryTotal, PeriodTotal

# SQLite strftime format strings keyed by reporting period.
_PERIOD_FORMATS: dict[str, str] = {
    "daily": "%Y-%m-%d",
    "monthly": "%Y-%m",
    "yearly": "%Y",
}


def current_period_range(period: str, today: date | None = None) -> tuple[date, date]:
    """Return the inclusive (start, end) date window for the *current* period."""
    today = today or date.today()
    if period == "daily":
        return today, today
    if period == "monthly":
        first = today.replace(day=1)
        if today.month == 12:
            next_first = date(today.year + 1, 1, 1)
        else:
            next_first = date(today.year, today.month + 1, 1)
        return first, next_first - timedelta(days=1)
    if period == "yearly":
        return date(today.year, 1, 1), date(today.year, 12, 31)
    raise ValueError(f"Unsupported period '{period}'")


def create_expense(session: Session, data: ExpenseCreate) -> Expense:
    expense = Expense(
        amount=data.amount,
        category=data.category.strip(),
        note=data.note.strip() if data.note else None,
        photo=data.photo or None,
        spent_at=data.spent_at or date.today(),
    )
    session.add(expense)
    session.commit()
    session.refresh(expense)
    return expense


def list_expenses(
    session: Session,
    start: date | None = None,
    end: date | None = None,
    limit: int = 200,
) -> list[Expense]:
    stmt = select(Expense)
    if start is not None:
        stmt = stmt.where(Expense.spent_at >= start)
    if end is not None:
        stmt = stmt.where(Expense.spent_at <= end)
    stmt = stmt.order_by(Expense.spent_at.desc(), Expense.id.desc()).limit(limit)
    return list(session.scalars(stmt).all())


def delete_expense(session: Session, expense_id: int) -> bool:
    result = session.execute(delete(Expense).where(Expense.id == expense_id))
    session.commit()
    return result.rowcount > 0


def totals_by_category(
    session: Session, start: date | None = None, end: date | None = None
) -> list[CategoryTotal]:
    stmt = select(Expense.category, func.sum(Expense.amount))
    if start is not None:
        stmt = stmt.where(Expense.spent_at >= start)
    if end is not None:
        stmt = stmt.where(Expense.spent_at <= end)
    stmt = stmt.group_by(Expense.category).order_by(func.sum(Expense.amount).desc())
    return [CategoryTotal(category=row[0], total=float(row[1])) for row in session.execute(stmt)]


def totals_by_period(
    session: Session,
    period: str,
    start: date | None = None,
    end: date | None = None,
) -> list[PeriodTotal]:
    if period not in _PERIOD_FORMATS:
        raise ValueError(f"Unsupported period '{period}'")

    bucket = func.strftime(_PERIOD_FORMATS[period], Expense.spent_at).label("bucket")
    stmt = select(bucket, func.sum(Expense.amount))
    if start is not None:
        stmt = stmt.where(Expense.spent_at >= start)
    if end is not None:
        stmt = stmt.where(Expense.spent_at <= end)
    stmt = stmt.group_by(bucket).order_by(bucket)
    return [PeriodTotal(period=row[0], total=float(row[1])) for row in session.execute(stmt)]


def totals_by_period_and_category(
    session: Session,
    period: str,
    start: date | None = None,
    end: date | None = None,
) -> list[PeriodCategoryTotal]:
    """Per-bucket × per-category totals (for stacked bar charts)."""
    if period not in _PERIOD_FORMATS:
        raise ValueError(f"Unsupported period '{period}'")

    bucket = func.strftime(_PERIOD_FORMATS[period], Expense.spent_at).label("bucket")
    stmt = select(bucket, Expense.category, func.sum(Expense.amount))
    if start is not None:
        stmt = stmt.where(Expense.spent_at >= start)
    if end is not None:
        stmt = stmt.where(Expense.spent_at <= end)
    stmt = stmt.group_by(bucket, Expense.category).order_by(bucket, Expense.category)
    return [
        PeriodCategoryTotal(period=row[0], category=row[1], total=float(row[2]))
        for row in session.execute(stmt)
    ]


def grand_total(
    session: Session, start: date | None = None, end: date | None = None
) -> float:
    stmt = select(func.coalesce(func.sum(Expense.amount), 0.0))
    if start is not None:
        stmt = stmt.where(Expense.spent_at >= start)
    if end is not None:
        stmt = stmt.where(Expense.spent_at <= end)
    return float(session.scalar(stmt) or 0.0)
