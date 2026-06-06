"""Unit tests for the repository (data-access) layer."""
from __future__ import annotations

from datetime import date

import pytest

from app import repository
from app.schemas import ExpenseCreate


def _make(session, amount: float, category: str, spent_at: date, note: str | None = None):
    return repository.create_expense(
        session,
        ExpenseCreate(amount=amount, category=category, note=note, spent_at=spent_at),
    )


def test_create_expense_persists_fields(db_session) -> None:
    expense = _make(db_session, 12.50, "Food", date(2026, 1, 5), note="lunch")
    assert expense.id is not None
    assert expense.amount == 12.50
    assert expense.category == "Food"
    assert expense.note == "lunch"
    assert expense.spent_at == date(2026, 1, 5)
    assert expense.created_at is not None


def test_create_expense_defaults_spent_at_to_today(db_session) -> None:
    expense = repository.create_expense(
        db_session, ExpenseCreate(amount=5.0, category="Coffee")
    )
    assert expense.spent_at == date.today()


def test_create_expense_strips_whitespace(db_session) -> None:
    expense = repository.create_expense(
        db_session,
        ExpenseCreate(amount=1.0, category="  Food  ", note="  hi  ", spent_at=date.today()),
    )
    assert expense.category == "Food"
    assert expense.note == "hi"


def test_list_expenses_returns_newest_first(db_session) -> None:
    _make(db_session, 1.0, "A", date(2026, 1, 1))
    _make(db_session, 2.0, "B", date(2026, 2, 1))
    _make(db_session, 3.0, "C", date(2026, 3, 1))

    rows = repository.list_expenses(db_session)
    assert [r.spent_at for r in rows] == [date(2026, 3, 1), date(2026, 2, 1), date(2026, 1, 1)]


def test_list_expenses_filters_by_date_range(db_session) -> None:
    _make(db_session, 1.0, "A", date(2026, 1, 1))
    _make(db_session, 2.0, "B", date(2026, 2, 15))
    _make(db_session, 3.0, "C", date(2026, 3, 31))

    rows = repository.list_expenses(db_session, start=date(2026, 2, 1), end=date(2026, 3, 1))
    assert [r.category for r in rows] == ["B"]


def test_list_expenses_respects_limit(db_session) -> None:
    for i in range(5):
        _make(db_session, 1.0, f"C{i}", date(2026, 1, i + 1))
    assert len(repository.list_expenses(db_session, limit=3)) == 3


def test_delete_expense_returns_true_when_removed(db_session) -> None:
    e = _make(db_session, 1.0, "X", date.today())
    assert repository.delete_expense(db_session, e.id) is True
    assert repository.list_expenses(db_session) == []


def test_delete_expense_returns_false_when_missing(db_session) -> None:
    assert repository.delete_expense(db_session, 9999) is False


def test_totals_by_category_sums_and_orders_desc(db_session) -> None:
    _make(db_session, 10.0, "Food", date(2026, 1, 1))
    _make(db_session, 5.0, "Food", date(2026, 1, 2))
    _make(db_session, 30.0, "Transport", date(2026, 1, 3))

    totals = repository.totals_by_category(db_session)
    assert [(t.category, t.total) for t in totals] == [
        ("Transport", 30.0),
        ("Food", 15.0),
    ]


@pytest.mark.parametrize(
    ("period", "expected"),
    [
        (
            "daily",
            [("2026-01-01", 10.0), ("2026-01-02", 5.0), ("2026-02-15", 30.0)],
        ),
        (
            "monthly",
            [("2026-01", 15.0), ("2026-02", 30.0)],
        ),
        (
            "yearly",
            [("2026", 45.0)],
        ),
    ],
)
def test_totals_by_period_buckets_correctly(db_session, period, expected) -> None:
    _make(db_session, 10.0, "Food", date(2026, 1, 1))
    _make(db_session, 5.0, "Food", date(2026, 1, 2))
    _make(db_session, 30.0, "Transport", date(2026, 2, 15))

    totals = repository.totals_by_period(db_session, period)
    assert [(t.period, t.total) for t in totals] == expected


def test_totals_by_period_rejects_unknown_period(db_session) -> None:
    with pytest.raises(ValueError):
        repository.totals_by_period(db_session, "weekly")


def test_grand_total_with_and_without_filters(db_session) -> None:
    _make(db_session, 10.0, "A", date(2026, 1, 1))
    _make(db_session, 20.0, "B", date(2026, 2, 1))

    assert repository.grand_total(db_session) == 30.0
    assert repository.grand_total(db_session, start=date(2026, 2, 1)) == 20.0
    assert repository.grand_total(db_session, end=date(2026, 1, 31)) == 10.0


def test_grand_total_empty_db_returns_zero(db_session) -> None:
    assert repository.grand_total(db_session) == 0.0


# ---------- current_period_range ----------


def test_current_period_range_daily() -> None:
    today = date(2026, 6, 15)
    assert repository.current_period_range("daily", today=today) == (today, today)


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2026, 6, 15), (date(2026, 6, 1), date(2026, 6, 30))),
        (date(2026, 2, 10), (date(2026, 2, 1), date(2026, 2, 28))),  # non-leap Feb
        (date(2024, 2, 10), (date(2024, 2, 1), date(2024, 2, 29))),  # leap Feb
        (date(2026, 12, 31), (date(2026, 12, 1), date(2026, 12, 31))),  # year wrap
        (date(2026, 1, 1), (date(2026, 1, 1), date(2026, 1, 31))),
    ],
)
def test_current_period_range_monthly(today, expected) -> None:
    assert repository.current_period_range("monthly", today=today) == expected


def test_current_period_range_yearly() -> None:
    today = date(2026, 6, 15)
    assert repository.current_period_range("yearly", today=today) == (
        date(2026, 1, 1),
        date(2026, 12, 31),
    )


def test_current_period_range_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        repository.current_period_range("weekly")


# ---------- totals_by_period_and_category ----------


def test_totals_by_period_and_category_groups_by_both(db_session) -> None:
    _make(db_session, 10.0, "Food", date(2026, 1, 15))
    _make(db_session, 5.0, "Food", date(2026, 1, 20))
    _make(db_session, 7.0, "Transport", date(2026, 1, 20))
    _make(db_session, 30.0, "Food", date(2026, 2, 10))

    rows = repository.totals_by_period_and_category(db_session, "monthly")
    as_set = {(r.period, r.category, r.total) for r in rows}
    assert as_set == {
        ("2026-01", "Food", 15.0),
        ("2026-01", "Transport", 7.0),
        ("2026-02", "Food", 30.0),
    }


def test_totals_by_period_and_category_respects_range(db_session) -> None:
    _make(db_session, 10.0, "Food", date(2026, 1, 15))
    _make(db_session, 30.0, "Food", date(2026, 2, 10))

    rows = repository.totals_by_period_and_category(
        db_session, "monthly", start=date(2026, 2, 1)
    )
    assert [(r.period, r.category, r.total) for r in rows] == [("2026-02", "Food", 30.0)]


def test_totals_by_period_and_category_rejects_unknown_period(db_session) -> None:
    with pytest.raises(ValueError):
        repository.totals_by_period_and_category(db_session, "weekly")


def test_totals_by_period_and_category_empty_db(db_session) -> None:
    assert repository.totals_by_period_and_category(db_session, "daily") == []
