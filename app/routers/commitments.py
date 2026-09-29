from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, HTTPException

from ..calendar import format_jalali_date, format_jalali_datetime
from ..database import connection
from ..services import finance
from ..schemas import (
    CommitmentGroupUpdate, CommitmentInput, CommitmentUpdate,
    InstallmentUpdate, PaymentInput, PaymentUpdate,
)
from ..utils import (
    installment_rows, month_bounds_or_error,
    normalize_text, serialize,
)

router = APIRouter(prefix="/api", tags=["commitments"])


@router.post("/commitments", status_code=201)
def create_commitment(payload: CommitmentInput):
    return finance.create_commitment(payload)


@router.post("/commitments/preview")
def preview_commitment(payload: CommitmentInput):
    return finance.preview_commitment(payload)


@router.get("/commitments")
def commitment_list():
    with connection() as db:
        return [
            serialize(row)
            for row in db.execute(
                """SELECT c.id, c.unique_code, c.title, c.kind, c.total_amount, c.repayment_amount, c.interval_months, COUNT(i.id) AS installment_count,
                          COALESCE(SUM(i.amount), 0) AS planned_amount,
                          COALESCE(SUM(p.payment_amount), 0) AS paid_amount,
                          MIN(CASE WHEN i.amount > COALESCE(p.payment_amount, 0) THEN i.due_date END) AS next_unpaid_due_date,
                          MIN(i.due_date) AS first_due_date,
                          MAX(i.due_date) AS last_due_date,
                          (SELECT amount FROM installments WHERE commitment_id = c.id ORDER BY due_date, id LIMIT 1) AS installment_amount,
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
    return finance.update_commitment(commitment_id, payload)


@router.patch("/commitments/{commitment_id}/group")
def update_commitment_group(commitment_id: int, payload: CommitmentGroupUpdate):
    return finance.update_commitment_group(commitment_id, payload)


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
    return finance.update_installment(installment_id, payload)


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
    return finance.create_payment(payload)


@router.patch("/payments/{payment_id}")
def update_payment(payment_id: int, payload: PaymentUpdate):
    return finance.update_payment(payment_id, payload)


@router.delete("/payments/{payment_id}")
def delete_payment(payment_id: int):
    return finance.delete_payment(payment_id)
