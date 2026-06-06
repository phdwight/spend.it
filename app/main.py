"""FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app import repository
from app.database import get_session, init_db
from app.schemas import ExpenseCreate, ExpenseRead, SummaryReport

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="spend.it", version="1.0.0", lifespan=lifespan)


# ---------- API ----------


@app.post(
    "/api/expenses",
    response_model=ExpenseRead,
    status_code=status.HTTP_201_CREATED,
)
def create_expense(
    payload: ExpenseCreate, session: Session = Depends(get_session)
) -> ExpenseRead:
    expense = repository.create_expense(session, payload)
    return ExpenseRead.model_validate(expense)


@app.get("/api/expenses", response_model=list[ExpenseRead])
def list_expenses(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    session: Session = Depends(get_session),
) -> list[ExpenseRead]:
    rows = repository.list_expenses(session, start=start, end=end, limit=limit)
    return [ExpenseRead.model_validate(r) for r in rows]


@app.delete("/api/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(expense_id: int, session: Session = Depends(get_session)) -> None:
    if not repository.delete_expense(session, expense_id):
        raise HTTPException(status_code=404, detail="Expense not found")


@app.get("/api/reports/summary", response_model=SummaryReport)
def summary(
    period: Literal["daily", "monthly", "yearly"] = "daily",
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    session: Session = Depends(get_session),
) -> SummaryReport:
    # When no explicit range is given, scope the category breakdown and the
    # headline total to the *current* period (today / this month / this year)
    # so they adjust as the user toggles. The trend bar chart still spans the
    # full dataset to give long-range context.
    if start is None and end is None:
        cat_start, cat_end = repository.current_period_range(period)
    else:
        cat_start, cat_end = start, end

    return SummaryReport(
        period=period,
        by_category=repository.totals_by_category(session, cat_start, cat_end),
        by_period=repository.totals_by_period(session, period, start, end),
        by_period_category=repository.totals_by_period_and_category(
            session, period, start, end
        ),
        grand_total=repository.grand_total(session, cat_start, cat_end),
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------- Static / PWA ----------

# Serve the SPA shell at root and the service worker at a stable URL.
@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/sw.js", include_in_schema=False)
def service_worker() -> FileResponse:
    return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
