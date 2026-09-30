from __future__ import annotations

from datetime import date, timedelta

import jdatetime
from fastapi import APIRouter, Query

from ..calendar import jalali_month_label, parse_jalali_date
from ..database import connection
from ..utils import installment_rows, month_bounds_or_error

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def dashboard(month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$")):
    today_jalali = jdatetime.date.fromgregorian(date=date.today())
    selected_month = month or f"{today_jalali.year:04d}-{today_jalali.month:02d}"
    start, end = month_bounds_or_error(selected_month)
    installment_data = installment_rows("WHERE i.due_date >= ? AND i.due_date < ?", (start, end))
    with connection() as db:
        transaction_data = db.execute(
            """SELECT transaction_type, COALESCE(SUM(amount), 0) AS total
               FROM transactions WHERE occurred_on >= ? AND occurred_on < ? GROUP BY transaction_type""",
            (start, end),
        ).fetchall()

    totals = {row["transaction_type"]: row["total"] for row in transaction_data}
    planned = sum(item["amount"] for item in installment_data)
    remaining = sum(item["remaining_amount"] for item in installment_data)
    today = date.today()
    action_items = [item for item in installment_rows("WHERE i.due_date <= ?", ((today + timedelta(days=7)).isoformat(),)) if item["remaining_amount"] > 0]
    for item in action_items:
        due_date = parse_jalali_date(item["due_date"])
        jalali = jdatetime.date.fromgregorian(date=due_date)
        item["due_month_label"] = jalali_month_label(f"{jalali.year:04d}-{jalali.month:02d}")
        item["days_overdue"] = (today - due_date).days
    action_items.sort(key=lambda item: (parse_jalali_date(item["due_date"]), item["id"]))
    due = [item for item in action_items if item["days_overdue"] >= 0]
    overdue = [item for item in due if item["days_overdue"] > 0]
    current_month = f"{today_jalali.year:04d}-{today_jalali.month:02d}"
    current_start, current_end = month_bounds_or_error(current_month)
    current = installment_rows("WHERE i.due_date >= ? AND i.due_date < ?", (current_start, current_end))
    return {
        "month": selected_month,
        "month_label": jalali_month_label(selected_month),
        "income": totals.get("income", 0),
        "expense": totals.get("expense", 0),
        "planned_commitments": planned,
        "paid_commitments": sum(item["paid_amount"] for item in installment_data),
        "remaining_commitments": remaining,
        "overdue_commitments": sum(item["remaining_amount"] for item in overdue),
        "upcoming": due,
        "open_count": sum(item["remaining_amount"] > 0 for item in installment_data),
        "overdue_installments": overdue,
        "today_installments": [item for item in action_items if item["days_overdue"] == 0],
        "next_week_installments": [item for item in action_items if item["days_overdue"] < 0],
        "current_month": current_month,
        "current_month_label": jalali_month_label(current_month),
        "current_installments": current,
    }
