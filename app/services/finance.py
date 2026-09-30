from __future__ import annotations

import json
from datetime import date

from ..calendar import format_jalali_date
from ..database import allocate_unique_code, connection, write_audit_log
from ..schemas import (CommitmentGroupUpdate, CommitmentInput, CommitmentUpdate,
                       InstallmentUpdate, PaymentInput, PaymentUpdate)
from ..utils import add_months, commitment_title_key, planned_installments


class FinanceError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def installment_amounts(total: int, count: int, base: int | None = None) -> list[int]:
    if count < 1 or total < count:
        raise FinanceError(422, "مبلغ بازپرداخت باید برای همهٔ اقساط مبلغ مثبت ایجاد کند.")
    regular = base if base is not None else total // count
    last = total - regular * (count - 1)
    if regular < 1 or last < 1:
        raise FinanceError(422, "مبلغ اقساط عادی از بازپرداخت بیشتر است؛ مبلغ هر قسط یا تعداد را اصلاح کنید.")
    return [regular] * (count - 1) + [last]


def creation_schedule(payload: CommitmentInput):
    try:
        dates = planned_installments(payload)
    except (ValueError, OverflowError):
        raise FinanceError(422, "محدودهٔ تاریخ اقساط معتبر نیست.") from None
    total = payload.repayment_amount or payload.installment_amount * payload.installment_count
    amounts = installment_amounts(total, payload.installment_count, payload.installment_amount)
    return dates, amounts, total


def create_commitment(payload: CommitmentInput):
    due_dates, amounts, planned_total = creation_schedule(payload)
    with connection(write=True) as db:
        unique_code = allocate_unique_code(db)
        cursor = db.execute(
            "INSERT INTO commitments(title, kind, total_amount, repayment_amount, unique_code, interval_months) VALUES (?, ?, ?, ?, ?, ?)",
            (payload.title.strip(), payload.kind.strip(), payload.total_amount, planned_total, unique_code, payload.interval_months),
        )
        commitment_id = cursor.lastrowid
        db.executemany(
            "INSERT INTO installments(commitment_id, due_date, amount) VALUES (?, ?, ?)",
            ((commitment_id, due.isoformat(), amount) for due, amount in zip(due_dates, amounts)),
        )
        write_audit_log(db, "create", "commitment", commitment_id, json.dumps({"after": payload.model_dump(mode="json"), "unique_code": unique_code}, ensure_ascii=False))
    return {"id": commitment_id, "installment_count": payload.installment_count, "unique_code": unique_code}


def preview_commitment(payload: CommitmentInput):
    due_dates, amounts, planned_total = creation_schedule(payload)
    return {
        "planned_total": planned_total,
        "first_due_date": format_jalali_date(due_dates[0]),
        "last_due_date": format_jalali_date(due_dates[-1]),
        "installments": [
            {"number": index + 1, "due_date": format_jalali_date(due), "amount": amounts[index]}
            for index, due in enumerate(due_dates)
        ],
    }


