from __future__ import annotations

from datetime import date
from fastapi import APIRouter, HTTPException, Query
from ..calendar import parse_jalali_date, format_jalali_date
from ..database import connection
from ..utils import month_bounds_or_error

router = APIRouter(prefix="/api", tags=["reports"])


def period_bounds(month, year, start_date, end_date):
    try:
        start, end = None, None
        if month:
            start, end = month_bounds_or_error(month)
        if year:
            ys, _ = month_bounds_or_error(f"{year}-01")
            ye, _ = month_bounds_or_error(f"{year + 1}-01")
            start, end = max(start or ys, ys), min(end or ye, ye)
        if start_date:
            value = parse_jalali_date(start_date).isoformat()
            start = max(start or value, value)
        if end_date:
            from datetime import timedelta
            value = (parse_jalali_date(end_date) + timedelta(days=1)).isoformat()
            end = min(end or value, value)
        if start and end and start >= end:
            raise ValueError("بازهٔ تاریخ معتبر نیست یا با ماه و سال انتخابی تداخل ندارد.")
        return start, end
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.get("/financial-report")
def financial_report(month: str | None = None, year: int | None = Query(None, ge=1200, le=1600),
                     start_date: str | None = None, end_date: str | None = None,
                     record_type: str = "", category: str = "", status: str = "", counterparty: str = "", search: str = "",
                     min_amount: int | None = Query(None, ge=0), max_amount: int | None = Query(None, ge=0)):
    if min_amount is not None and max_amount is not None and min_amount > max_amount:
        raise HTTPException(422, "حداقل مبلغ نباید از حداکثر بیشتر باشد.")
    if record_type not in ("", "income", "expense", "installment", "commitment"):
        raise HTTPException(422, "نوع رکورد معتبر نیست.")
    start, end = period_bounds(month, year, start_date, end_date)
    with connection() as db:
        rows = [dict(row) for row in db.execute("""SELECT t.id, t.occurred_on AS date, t.transaction_type AS record_type,
                COALESCE(NULLIF(t.title, ''), NULLIF(t.note, ''), 'تراکنش') AS title, COALESCE(c.name, '') AS category, t.amount, t.status, t.counterparty, t.note, t.payment_id
                FROM transactions t LEFT JOIN categories c ON c.id=t.category_id""")]
        installments = [dict(row) for row in db.execute("""SELECT i.id, i.commitment_id, i.due_date AS date, c.title, c.kind AS category,
            i.amount, i.note, COALESCE(p.paid,0) AS paid_amount,
            ROW_NUMBER() OVER (PARTITION BY i.commitment_id ORDER BY i.due_date,i.id) AS installment_number,
            COUNT(*) OVER (PARTITION BY i.commitment_id) AS installment_count
            FROM installments i JOIN commitments c ON c.id=i.commitment_id
            LEFT JOIN (SELECT installment_id,SUM(amount) AS paid FROM payments GROUP BY installment_id) p ON p.installment_id=i.id""")]
    today = date.today().isoformat()
    for item in installments:
        item.update(record_type="installment", counterparty="")
        item["remaining_amount"] = max(0, item["amount"] - item["paid_amount"])
        item["status"] = "paid" if not item["remaining_amount"] else "partial" if item["paid_amount"] else "overdue" if item["date"] < today else "unpaid"
    def matches(item):
        return ((not start or item["date"] >= start) and (not end or item["date"] < end)
                and (not category or category.casefold() in item["category"].casefold())
                and (not status or item["status"] == status)
                and (not counterparty or counterparty.casefold() in item["counterparty"].casefold())
                and (not search or search.casefold() in (item["title"] + " " + item["note"]).casefold())
                and (min_amount is None or item["amount"] >= min_amount)
                and (max_amount is None or item["amount"] <= max_amount))
    transactions = [item for item in rows if matches(item) and (not record_type or item["record_type"] == record_type)]
    installments = [item for item in installments if matches(item) and record_type in ("", "installment", "commitment")]
    groups = {}
    for item in installments:
        group = groups.setdefault(item["commitment_id"], dict(id=item["commitment_id"], commitment_id=item["commitment_id"], record_type="commitment", title=item["title"], category=item["category"], date=item["date"], amount=0, paid_amount=0, remaining_amount=0, installment_count=0, note="تجمیع اقساط مطابق فیلتر؛ در جمع دوباره محاسبه نمی‌شود", counterparty=""))
        for key in ("amount", "paid_amount", "remaining_amount"):
            group[key] += item[key]
        group["date"] = min(group["date"], item["date"])
        group["installment_count"] += 1
    for group in groups.values():
        group["status"] = "paid" if not group["remaining_amount"] else "partial" if group["paid_amount"] else "overdue" if group["date"] < today else "unpaid"
    active = [item for item in transactions if item["status"] != "cancelled" and not item.get("payment_id")]
    def total(kind, paid_only=False):
        return sum(item["amount"] for item in active if item["record_type"] == kind and (not paid_only or item["status"] == "paid"))
    summary = dict(income=total("income"), expense=total("expense"), net=total("income")-total("expense"),
                   realized_net=total("income",True)-total("expense",True),
                   installment_total=sum(item["amount"] for item in installments),
                   commitment_total=sum(group["amount"] for group in groups.values()),
                   remaining_installments=sum(item["remaining_amount"] for item in installments),
                   income_count=sum(item["record_type"] == "income" for item in active), expense_count=sum(item["record_type"] == "expense" for item in active),
                   installment_count=len(installments), commitment_count=len(groups))
    summary["total_expenses"] = summary["expense"] + summary["installment_total"]
    summary["monthly_balance"] = summary["income"] - summary["total_expenses"]
    summary["after_installments"] = summary["net"] - summary["installment_total"]
    result = transactions + ([] if record_type == "commitment" else installments) + ([] if record_type == "installment" else list(groups.values()))
    result.sort(key=lambda item: (item["date"], item["record_type"], item["id"]))
    for item in result:
        item["date"] = format_jalali_date(item["date"])
    return {"items": result, "summary": summary}
