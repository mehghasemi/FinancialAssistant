"""User-managed reference data and account opening balances."""
import json
import sqlite3
from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator

from ..calendar import parse_jalali_date, format_jalali_date
from ..database import connection, write_audit_log

router = APIRouter(prefix="/api/base-data", tags=["base-data"])
Resource = Literal["banks", "accounts", "categories"]


class ReferenceInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["bank", "cash"] = "bank"
    bank_id: int | None = Field(default=None, gt=0)
    account_number: str = Field(default="", max_length=40)
    opening_amount: int | None = Field(default=None, ge=0, le=9007199254740991)
    opening_date: date | None = None
    transaction_type: Literal["income", "expense"] = "expense"

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Name is required")
        return value

    @field_validator("opening_date", mode="before")
    @classmethod
    def parse_date(cls, value):
        return parse_jalali_date(value) if value else None

    @model_validator(mode="after")
    def opening_pair(self):
        if (self.opening_amount is None) != (self.opening_date is None):
            raise ValueError("Opening amount and date are required together")
        if self.opening_date and self.opening_date > date.today():
            raise ValueError("Opening date cannot be in the future")
        return self


@router.get("")
def reference_data():
    from ..services.cashflow import cash_overview
    import jdatetime
    today = date.today()
    month = jdatetime.date.fromgregorian(date=today).strftime("%Y-%m")
    cash = cash_overview(month, today)
    with connection() as db:
        result = {table: [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY id")]
                  for table in ("banks", "accounts", "categories")}
    for account in result["accounts"]:
        account["balance"] = cash["account_balances"].get(account["id"])
        if account["opening_date"]:
            account["opening_date"] = format_jalali_date(account["opening_date"])
    result["unassigned_count"] = cash["unassigned_count"]
    return result


def save_reference(resource, payload, identifier=None):
    fields = {"banks": ("name",), "categories": ("name", "transaction_type"),
              "accounts": ("name", "kind", "bank_id", "account_number", "opening_amount", "opening_date")}[resource]
    values = payload.model_dump(mode="json", include=set(fields))
    if resource == "accounts" and payload.kind == "cash":
        values["bank_id"] = None
    try:
        with connection(write=True) as db:
            before = db.execute(f"SELECT * FROM {resource} WHERE id=?", (identifier,)).fetchone() if identifier else None
            if identifier and not before:
                raise HTTPException(404, "رکورد پیدا نشد.")
            if resource == "accounts":
                if values["bank_id"] and not db.execute("SELECT 1 FROM banks WHERE id=?", (values["bank_id"],)).fetchone():
                    raise HTTPException(422, "بانک معتبر انتخاب کنید.")
                if payload.opening_date and db.execute("SELECT 1 FROM accounts WHERE id!=? AND opening_date IS NOT NULL AND opening_date!=?", (identifier or 0, values["opening_date"])).fetchone():
                    raise HTTPException(422, "تاریخ مبنای موجودی همهٔ حساب‌ها باید یکسان باشد.")
            if resource == "categories" and before and before["transaction_type"] != payload.transaction_type:
                if db.execute("SELECT 1 FROM transactions WHERE category_id=? UNION ALL SELECT 1 FROM monthly_budgets WHERE category_id=?", (identifier, identifier)).fetchone():
                    raise HTTPException(409, "نوع دسته‌بندی استفاده‌شده قابل تغییر نیست.")
            if identifier:
                db.execute(f"UPDATE {resource} SET " + ",".join(f"{key}=?" for key in values) + " WHERE id=?", (*values.values(), identifier))
            else:
                identifier = db.execute(f"INSERT INTO {resource} ({','.join(values)}) VALUES ({','.join('?' for _ in values)})", tuple(values.values())).lastrowid
            write_audit_log(db, "update" if before else "create", resource, identifier,
                            json.dumps({"before": dict(before) if before else None, "after": values}, ensure_ascii=False))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "نام تکراری است یا اطلاعات به رکورد دیگری وابسته است.")
    return {"id": identifier}


@router.post("/{resource}", status_code=201)
def create_reference(resource: Resource, payload: ReferenceInput):
    return save_reference(resource, payload)


@router.put("/{resource}/{identifier}")
def update_reference(resource: Resource, identifier: int, payload: ReferenceInput):
    return save_reference(resource, payload, identifier)


@router.delete("/{resource}/{identifier}")
def delete_reference(resource: Resource, identifier: int, confirm: bool = Query(False)):
    if not confirm:
        raise HTTPException(422, "تأیید حذف لازم است.")
    try:
        with connection(write=True) as db:
            row = db.execute(f"SELECT * FROM {resource} WHERE id=?", (identifier,)).fetchone()
            if not row:
                raise HTTPException(404, "رکورد پیدا نشد.")
            db.execute(f"DELETE FROM {resource} WHERE id=?", (identifier,))
            write_audit_log(db, "delete", resource, identifier, json.dumps({"before": dict(row)}, ensure_ascii=False))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "این مورد استفاده شده است و قابل حذف نیست.")
    return {"status": "deleted"}
