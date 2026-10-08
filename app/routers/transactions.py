from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from ..calendar import format_jalali_date
from ..database import connection, write_audit_log
from ..schemas import TransactionInput
from ..utils import month_bounds_or_error, serialize

router = APIRouter(prefix="/api", tags=["transactions"])


@router.get("/accounts")
def accounts():
    with connection() as db:
        return [serialize(row) for row in db.execute("SELECT id, name, kind FROM accounts ORDER BY id").fetchall()]


@router.get("/categories")
def categories(transaction_type: Literal["income", "expense"] | None = None):
    sql = "SELECT id, name, transaction_type FROM categories"
    params: tuple = ()
    if transaction_type:
        sql += " WHERE transaction_type = ?"
        params = (transaction_type,)
    sql += " ORDER BY transaction_type, name"
    with connection() as db:
        return [serialize(row) for row in db.execute(sql, params).fetchall()]


def validate_references(db, payload):
    if payload.category_id:
        category = db.execute("SELECT transaction_type FROM categories WHERE id = ?", (payload.category_id,)).fetchone()
        if not category:
            raise HTTPException(404, "دسته‌بندی پیدا نشد.")
        if category["transaction_type"] != payload.transaction_type:
            raise HTTPException(422, "نوع دسته‌بندی با نوع تراکنش هم‌خوان نیست.")
    if payload.account_id and not db.execute("SELECT 1 FROM accounts WHERE id = ?", (payload.account_id,)).fetchone():
        raise HTTPException(404, "حساب پیدا نشد.")



def validate_payment_and_duplicates(db, payload, identifier=0):
    if payload.payment_id:
        payment = db.execute("SELECT * FROM payments WHERE id=?", (payload.payment_id,)).fetchone()
        if not payment:
            raise HTTPException(404, "پرداخت قسط پیدا نشد.")
        if (payload.transaction_type != "expense" or payload.status != "paid" or
                (payload.amount, (payload.settled_on or payload.occurred_on).isoformat(), payload.account_id) !=
                (payment["amount"], payment["paid_on"], payment["account_id"])):
            raise HTTPException(422, "برای اتصال، نوع هزینه و وضعیت انجام‌شده و مبلغ، تاریخ و حساب یکسان با پرداخت قسط لازم است.")
        if db.execute("SELECT 1 FROM transactions WHERE payment_id=? AND id!=?", (payload.payment_id, identifier)).fetchone():
            raise HTTPException(409, "این پرداخت قبلاً به یک هزینه متصل شده است.")
    if payload.confirm_duplicate or payload.status == "cancelled":
        return
    duplicates = db.execute("""SELECT id,title FROM transactions WHERE id!=? AND transaction_type=?
        AND amount=? AND occurred_on=? AND account_id IS ? AND status!='cancelled'""",
        (identifier, payload.transaction_type, payload.amount, payload.occurred_on.isoformat(), payload.account_id)).fetchall()
    if duplicates:
        raise HTTPException(409, {"code":"possible_duplicate", "message":"تراکنش با مبلغ، تاریخ، نوع و حساب مشابه وجود دارد. آیا این یک تراکنش مستقل است؟",
                                  "candidates":[dict(row) for row in duplicates]})


@router.get("/payment-links")
def payment_links():
    with connection() as db:
        items = [dict(row) for row in db.execute("""SELECT p.id,p.amount,p.paid_on,p.account_id,i.due_date,
            i.commitment_id,c.title,t.id AS transaction_id FROM payments p
            JOIN installments i ON i.id=p.installment_id JOIN commitments c ON c.id=i.commitment_id
            LEFT JOIN transactions t ON t.payment_id=p.id ORDER BY p.paid_on DESC,p.id DESC""")]
    for item in items:
        item["paid_on"] = format_jalali_date(item["paid_on"])
        item["due_date"] = format_jalali_date(item["due_date"])
    return items


