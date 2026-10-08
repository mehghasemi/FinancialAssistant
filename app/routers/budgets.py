from __future__ import annotations

import json
from fastapi import APIRouter, HTTPException
from ..database import connection, write_audit_log
from ..schemas import BudgetInput
from ..utils import month_bounds_or_error

router = APIRouter(prefix="/api", tags=["budgets"])


@router.get("/budgets")
def budgets(month: str):
    start, end = month_bounds_or_error(month)
    with connection() as db:
        limits = {row["category_id"]: row["amount"] for row in db.execute(
            "SELECT category_id,amount FROM monthly_budgets WHERE month=?", (month,))}
        totals = {row["category_id"]: dict(row) for row in db.execute("""
            SELECT category_id,
                SUM(CASE WHEN status='paid' THEN amount ELSE 0 END) AS spent,
                SUM(CASE WHEN status='unpaid' THEN amount ELSE 0 END) AS pending
            FROM transactions WHERE transaction_type='expense' AND payment_id IS NULL
                AND status!='cancelled' AND (CASE WHEN status='paid' THEN COALESCE(settled_on,occurred_on) ELSE occurred_on END)>=?
                AND (CASE WHEN status='paid' THEN COALESCE(settled_on,occurred_on) ELSE occurred_on END)<? GROUP BY category_id
            """, (start, end))}
        categories = [dict(row) for row in db.execute(
            "SELECT id,name FROM categories WHERE transaction_type='expense' ORDER BY name")]
    if None in totals:
        categories.append({"id": None, "name": "بدون دسته‌بندی"})
    items = []
    for category in categories:
        identifier = category["id"]
        spent = totals.get(identifier, {}).get("spent", 0)
        pending = totals.get(identifier, {}).get("pending", 0)
        limit = limits.get(identifier)
        items.append(dict(category_id=identifier, category=category["name"], amount=limit,
                          spent=spent, pending=pending,
                          remaining=None if limit is None else limit-spent,
                          available=None if limit is None else limit-spent-pending))
    budgeted = [item for item in items if item["amount"] is not None]
    summary = {key: sum(item[key] for item in budgeted)
               for key in ("amount", "spent", "pending", "remaining", "available")}
    summary["unbudgeted_expenses"] = sum(item["spent"]+item["pending"] for item in items if item["amount"] is None)
    return {"month": month, "items": items, "summary": summary}


@router.put("/budgets")
def save_budget(payload: BudgetInput):
    month_bounds_or_error(payload.month)
    with connection(write=True) as db:
        category = db.execute("SELECT transaction_type FROM categories WHERE id=?", (payload.category_id,)).fetchone()
        if not category or category[0] != "expense":
            raise HTTPException(422, "یک دسته‌بندی هزینه انتخاب کنید.")
        before = db.execute("SELECT * FROM monthly_budgets WHERE month=? AND category_id=?",
                            (payload.month, payload.category_id)).fetchone()
        db.execute("""INSERT INTO monthly_budgets(month,category_id,amount) VALUES (?,?,?)
            ON CONFLICT(month,category_id) DO UPDATE SET amount=excluded.amount""",
                   (payload.month, payload.category_id, payload.amount))
        write_audit_log(db, "update" if before else "create", "budget", payload.category_id,
                        json.dumps({"before":dict(before) if before else None,
                                    "after":payload.model_dump()}, ensure_ascii=False))
    return {"status": "saved"}


@router.delete("/budgets/{category_id}")
def delete_budget(category_id: int, month: str, confirm: bool = False):
    month_bounds_or_error(month)
    if not confirm:
        raise HTTPException(422, "حذف بودجه نیاز به تأیید دارد.")
    with connection(write=True) as db:
        before = db.execute("SELECT * FROM monthly_budgets WHERE month=? AND category_id=?", (month, category_id)).fetchone()
        if not before:
            raise HTTPException(404, "بودجه پیدا نشد.")
        db.execute("DELETE FROM monthly_budgets WHERE month=? AND category_id=?", (month, category_id))
        write_audit_log(db, "delete", "budget", category_id, json.dumps({"before":dict(before)}, ensure_ascii=False))
    return {"status": "deleted"}
