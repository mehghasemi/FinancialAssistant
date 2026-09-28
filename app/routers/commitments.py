from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, HTTPException

from ..calendar import format_jalali_date, format_jalali_datetime
from ..database import allocate_unique_code, connection, write_audit_log
from ..schemas import (
    CommitmentGroupUpdate, CommitmentInput, CommitmentUpdate,
    InstallmentUpdate, PaymentInput, PaymentUpdate,
)
from ..utils import (
    commitment_title_key, installment_rows, month_bounds_or_error,
    normalize_text, planned_installments, serialize,
)

router = APIRouter(prefix="/api", tags=["commitments"])


@router.post("/commitments", status_code=201)
def create_commitment(payload: CommitmentInput):
    due_dates = planned_installments(payload)
    planned_total = payload.installment_amount * payload.installment_count
    if payload.repayment_amount is not None and payload.repayment_amount != planned_total:
        raise HTTPException(422, "مبلغ بازپرداخت باید برابر با جمع اقساط باشد.")
    with connection() as db:
        unique_code = allocate_unique_code(db)
        cursor = db.execute(
            "INSERT INTO commitments(title, kind, total_amount, repayment_amount, unique_code) VALUES (?, ?, ?, ?, ?)",
            (payload.title.strip(), payload.kind.strip(), payload.total_amount, payload.repayment_amount, unique_code),
        )
        commitment_id = cursor.lastrowid
        db.executemany(
            "INSERT INTO installments(commitment_id, due_date, amount) VALUES (?, ?, ?)",
            ((commitment_id, due.isoformat(), payload.installment_amount) for due in due_dates),
        )
        write_audit_log(db, "create", "commitment", commitment_id, payload.title)
    return {"id": commitment_id, "installment_count": payload.installment_count, "unique_code": unique_code}


@router.post("/commitments/preview")
def preview_commitment(payload: CommitmentInput):
    due_dates = planned_installments(payload)
    planned_total = payload.installment_amount * payload.installment_count
    if payload.repayment_amount is not None and payload.repayment_amount != planned_total:
        raise HTTPException(422, "مبلغ بازپرداخت باید برابر با جمع اقساط باشد.")
    return {
        "planned_total": planned_total,
        "first_due_date": format_jalali_date(due_dates[0]),
        "last_due_date": format_jalali_date(due_dates[-1]),
        "installments": [
            {"number": index + 1, "due_date": format_jalali_date(due), "amount": payload.installment_amount}
            for index, due in enumerate(due_dates)
        ],
    }


@router.get("/commitments")
def commitment_list():
    with connection() as db:
        return [
            serialize(row)
            for row in db.execute(
                """SELECT c.id, c.unique_code, c.title, c.kind, c.total_amount, c.repayment_amount, COUNT(i.id) AS installment_count,
                          COALESCE(SUM(i.amount), 0) AS planned_amount,
                          COALESCE(SUM(p.payment_amount), 0) AS paid_amount,
                          MIN(CASE WHEN i.amount > COALESCE(p.payment_amount, 0) THEN i.due_date END) AS next_unpaid_due_date,
                          MAX(i.due_date) AS last_due_date,
                          GROUP_CONCAT(i.due_date) AS due_dates
                   FROM commitments c
                   LEFT JOIN installments i ON i.commitment_id = c.id
                   LEFT JOIN (
                       SELECT installment_id, SUM(amount) AS payment_amount
                       FROM payments GROUP BY installment_id
                   ) p ON p.installment_id = i.id
                   GROUP BY c.id
                   ORDER BY c.id DESC"""
            ).fetchall()
        ]


