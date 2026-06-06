"""Integration tests for the FastAPI HTTP endpoints."""
from __future__ import annotations

from datetime import date, timedelta


def test_health_returns_ok(client) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ---------- POST /api/expenses ----------


def test_create_expense_returns_201_and_payload(client) -> None:
    r = client.post(
        "/api/expenses",
        json={"amount": 12.5, "category": "Food", "note": "lunch", "spent_at": "2026-05-01"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["amount"] == 12.5
    assert body["category"] == "Food"
    assert body["note"] == "lunch"
    assert body["spent_at"] == "2026-05-01"
    assert isinstance(body["id"], int)
    assert "created_at" in body


def test_create_expense_defaults_spent_at_to_today(client) -> None:
    r = client.post("/api/expenses", json={"amount": 5, "category": "Coffee"})
    assert r.status_code == 201
    assert r.json()["spent_at"] == date.today().isoformat()


def test_create_expense_rejects_non_positive_amount(client) -> None:
    r = client.post("/api/expenses", json={"amount": 0, "category": "X"})
    assert r.status_code == 422

    r = client.post("/api/expenses", json={"amount": -1, "category": "X"})
    assert r.status_code == 422


def test_create_expense_rejects_missing_category(client) -> None:
    r = client.post("/api/expenses", json={"amount": 1.0, "category": ""})
    assert r.status_code == 422


def test_create_expense_rejects_invalid_date(client) -> None:
    r = client.post(
        "/api/expenses", json={"amount": 1.0, "category": "X", "spent_at": "not-a-date"}
    )
    assert r.status_code == 422


# ---------- GET /api/expenses ----------


def _seed(client, items: list[dict]) -> None:
    for it in items:
        assert client.post("/api/expenses", json=it).status_code == 201


def test_list_expenses_empty_returns_empty_list(client) -> None:
    r = client.get("/api/expenses")
    assert r.status_code == 200
    assert r.json() == []


def test_list_expenses_filters_by_range(client) -> None:
    _seed(
        client,
        [
            {"amount": 1.0, "category": "A", "spent_at": "2026-01-01"},
            {"amount": 2.0, "category": "B", "spent_at": "2026-02-15"},
            {"amount": 3.0, "category": "C", "spent_at": "2026-03-31"},
        ],
    )
    r = client.get("/api/expenses", params={"start": "2026-02-01", "end": "2026-03-01"})
    assert r.status_code == 200
    assert [e["category"] for e in r.json()] == ["B"]


def test_list_expenses_respects_limit(client) -> None:
    _seed(
        client,
        [
            {"amount": float(i + 1), "category": f"C{i}", "spent_at": f"2026-01-0{i + 1}"}
            for i in range(5)
        ],
    )
    r = client.get("/api/expenses", params={"limit": 2})
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_list_expenses_rejects_invalid_limit(client) -> None:
    assert client.get("/api/expenses", params={"limit": 0}).status_code == 422
    assert client.get("/api/expenses", params={"limit": 9999}).status_code == 422


# ---------- DELETE /api/expenses/{id} ----------


def test_delete_expense_removes_record(client) -> None:
    created = client.post(
        "/api/expenses", json={"amount": 1.0, "category": "X", "spent_at": "2026-01-01"}
    ).json()
    r = client.delete(f"/api/expenses/{created['id']}")
    assert r.status_code == 204
    assert client.get("/api/expenses").json() == []


def test_delete_expense_missing_returns_404(client) -> None:
    assert client.delete("/api/expenses/99999").status_code == 404


# ---------- GET /api/reports/summary ----------


def test_summary_aggregates_by_category_and_period(client) -> None:
    """When no range is given, by_category is scoped to the current period
    window while by_period spans the full dataset."""
    today = date.today()
    last_year = date(today.year - 1, 1, 15)

    _seed(
        client,
        [
            {"amount": 10, "category": "Food", "spent_at": today.isoformat()},
            {"amount": 5, "category": "Food", "spent_at": today.isoformat()},
            {"amount": 30, "category": "Transport", "spent_at": today.isoformat()},
            {"amount": 99, "category": "Travel", "spent_at": last_year.isoformat()},
        ],
    )

    daily = client.get("/api/reports/summary", params={"period": "daily"}).json()
    assert daily["period"] == "daily"
    # Categories + grand_total are scoped to today only.
    assert daily["grand_total"] == 45.0
    assert {(c["category"], c["total"]) for c in daily["by_category"]} == {
        ("Food", 15.0),
        ("Transport", 30.0),
    }
    # Bar chart still shows all data, bucketed by day.
    bar_keys = {p["period"] for p in daily["by_period"]}
    assert today.isoformat() in bar_keys
    assert last_year.isoformat() in bar_keys


def test_summary_categories_scope_to_current_period(client) -> None:
    today = date.today()
    last_year_same_month = date(today.year - 1, today.month, 1)

    _seed(
        client,
        [
            {"amount": 100, "category": "Food", "spent_at": today.isoformat()},
            {"amount": 200, "category": "Food", "spent_at": last_year_same_month.isoformat()},
        ],
    )

    # Daily: only today counts.
    daily = client.get("/api/reports/summary", params={"period": "daily"}).json()
    assert daily["grand_total"] == 100.0

    # Monthly: this month -> only today's record (last year is excluded).
    monthly = client.get("/api/reports/summary", params={"period": "monthly"}).json()
    assert monthly["grand_total"] == 100.0
    assert [c["category"] for c in monthly["by_category"]] == ["Food"]

    # Yearly: this year -> only today's record.
    yearly = client.get("/api/reports/summary", params={"period": "yearly"}).json()
    assert yearly["grand_total"] == 100.0


def test_summary_categories_empty_when_no_records_in_period(client) -> None:
    """Past records exist but none in the current daily window -> empty cats."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    _seed(client, [{"amount": 50, "category": "Food", "spent_at": yesterday}])

    daily = client.get("/api/reports/summary", params={"period": "daily"}).json()
    assert daily["grand_total"] == 0.0
    assert daily["by_category"] == []
    # Bar chart still includes yesterday.
    assert any(p["period"] == yesterday for p in daily["by_period"])


def test_summary_empty_db_returns_zero(client) -> None:
    body = client.get("/api/reports/summary", params={"period": "daily"}).json()
    assert body == {
        "period": "daily",
        "by_category": [],
        "by_period": [],
        "by_period_category": [],
        "grand_total": 0.0,
    }


def test_summary_rejects_unknown_period(client) -> None:
    r = client.get("/api/reports/summary", params={"period": "weekly"})
    assert r.status_code == 422


def test_summary_explicit_range_overrides_period_scope(client) -> None:
    """When start/end is given, it applies to categories AND bars (no auto-scope)."""
    today = date.today()
    old = date(today.year - 1, 1, 15)
    _seed(
        client,
        [
            {"amount": 10, "category": "A", "spent_at": old.isoformat()},
            {"amount": 20, "category": "B", "spent_at": today.isoformat()},
        ],
    )

    body = client.get(
        "/api/reports/summary",
        params={"period": "daily", "start": old.isoformat(), "end": old.isoformat()},
    ).json()
    # Explicit range wins -> only the old record is included.
    assert body["grand_total"] == 10.0
    assert [c["category"] for c in body["by_category"]] == ["A"]
    assert [p["period"] for p in body["by_period"]] == [old.isoformat()]


def test_summary_includes_by_period_category_for_drilldown(client) -> None:
    """The frontend uses by_period_category to render stacked bars and to drill
    the doughnut into a specific bucket on click."""
    _seed(
        client,
        [
            {"amount": 10, "category": "Food", "spent_at": "2026-01-15"},
            {"amount": 5, "category": "Transport", "spent_at": "2026-01-20"},
            {"amount": 30, "category": "Food", "spent_at": "2026-02-10"},
            {"amount": 7, "category": "Transport", "spent_at": "2026-02-12"},
        ],
    )

    body = client.get(
        "/api/reports/summary",
        params={"period": "monthly", "start": "2026-01-01", "end": "2026-02-28"},
    ).json()

    rows = {(r["period"], r["category"]): r["total"] for r in body["by_period_category"]}
    assert rows == {
        ("2026-01", "Food"): 10.0,
        ("2026-01", "Transport"): 5.0,
        ("2026-02", "Food"): 30.0,
        ("2026-02", "Transport"): 7.0,
    }
    # Sums per bucket match the flat by_period series.
    flat = {p["period"]: p["total"] for p in body["by_period"]}
    assert flat == {"2026-01": 15.0, "2026-02": 37.0}
