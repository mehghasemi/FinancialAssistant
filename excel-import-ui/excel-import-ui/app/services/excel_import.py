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

from collections import defaultdict
from io import BytesIO

from openpyxl import load_workbook

from .. import database
from ..calendar import parse_jalali_date

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
        return int(float(value))
    except (TypeError, ValueError):
        return None


def import_sheet4(file_bytes: bytes) -> dict:
    try:
        workbook = load_workbook(BytesIO(file_bytes), data_only=True)
    except Exception as error:  # noqa: BLE001 - surfaced as a clean 422 message
        raise ExcelImportError("فایل ارسالی یک اکسل معتبر نیست.") from error

    if "Sheet4" not in workbook.sheetnames:
        raise ExcelImportError("شیت «Sheet4» در فایل پیدا نشد.")
    sheet = workbook["Sheet4"]

    header_row = 1
    headers = {_cell_text(cell.value): cell.column for cell in sheet[header_row]}
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
        raise ExcelImportError(f"ستون‌های لازم در Sheet4 پیدا نشد: {'، '.join(missing)}")

    groups: dict[tuple[str, str, int], list[tuple[int, str, int, str]]] = defaultdict(list)
    skipped_rows: list[int] = []

    for row_number in range(header_row + 1, sheet.max_row + 1):
        kind = _cell_text(sheet.cell(row_number, col_kind).value) if col_kind else ""
        title = _cell_text(sheet.cell(row_number, col_title).value)
        total_raw = _amount_value(sheet.cell(row_number, col_total).value)
        due_raw = sheet.cell(row_number, col_due).value
        status = _cell_text(sheet.cell(row_number, col_status).value)
        amount_raw = _amount_value(sheet.cell(row_number, col_amount).value)

        if not title or total_raw is None or amount_raw is None or amount_raw <= 0:
            if title or total_raw or amount_raw:
                skipped_rows.append(row_number)
            continue
        try:
            due_date = parse_jalali_date(due_raw)
        except (ValueError, TypeError):
            skipped_rows.append(row_number)
            continue

        total = total_raw // 10
        amount = amount_raw // 10
        groups[(kind, title, total)].append((row_number, due_date.isoformat(), amount, status))

    if not groups:
        raise ExcelImportError("هیچ ردیف معتبری در Sheet4 پیدا نشد.")

    commitment_count = installment_count = payment_count = 0
    database.initialize_database()
    with database.connection() as db:
        for group_index, ((kind, title, total), rows) in enumerate(sorted(groups.items()), start=1):
            repayment_amount = sum(row[2] for row in rows)
            commitment_key = f"commitment:Sheet4:{group_index:03d}:{title}:{total}"
            db.execute(
                """INSERT OR IGNORE INTO commitments(title, kind, total_amount, repayment_amount, source_key)
                   VALUES (?, ?, ?, ?, ?)""",
                (title, kind or "سایر", total, repayment_amount, commitment_key),
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
                    (commitment_id, due_iso, amount, f"واردشده از Sheet4 اکسل (کد گروه: {group_index:03d})", installment_key),
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
                        """INSERT OR IGNORE INTO payments(installment_id, amount, paid_on, account_id, note, source_key)
                           VALUES (?, ?, ?, NULL, ?, ?)""",
                        (
                            installment_row["id"], amount, due_iso,
                            "واردشده از اکسل؛ تاریخ پرداخت در فایل موجود نبود، سررسید به‌عنوان تاریخ پرداخت ثبت شد.",
                            payment_key,
                        ),
                    )
                    payment_count += 1

    return {
        "groups": len(groups),
        "commitments": commitment_count,
        "installments": installment_count,
        "payments": payment_count,
        "skipped_rows": skipped_rows,
    }