def transaction_values(payload):
    return (payload.transaction_type, payload.amount, payload.occurred_on.isoformat(), payload.category_id,
            payload.account_id, payload.note.strip(), payload.title.strip() or payload.note.strip() or "تراکنش", payload.counterparty.strip(), payload.status, payload.payment_id,
            (payload.settled_on or payload.occurred_on).isoformat() if payload.status == "paid" else None,
            int(payload.settled_on is None))


@router.get("/transaction-duplicates")
def transaction_duplicates():
    with connection() as db:
        items = [dict(row) for row in db.execute("""SELECT id,title,transaction_type,amount,occurred_on,account_id FROM (
            SELECT *,COUNT(*) OVER(PARTITION BY transaction_type,amount,occurred_on,account_id) AS similar
            FROM transactions WHERE status!='cancelled'
        ) WHERE similar>1 ORDER BY occurred_on DESC,amount,account_id,id""")]
    for item in items:
        item["occurred_on"] = format_jalali_date(item["occurred_on"])
    return items


@router.post("/transactions", status_code=201)
def create_transaction(payload: TransactionInput):
    with connection(write=True) as db:
        validate_references(db, payload)
        validate_payment_and_duplicates(db, payload)
        cursor = db.execute("""INSERT INTO transactions(transaction_type, amount, occurred_on, category_id, account_id, note, title, counterparty, status, payment_id, settled_on, settled_date_assumed)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", transaction_values(payload))
        write_audit_log(db, "create", "transaction", cursor.lastrowid, json.dumps({"after": payload.model_dump(mode="json")}, ensure_ascii=False))
        return {"id": cursor.lastrowid}


@router.patch("/transactions/{identifier}")
def update_transaction(identifier: int, payload: TransactionInput):
    with connection(write=True) as db:
        before = db.execute("SELECT * FROM transactions WHERE id = ?", (identifier,)).fetchone()
        if not before:
            raise HTTPException(404, "تراکنش پیدا نشد.")
        validate_references(db, payload)
        validate_payment_and_duplicates(db, payload, identifier)
        db.execute("""UPDATE transactions SET transaction_type=?, amount=?, occurred_on=?, category_id=?, account_id=?, note=?, title=?, counterparty=?, status=?, payment_id=?, settled_on=?, settled_date_assumed=? WHERE id=?""", (*transaction_values(payload), identifier))
        write_audit_log(db, "update", "transaction", identifier, json.dumps({"before": dict(before), "after": payload.model_dump(mode="json")}, ensure_ascii=False))
    return {"id": identifier}


@router.delete("/transactions/{identifier}")
def delete_transaction(identifier: int, confirm: bool = False):
    if not confirm:
        raise HTTPException(422, "حذف تراکنش نیاز به تأیید دارد.")
    with connection(write=True) as db:
        before = db.execute("SELECT * FROM transactions WHERE id=?", (identifier,)).fetchone()
        if not before:
            raise HTTPException(404, "تراکنش پیدا نشد.")
        write_audit_log(db, "delete", "transaction", identifier, json.dumps({"before": dict(before)}, ensure_ascii=False))
        db.execute("DELETE FROM transactions WHERE id=?", (identifier,))
    return {"status": "deleted"}


@router.get("/transactions")
def transactions(month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$")):
    params: list[str] = []
    where = ""
    if month:
        start, end = month_bounds_or_error(month)
        where = "WHERE t.occurred_on >= ? AND t.occurred_on < ?"
        params.extend((start, end))
    query = f"""
        SELECT t.*,
               c.name AS category_name, a.name AS account_name
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        LEFT JOIN accounts a ON a.id = t.account_id
        {where}
        ORDER BY t.occurred_on DESC, t.id DESC
    """
    with connection() as db:
        result = [serialize(row) for row in db.execute(query, params).fetchall()]
    for item in result:
        item["title"] = item["title"] or item["note"] or "تراکنش"
        item["occurred_on"] = format_jalali_date(item["occurred_on"])
        item["settled_on"] = format_jalali_date(item["settled_on"]) if item["settled_on"] else None
    return result
