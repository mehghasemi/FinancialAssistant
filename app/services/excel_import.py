from __future__ import annotations

"""Reusable import logic for the 'Sheet4' expense/loan installments sheet.

Used both by the CLI script (scripts/import_sheet4.py) and by the
POST /api/imports/sheet4 endpoint (settings page in the web UI).

Rules (as decided with the user):
- Only a sheet named "Sheet4" is read; every other sheet is ignored.
- All amounts in the sheet are in Rial; every amount is divided by 10 to store in Toman.
- `مبلغ کل` (total_amount) is kept exactly as given (purely informational).
- `repayment_amount` is computed per commitment group as the sum of that group's
  installment amounts (after the /10 conversion), so the app's own validation
  (sum of installments must equal repayment_amount) holds true by construction.
- Payments are created for rows marked 'پرداخت شده' / 'تسویه شده', with
  account_id = NULL and paid_on = due_date (the sheet has no separate payment date).
- Re-running the import is idempotent: rows already imported (matched by
  source_key) are skipped via INSERT OR IGNORE.
"""

import json
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from io import BytesIO

from openpyxl import load_workbook

from .. import database
from ..calendar import parse_jalali_date
from ..database import allocate_unique_code

PAID_STATUSES = {"پرداخت شده", "تسویه شده"}
REQUIRED_COLUMNS = ("عنوان", "مبلغ کل", "تاریخ سررسید", "وضعیت", "مبلغ")


class ExcelImportError(ValueError):
    """Raised when the workbook doesn't have the expected sheet/columns."""