def update_commitment(commitment_id: int, payload: CommitmentUpdate):
    with connection(write=True) as db:
        existing = db.execute("SELECT * FROM commitments WHERE id = ?", (commitment_id,)).fetchone()
        if existing is None:
            raise FinanceError(404, "تعهد پیدا نشد.")
        rows = db.execute(
            "SELECT * FROM installments WHERE commitment_id = ? ORDER BY due_date, id",
            (commitment_id,),
        ).fetchall()
        count = payload.installment_count if payload.installment_count is not None else len(rows)
        planned = sum(row["amount"] for row in rows)
        previous_total = existing["repayment_amount"] or planned
        total = (payload.repayment_amount if payload.repayment_amount is not None else
                 payload.installment_amount * count if payload.installment_amount is not None else previous_total)
        interval = payload.interval_months if payload.interval_months is not None else existing["interval_months"]
        first = payload.first_due_date or (date.fromisoformat(rows[0]["due_date"]) if rows else None)
        count_changed = count != len(rows)
        money_changed = (count_changed
                         or (payload.repayment_amount is not None and total != previous_total)
                         or (payload.installment_amount is not None and
                             (not rows or any(row["amount"] != payload.installment_amount for row in rows))))
        dates_changed = (count_changed
                         or (payload.interval_months is not None and interval != existing["interval_months"])
                         or (payload.first_due_date is not None and
                             (not rows or first.isoformat() != rows[0]["due_date"])))
        rebuild = money_changed or dates_changed
        if rebuild:
            if count < 1 or first is None:
                raise FinanceError(422, "تاریخ و تعداد اقساط باید معتبر باشند.")
            amounts = installment_amounts(total, count, payload.installment_amount) if money_changed else [row["amount"] for row in rows]
            if dates_changed:
                if interval is None:
                    raise FinanceError(422, "برای بازتنظیم سررسیدها، دورهٔ پرداخت را مشخص کنید.")
                try:
                    dates = [add_months(first, index * interval).isoformat() for index in range(count)]
                except (ValueError, OverflowError):
                    raise FinanceError(422, "محدودهٔ تاریخ اقساط معتبر نیست.") from None
            else:
                dates = [row["due_date"] for row in rows]
            paid = {row["installment_id"]: row["paid"] for row in db.execute(
                "SELECT p.installment_id, SUM(p.amount) AS paid FROM payments p "
                "JOIN installments i ON i.id = p.installment_id WHERE i.commitment_id = ? GROUP BY p.installment_id",
                (commitment_id,),
            )}
            for index, row in enumerate(rows):
                if index >= count and row["id"] in paid:
                    raise FinanceError(422, "کاهش تعداد اقساط باعث حذف قسط دارای پرداخت می‌شود؛ ابتدا برنامه را اصلاح کنید.")
                if index < count and amounts[index] < paid.get(row["id"], 0):
                    raise FinanceError(422, f"قسط {index + 1} با سررسید {format_jalali_date(row['due_date'])}: مبلغ جدید {amounts[index]:,} تومان از پرداخت ثبت‌شدهٔ {paid[row['id']]:,} تومان کمتر است.")
            # Update every surviving installment in place; payment IDs and dates never change.
            for index, (due, value) in enumerate(zip(dates, amounts)):
                if index < len(rows):
                    db.execute("UPDATE installments SET due_date = ?, amount = ? WHERE id = ?",
                               (due, value, rows[index]["id"]))
                else:
                    db.execute("INSERT INTO installments(commitment_id, due_date, amount) VALUES (?, ?, ?)",
                               (commitment_id, due, value))
            for row in rows[count:]:
                db.execute("DELETE FROM installments WHERE id = ?", (row["id"],))
        repayment = total if money_changed else (payload.repayment_amount if payload.repayment_amount is not None else existing["repayment_amount"])
        total_amount = payload.total_amount if "total_amount" in payload.model_fields_set else existing["total_amount"]
        db.execute(
            "UPDATE commitments SET title = ?, kind = ?, total_amount = ?, repayment_amount = ?, interval_months = ? WHERE id = ?",
            (payload.title, payload.kind, total_amount, repayment,
             interval if rebuild or payload.interval_months is not None else existing["interval_months"], commitment_id),
        )
        after = dict(db.execute("SELECT * FROM commitments WHERE id = ?", (commitment_id,)).fetchone())
        write_audit_log(db, "update", "commitment", commitment_id, json.dumps({
            "before": dict(existing), "after": after,
            "schedule_before": [dict(row) for row in rows] if rebuild else None,
            "schedule_after": [dict(row) for row in db.execute(
                "SELECT * FROM installments WHERE commitment_id = ? ORDER BY due_date, id", (commitment_id,)
            )] if rebuild else None,
        }, ensure_ascii=False))
    return {"id": commitment_id}


def update_commitment_group(commitment_id: int, payload: CommitmentGroupUpdate):
    with connection(write=True) as db:
        records = db.execute("SELECT id, title, kind, total_amount FROM commitments").fetchall()
        anchor = next((row for row in records if row["id"] == commitment_id), None)
        if anchor is None:
            raise FinanceError(404, "تعهد پیدا نشد.")
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


def update_installment(installment_id: int, payload: InstallmentUpdate):
    with connection(write=True) as db:
        existing = db.execute("SELECT id, commitment_id, due_date, amount, note FROM installments WHERE id = ?", (installment_id,)).fetchone()
        if not existing:
            raise FinanceError(404, "قسط پیدا نشد.")
        paid_amount = db.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM payments WHERE installment_id = ?", (installment_id,)
        ).fetchone()["total"]
        if payload.amount < paid_amount:
            raise FinanceError(422, "مبلغ قسط نمی‌تواند کمتر از پرداخت‌های ثبت‌شده باشد.")
        planned_amount = db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM installments WHERE commitment_id = ?", (existing["commitment_id"],)
        ).fetchone()[0]
        repayment_amount = db.execute(
            "SELECT repayment_amount FROM commitments WHERE id = ?", (existing["commitment_id"],)
        ).fetchone()[0]
        difference = payload.amount - existing["amount"]
        if difference:
            new_repayment = (repayment_amount if repayment_amount is not None else planned_amount) + difference
            db.execute("UPDATE commitments SET repayment_amount = ? WHERE id = ?",
                       (new_repayment, existing["commitment_id"]))
            write_audit_log(db, "update", "commitment", existing["commitment_id"], json.dumps({
                "installment_id": installment_id,
                "before": {"repayment_amount": repayment_amount},
                "after": {"repayment_amount": new_repayment},
            }, ensure_ascii=False))
        db.execute(
            "UPDATE installments SET due_date = ?, amount = ?, note = ? WHERE id = ?",
            (payload.due_date.isoformat(), payload.amount, payload.note, installment_id),
        )
        write_audit_log(db, "update", "installment", installment_id, json.dumps({
            "before": {"due_date": existing["due_date"], "amount": existing["amount"], "note": existing["note"]},
            "after": {"due_date": payload.due_date.isoformat(), "amount": payload.amount, "note": payload.note}
        }, ensure_ascii=False))
    return {"id": installment_id}