@router.patch("/commitments/{commitment_id}")
def update_commitment(commitment_id: int, payload: CommitmentUpdate):
    with connection() as db:
        existing = db.execute(
            "SELECT id, title, kind, total_amount, repayment_amount, installment_count, interval_months FROM commitments WHERE id = ?", (commitment_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(404, "تعهد پیدا نشد.")
        
        # اگر installment_count یا repayment_amount تغییر کند: اقساط را بازسازی کن
        if payload.installment_count is not None or payload.repayment_amount is not None:
            # ابتدا تاریخ اولین قسط موجود را بگیر (اگه payload ارسال نکرده)
            old_installments = db.execute(
                "SELECT due_date FROM installments WHERE commitment_id = ? ORDER BY due_date LIMIT 1", (commitment_id,)
            ).fetchone()
            first_due_date = payload.first_due_date or (old_installments["due_date"] if old_installments else None)
            
            # حذف اقساط قدیمی
            db.execute("DELETE FROM installments WHERE commitment_id = ?", (commitment_id,))
            
            installment_count = payload.installment_count if payload.installment_count is not None else existing["installment_count"]
            repayment_amount = payload.repayment_amount if payload.repayment_amount is not None else existing["repayment_amount"]
            interval_months = payload.interval_months if payload.interval_months is not None else (existing["interval_months"] or 1)
            
            # ساخت اقساط جدید
            if first_due_date and installment_count and repayment_amount:
                from ..utils import add_months
                
                amount_per_installment = repayment_amount // installment_count
                remainder = repayment_amount % installment_count
                
                for i in range(installment_count):
                    # محاسبهٔ تاریخ قسط
                    due_date = add_months(first_due_date, i * interval_months)
                    
                    # مبلغ: اخرین قسط = remainder + amount_per_installment
                    amount = amount_per_installment + (remainder if i == installment_count - 1 else 0)
                    
                    db.execute(
                        "INSERT INTO installments (commitment_id, due_date, amount, source_key) VALUES (?, ?, ?, ?)",
                        (commitment_id, str(due_date), amount, f"patch-{commitment_id}-{i}")
                    )
        
        # فیلدهای تعهد را به‌روز کن
        db.execute(
            "UPDATE commitments SET title = ?, kind = ?, total_amount = ?, repayment_amount = ?, installment_count = ?, interval_months = ? WHERE id = ?",
            (
                payload.title,
                payload.kind,
                payload.total_amount,
                payload.repayment_amount if payload.repayment_amount is not None else existing["repayment_amount"],
                payload.installment_count if payload.installment_count is not None else existing["installment_count"],
                payload.interval_months if payload.interval_months is not None else (existing["interval_months"] or 1),
                commitment_id
            ),
        )
        write_audit_log(db, "update", "commitment", commitment_id, json.dumps({
            "before": dict(existing),
            "after": {
                "title": payload.title, "kind": payload.kind,
                "total_amount": payload.total_amount, "repayment_amount": payload.repayment_amount,
                "installment_count": payload.installment_count, "interval_months": payload.interval_months,
            }
        }, ensure_ascii=False))
    return {"id": commitment_id}


@router.patch("/commitments/{commitment_id}/group")
def update_commitment_group(commitment_id: int, payload: CommitmentGroupUpdate):
    with connection() as db:
        records = db.execute("SELECT id, title, kind, total_amount FROM commitments").fetchall()
        anchor = next((row for row in records if row["id"] == commitment_id), None)
        if anchor is None:
            raise HTTPException(404, "تعهد پیدا نشد.")
        key = commitment_title_key(anchor["title"])
        related = [row for row in records if commitment_title_key(row["title"]) == key]
        for row in related:
            db.execute("UPDATE commitments SET title = ?, kind = ? WHERE id = ?", (payload.title, payload.kind, row["id"]))
            write_audit_log(db, "update", "commitment", row["id"], json.dumps({
                "before": dict(row),
                "after": {"title": payload.title, "kind": payload.kind, "total_amount": row["total_amount"]},
                "scope": "group",
            }, ensure_ascii=False))
    return {"id": commitment_id, "updated_count": len(related)}


@router.get("/commitment-filters")
def commitment_filters():
    with connection() as db:
        return [
            serialize(row)
            for row in db.execute(
                """SELECT c.title, c.total_amount, COUNT(DISTINCT c.id) AS commitment_count,
                          COUNT(i.id) AS installment_count
                   FROM commitments c
                   LEFT JOIN installments i ON i.commitment_id = c.id
                   GROUP BY c.title, c.total_amount
                   ORDER BY c.title, c.total_amount"""
            ).fetchall()
        ]


@router.get("/installments")
def installments(
    month: str | None = None,
    status: Literal["paid", "partial", "overdue", "unpaid"] | None = None,
    commitment_id: int | None = None,
    commitment_title: str | None = None,
    commitment_total: int | None = None,
    commitment_total_missing: bool = False,
    search: str | None = None,
):
    clauses, params = [], []
    if month:
        start, end = month_bounds_or_error(month)
        clauses.append("i.due_date >= ? AND i.due_date < ?")
        params.extend((start, end))
    if commitment_id:
        clauses.append("i.commitment_id = ?")
        params.append(commitment_id)
    if commitment_title and normalize_text(commitment_title):
        clauses.append("c.title = ?")
        params.append(normalize_text(commitment_title))
        if commitment_total_missing:
            clauses.append("c.total_amount IS NULL")
        elif commitment_total is not None:
            clauses.append("c.total_amount = ?")
            params.append(commitment_total)
    if search and normalize_text(search):
        clauses.append("c.title LIKE ?")
        params.append(f"%{normalize_text(search)}%")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    result = installment_rows(where, tuple(params))
    if status:
        result = [item for item in result if item["status"] == status]
    return result


@router.patch("/installments/{installment_id}")
def update_installment(installment_id: int, payload: InstallmentUpdate):
    with connection() as db:
        existing = db.execute("SELECT id, commitment_id, due_date, amount, note FROM installments WHERE id = ?", (installment_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "قسط پیدا نشد.")
        paid_amount = db.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM payments WHERE installment_id = ?", (installment_id,)
        ).fetchone()["total"]
        if payload.amount < paid_amount:
            raise HTTPException(422, "مبلغ قسط نمی‌تواند کمتر از پرداخت‌های ثبت‌شده باشد.")
        planned_amount = db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM installments WHERE commitment_id = ?", (existing["commitment_id"],)
        ).fetchone()[0]
        repayment_amount = db.execute(
            "SELECT repayment_amount FROM commitments WHERE id = ?", (existing["commitment_id"],)
        ).fetchone()[0]
        new_total = planned_amount - existing["amount"] + payload.amount
        if repayment_amount is not None and new_total != repayment_amount:
            raise HTTPException(422, "جمع اقساط باید برابر با مبلغ بازپرداخت تعهد باقی بماند.")
        db.execute(
            "UPDATE installments SET due_date = ?, amount = ?, note = ? WHERE id = ?",
            (payload.due_date.isoformat(), payload.amount, payload.note, installment_id),
        )
        write_audit_log(db, "update", "installment", installment_id, json.dumps({
            "before": {"due_date": existing["due_date"], "amount": existing["amount"], "note": existing["note"]},
            "after": {"due_date": payload.due_date.isoformat(), "amount": payload.amount, "note": payload.note}
        }, ensure_ascii=False))
    return {"id": installment_id}


@router.get("/installments/{installment_id}/details")
def installment_details(installment_id: int):
    with connection() as db:
        row = db.execute("SELECT commitment_id FROM installments WHERE id = ?", (installment_id,)).fetchone()
        if not row:
            raise HTTPException(404, "قسط پیدا نشد.")
        payments = [serialize(item) for item in db.execute(
            "SELECT p.id, p.amount, p.paid_on, p.account_id, p.note, a.name AS account_name "
            "FROM payments p LEFT JOIN accounts a ON a.id = p.account_id WHERE p.installment_id = ? ORDER BY p.id", (installment_id,)
        ).fetchall()]
        logs = [serialize(item) for item in db.execute(
            "SELECT id, action, resource_type, details, created_at FROM audit_logs "
            "WHERE (resource_type = 'installment' AND resource_id = ?) "
            "OR (resource_type = 'commitment' AND resource_id = ?) "
            "OR (resource_type = 'payment' AND (resource_id IN (SELECT id FROM payments WHERE installment_id = ?) "
            "OR (json_valid(details) AND json_extract(details, '$.installment_id') = ?) "
            "OR details = ?)) ORDER BY id DESC",
            (installment_id, row["commitment_id"], installment_id, installment_id, f"installment:{installment_id}")
        ).fetchall()]
        for log in logs:
            try:
                log["details"] = json.loads(log["details"])
            except (ValueError, TypeError):
                pass
        for payment in payments:
            payment["paid_on"] = format_jalali_date(payment["paid_on"])
        for log in logs:
            log["created_at"] = format_jalali_datetime(log["created_at"])
    return {"payments": payments, "history": logs}


@router.post("/payments", status_code=201)
def create_payment(payload: PaymentInput):
    with connection() as db:
        installment = db.execute("SELECT amount FROM installments WHERE id = ?", (payload.installment_id,)).fetchone()
        if not installment:
            raise HTTPException(404, "سررسید پیدا نشد.")
        paid = db.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM payments WHERE installment_id = ?", (payload.installment_id,)).fetchone()["total"]
        if paid + payload.amount > installment["amount"]:
            raise HTTPException(422, "مبلغ پرداخت از ماندهٔ سررسید بیشتر است.")
        cursor = db.execute(
            "INSERT INTO payments(installment_id, amount, paid_on, account_id, note) VALUES (?, ?, ?, ?, ?)",
            (payload.installment_id, payload.amount, payload.paid_on.isoformat(), payload.account_id, payload.note.strip()),
        )
        write_audit_log(db, "create", "payment", cursor.lastrowid, json.dumps({
            "installment_id": payload.installment_id, "amount": payload.amount, "paid_on": payload.paid_on.isoformat()
        }, ensure_ascii=False))
        return {"id": cursor.lastrowid}


@router.patch("/payments/{payment_id}")
def update_payment(payment_id: int, payload: PaymentUpdate):
    with connection() as db:
        existing = db.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "پرداخت پیدا نشد.")
        installment = db.execute("SELECT amount FROM installments WHERE id = ?", (existing["installment_id"],)).fetchone()
        paid_other = db.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE installment_id = ? AND id != ?", (existing["installment_id"], payment_id)).fetchone()[0]
        if paid_other + payload.amount > installment["amount"]:
            raise HTTPException(422, "مجموع پرداخت‌ها از مبلغ قسط بیشتر می‌شود.")
        if payload.account_id is not None and not db.execute("SELECT 1 FROM accounts WHERE id = ?", (payload.account_id,)).fetchone():
            raise HTTPException(422, "حساب انتخاب‌شده پیدا نشد.")
        db.execute("UPDATE payments SET amount = ?, paid_on = ?, account_id = ?, note = ? WHERE id = ?",
                   (payload.amount, payload.paid_on.isoformat(), payload.account_id, payload.note.strip(), payment_id))
        write_audit_log(db, "update", "payment", payment_id, json.dumps({
            "installment_id": existing["installment_id"],
            "before": {key: existing[key] for key in ("amount", "paid_on", "account_id", "note")},
            "after": {"amount": payload.amount, "paid_on": payload.paid_on.isoformat(), "account_id": payload.account_id, "note": payload.note.strip()}
        }, ensure_ascii=False))
    return {"id": payment_id}


@router.delete("/payments/{payment_id}")
def delete_payment(payment_id: int):
    with connection() as db:
        existing = db.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "پرداخت پیدا نشد.")
        write_audit_log(db, "delete", "payment", payment_id, json.dumps({
            "installment_id": existing["installment_id"],
            "before": {key: existing[key] for key in ("amount", "paid_on", "account_id", "note")}
        }, ensure_ascii=False))
        db.execute("DELETE FROM payments WHERE id = ?", (payment_id,))
    return {"id": payment_id}