def _cell_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _amount_value(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        if not cleaned:
            return None
        value = cleaned
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount != amount.to_integral_value():
            return None
        if amount <= 0 or amount > 9223372036854775807 or amount % 10:
            return None
        return int(amount)
    except (InvalidOperation, TypeError, ValueError):
        return None


def import_sheet4(file_bytes: bytes) -> dict:
    try:
        workbook = load_workbook(BytesIO(file_bytes), data_only=False)
    except Exception as error:  # noqa: BLE001 - surfaced as a clean 422 message
        raise ExcelImportError("فایل ارسالی یک اکسل معتبر نیست.") from error

    try:
        groups = _validate_sheet4(workbook)
    finally:
        workbook.close()
    return _save_groups(groups)


def _validation_error(errors: list[str]) -> ExcelImportError:
    shown = errors[:50]
    message = f"ورود انجام نشد؛ هیچ اطلاعاتی ثبت نشد. {len(errors)} مورد نیاز به اصلاح دارد:\n"
    message += "\n".join(shown)
    if len(errors) > len(shown):
        message += f"\nو {len(errors) - len(shown)} مورد دیگر؛ ابتدا موارد بالا را اصلاح و دوباره تلاش کنید."
    return ExcelImportError(message)


def _validate_sheet4(workbook):
    """Validate every populated row before any database write."""
    if "Sheet4" not in workbook.sheetnames:
        raise ExcelImportError("شیت «Sheet4» در فایل پیدا نشد.")
    sheet = workbook["Sheet4"]

    header_row = 1
    headers = {_cell_text(cell.value): cell.column for cell in sheet[header_row]}
    counts = Counter(_cell_text(cell.value) for cell in sheet[header_row])
    duplicates = [name for name in (*REQUIRED_COLUMNS, "نوع", "تاریخ سرسید") if counts[name] > 1]
    if duplicates or ("تاریخ سررسید" in headers and "تاریخ سرسید" in headers):
        raise _validation_error(["ردیف ۱: سرتیتر تکراری یا دو ستون سررسید وجود دارد؛ از هر سرتیتر فقط یک ستون نگه دارید."])
    col_kind = headers.get("نوع")
    col_title = headers.get("عنوان")
    col_total = headers.get("مبلغ کل")
    col_due = headers.get("تاریخ سررسید") or headers.get("تاریخ سرسید")
    col_status = headers.get("وضعیت")
    col_amount = headers.get("مبلغ")

    missing = [
        name for name, column in {
            "عنوان": col_title, "مبلغ کل": col_total, "تاریخ سررسید": col_due,
            "وضعیت": col_status, "مبلغ": col_amount,
        }.items() if not column
    ]
    if missing:
        raise _validation_error([f"ردیف ۱: ستون‌های لازم در Sheet4 پیدا نشد: {'، '.join(missing)}"])

    groups: dict[tuple[str, str, int], list[tuple[int, str, int, str]]] = defaultdict(list)
    errors: list[str] = []
    seen_rows = {}

    for row_number in range(header_row + 1, sheet.max_row + 1):
        if all(cell.value is None or _cell_text(cell.value) == "" for cell in sheet[row_number]):
            continue
        row_errors = []
        kind = _cell_text(sheet.cell(row_number, col_kind).value) if col_kind else ""
        title = _cell_text(sheet.cell(row_number, col_title).value)
        total_raw = _amount_value(sheet.cell(row_number, col_total).value)
        due_raw = sheet.cell(row_number, col_due).value
        status = _cell_text(sheet.cell(row_number, col_status).value)
        amount_raw = _amount_value(sheet.cell(row_number, col_amount).value)

        if not title:
            row_errors.append("عنوان خالی است")
        for label, value in (("مبلغ کل", total_raw), ("مبلغ", amount_raw)):
            if value is None:
                row_errors.append(f"«{label}» باید عدد صحیح مثبت به ریال، مضرب ۱۰ و حداکثر ۹۲۲۳۳۷۲۰۳۶۸۵۴۷۷۵۸۰۷ باشد؛ فرمول قابل قبول نیست")
        if status not in PAID_STATUSES | {"پرداخت نشده"}:
            row_errors.append("وضعیت باید «پرداخت شده»، «تسویه شده» یا «پرداخت نشده» باشد")
        relevant_columns = [col_title, col_kind, col_total, col_due, col_status, col_amount]
        if any(sheet.cell(row_number, column).data_type == 'f' for column in relevant_columns if column):
            row_errors.append("سلول فرمولی وجود دارد؛ نتیجه را به صورت مقدار ثابت جای‌گذاری کنید")
        try:
            due_date = parse_jalali_date(due_raw)
        except (ValueError, TypeError, AttributeError, OverflowError):
            row_errors.append("تاریخ سررسید معتبر نیست؛ تاریخ شمسی مانند 1405/07/01 وارد کنید")
        if row_errors:
            errors.append(f"ردیف {row_number}: " + "؛ ".join(row_errors))
            continue

        total = total_raw // 10
        amount = amount_raw // 10
        key = (kind or "سایر", title, total)
        row_key = (*key, due_date.isoformat(), amount)
        if row_key in seen_rows:
            errors.append(f"ردیف {row_number}: قسط تکراری با ردیف {seen_rows[row_key]}؛ برای تعهد مستقل عنوان متفاوت وارد کنید.")
        else:
            seen_rows[row_key] = row_number
        groups[key].append((row_number, due_date.isoformat(), amount, status))

    for rows in groups.values():
        if sum(row[2] for row in rows) > 9223372036854775807:
            errors.append(f"ردیف {rows[0][0]}: جمع مبالغ اقساط این تعهد بیش از حد مجاز است.")
    if errors:
        raise _validation_error(errors)

    if not groups:
        raise _validation_error(["شیت Sheet4 خالی است؛ اطلاعات را از ردیف دوم وارد کنید."])
    return groups


def _save_groups(groups) -> dict:
    commitment_count = installment_count = payment_count = 0
    database.initialize_database()
    with database.connection(write=True) as db:
        _validate_existing_rows(db, groups)
        for group_index, ((kind, title, total), rows) in enumerate(sorted(groups.items()), start=1):
            repayment_amount = sum(row[2] for row in rows)
            commitment_key = f"commitment:Sheet4:{group_index:03d}:{title}:{total}"
            existing = db.execute(
                "SELECT id FROM commitments WHERE source_key = ?", (commitment_key,)
            ).fetchone()
            if existing is None:
                db.execute(
                    """INSERT INTO commitments(title, kind, total_amount, repayment_amount, unique_code, source_key)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (title, kind or "سایر", total, repayment_amount, allocate_unique_code(db), commitment_key),
                )
            commitment_id = db.execute(
                "SELECT id FROM commitments WHERE source_key = ?", (commitment_key,)
            ).fetchone()["id"]
            commitment_count += 1

            for row_number, due_iso, amount, status in rows:
                installment_key = f"installment:Sheet4:{row_number}"
                db.execute(
                    """INSERT OR IGNORE INTO installments(commitment_id, due_date, amount, note, source_key)
                       VALUES (?, ?, ?, ?, ?)""",
                    (commitment_id, due_iso, amount, "", installment_key),
                )
                installment_row = db.execute(
                    "SELECT id FROM installments WHERE source_key = ?", (installment_key,)
                ).fetchone()
                if not installment_row:
                    continue
                installment_count += 1

                if status in PAID_STATUSES:
                    payment_key = f"payment:Sheet4:{row_number}"
                    db.execute(
                        """INSERT OR IGNORE INTO payments(installment_id, amount, paid_on, account_id, note, source_key, paid_date_assumed)
                           VALUES (?, ?, ?, NULL, ?, ?, 1)""",
                        (
                            installment_row["id"], amount, due_iso,
                            "تاریخ پرداخت در فایل موجود نبود، سررسید به‌عنوان تاریخ پرداخت ثبت شد.",
                            payment_key,
                        ),
                    )
                    payment_count += 1
            if existing is None:
                database.write_audit_log(db, "import", "commitment", commitment_id, json.dumps({
                    "after": {"title": title, "kind": kind, "total_amount": total,
                              "repayment_amount": repayment_amount, "installments": rows},
                    "source": "Sheet4"
                }, ensure_ascii=False))

    return {
        "groups": len(groups),
        "commitments": commitment_count,
        "installments": installment_count,
        "payments": payment_count,
        "skipped_rows": [],
    }


def _validate_existing_rows(db, groups):
    """Reject source-key collisions rather than silently skipping changed data."""
    errors = []
    for group_index, ((kind, title, total), rows) in enumerate(sorted(groups.items()), start=1):
        expected_key = f"commitment:Sheet4:{group_index:03d}:{title}:{total}"
        existing_group = db.execute(
            "SELECT kind, title, total_amount, repayment_amount FROM commitments WHERE source_key = ?",
            (expected_key,),
        ).fetchone()
        if existing_group and tuple(existing_group) != (kind, title, total, sum(row[2] for row in rows)):
            errors.append(f"ردیف {rows[0][0]}: تعهد قبلاً وارد شده ولی مشخصات یا مجموع اقساط تغییر کرده است؛ از ویرایش داخل برنامه استفاده کنید.")
        for row_number, due_iso, amount, status in rows:
            existing = db.execute(
                """SELECT i.due_date, i.amount, c.source_key,
                          (SELECT COUNT(*) FROM payments p WHERE p.installment_id = i.id) AS payment_count,
                          (SELECT COALESCE(SUM(p.amount), 0) FROM payments p WHERE p.installment_id = i.id) AS paid
                   FROM installments i JOIN commitments c ON c.id = i.commitment_id
                   WHERE i.source_key = ?""", (f"installment:Sheet4:{row_number}",),
            ).fetchone()
            if existing and (existing['due_date'] != due_iso or existing['amount'] != amount
                             or existing['source_key'] != expected_key
                             or existing['paid'] != (amount if status in PAID_STATUSES else 0)
                             or existing['payment_count'] != (1 if status in PAID_STATUSES else 0)):
                errors.append(f"ردیف {row_number}: با اطلاعات قبلاً واردشده تداخل دارد؛ فایل تغییرکرده را مجدد وارد نکنید و از ویرایش داخل برنامه استفاده کنید.")
    if errors:
        raise _validation_error(errors)