def create_payment(payload: PaymentInput):
    with connection(write=True) as db:
        if payload.account_id is not None and not db.execute("SELECT 1 FROM accounts WHERE id = ?", (payload.account_id,)).fetchone():
            raise FinanceError(422, "حساب انتخاب‌شده پیدا نشد.")
        installment = db.execute("SELECT amount FROM installments WHERE id = ?", (payload.installment_id,)).fetchone()
        if not installment:
            raise FinanceError(404, "سررسید پیدا نشد.")
        paid = db.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM payments WHERE installment_id = ?", (payload.installment_id,)).fetchone()["total"]
        if paid + payload.amount > installment["amount"]:
            raise FinanceError(422, "مبلغ پرداخت از ماندهٔ سررسید بیشتر است.")
        cursor = db.execute(
            "INSERT INTO payments(installment_id, amount, paid_on, account_id, note) VALUES (?, ?, ?, ?, ?)",
            (payload.installment_id, payload.amount, payload.paid_on.isoformat(), payload.account_id, payload.note.strip()),
        )
        write_audit_log(db, "create", "payment", cursor.lastrowid, json.dumps({
            "installment_id": payload.installment_id, "after": payload.model_dump(mode="json")
        }, ensure_ascii=False))
        return {"id": cursor.lastrowid}


def update_payment(payment_id: int, payload: PaymentUpdate):
    with connection(write=True) as db:
        existing = db.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
        if not existing:
            raise FinanceError(404, "پرداخت پیدا نشد.")
        installment = db.execute("SELECT amount FROM installments WHERE id = ?", (existing["installment_id"],)).fetchone()
        paid_other = db.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE installment_id = ? AND id != ?", (existing["installment_id"], payment_id)).fetchone()[0]
        if paid_other + payload.amount > installment["amount"]:
            raise FinanceError(422, "مجموع پرداخت‌ها از مبلغ قسط بیشتر می‌شود.")
        if payload.account_id is not None and not db.execute("SELECT 1 FROM accounts WHERE id = ?", (payload.account_id,)).fetchone():
            raise FinanceError(422, "حساب انتخاب‌شده پیدا نشد.")
        db.execute("UPDATE payments SET amount = ?, paid_on = ?, account_id = ?, note = ? WHERE id = ?",
                   (payload.amount, payload.paid_on.isoformat(), payload.account_id, payload.note.strip(), payment_id))
        write_audit_log(db, "update", "payment", payment_id, json.dumps({
            "installment_id": existing["installment_id"],
            "before": {key: existing[key] for key in ("amount", "paid_on", "account_id", "note")},
            "after": {"amount": payload.amount, "paid_on": payload.paid_on.isoformat(), "account_id": payload.account_id, "note": payload.note.strip()}
        }, ensure_ascii=False))
    return {"id": payment_id}


def delete_payment(payment_id: int):
    with connection(write=True) as db:
        existing = db.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
        if not existing:
            raise FinanceError(404, "پرداخت پیدا نشد.")
        write_audit_log(db, "delete", "payment", payment_id, json.dumps({
            "installment_id": existing["installment_id"],
            "before": {key: existing[key] for key in ("amount", "paid_on", "account_id", "note")}
        }, ensure_ascii=False))
        db.execute("DELETE FROM payments WHERE id = ?", (payment_id,))
    return {"id": payment_id}


def delete_commitment(commitment_id: int):
    with connection(write=True) as db:
        commitment = db.execute("SELECT * FROM commitments WHERE id = ?", (commitment_id,)).fetchone()
        if commitment is None:
            raise FinanceError(404, "تعهد پیدا نشد.")
        installments = [dict(row) for row in db.execute("SELECT * FROM installments WHERE commitment_id = ?", (commitment_id,))]
        payments = [dict(row) for row in db.execute("SELECT p.* FROM payments p JOIN installments i ON i.id = p.installment_id WHERE i.commitment_id = ?", (commitment_id,))]
        write_audit_log(db, "delete", "commitment", commitment_id, json.dumps({
            "before": dict(commitment), "installments": installments, "payments": payments
        }, ensure_ascii=False))
        db.execute("DELETE FROM payments WHERE installment_id IN (SELECT id FROM installments WHERE commitment_id = ?)", (commitment_id,))
        db.execute("DELETE FROM installments WHERE commitment_id = ?", (commitment_id,))
        db.execute("DELETE FROM commitments WHERE id = ?", (commitment_id,))
    return {"id": commitment_id, "deleted_installments": len(installments), "deleted_payments": len(payments)}
