"""Ordered migrations. Each version and its marker commit in one transaction."""
from __future__ import annotations

import sqlite3
import jdatetime
from datetime import date

SCHEMA_VERSION = 7


def _ensure_column(db: sqlite3.Connection, table: str, definition: str) -> None:
    column_name = definition.split()[0]
    columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
    if column_name not in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def allocate_unique_code(db: sqlite3.Connection) -> str:
    """Return the next sequential 3-digit (or wider, past 999) commitment code."""
    row = db.execute(
        "SELECT MAX(CAST(unique_code AS INTEGER)) AS max_code FROM commitments "
        "WHERE unique_code IS NOT NULL AND unique_code GLOB '[0-9]*'"
    ).fetchone()
    next_number = (row["max_code"] or 0) + 1
    return f"{next_number:03d}"


def _assign_missing_unique_codes(db: sqlite3.Connection) -> None:
    missing_rows = db.execute(
        "SELECT id FROM commitments WHERE unique_code IS NULL ORDER BY id"
    ).fetchall()
    for row in missing_rows:
        db.execute(
            "UPDATE commitments SET unique_code = ? WHERE id = ?",
            (allocate_unique_code(db), row["id"]),
        )


def _apply_rial_to_toman_migration(db: sqlite3.Connection) -> None:
    migration_key = "rial_amounts_to_toman_20260919"
    if db.execute("SELECT 1 FROM data_migrations WHERE migration_key = ?", (migration_key,)).fetchone():
        return
    for table, column in (
        ("transactions", "amount"),
        ("commitments", "total_amount"),
        ("installments", "amount"),
        ("payments", "amount"),
        ("budget_items", "amount"),
    ):
        db.execute(f"UPDATE {table} SET {column} = CAST({column} / 10 AS INTEGER) WHERE {column} IS NOT NULL")
    db.execute("INSERT INTO data_migrations(migration_key) VALUES (?)", (migration_key,))



def _legacy_schema(db):
    _ensure_column(db, "commitments", "repayment_amount INTEGER")
    _ensure_column(db, "commitments", "unique_code TEXT")
    _ensure_column(db, "commitments", "source_key TEXT")
    _ensure_column(db, "installments", "source_key TEXT")
    _ensure_column(db, "payments", "source_key TEXT")
    _ensure_column(db, "transactions", "source_key TEXT")
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_commitments_unique_code "
        "ON commitments(unique_code) WHERE unique_code IS NOT NULL"
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_commitments_source_key "
        "ON commitments(source_key) WHERE source_key IS NOT NULL"
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_installments_source_key "
        "ON installments(source_key) WHERE source_key IS NOT NULL"
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_source_key "
        "ON payments(source_key) WHERE source_key IS NOT NULL"
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_transactions_source_key "
        "ON transactions(source_key) WHERE source_key IS NOT NULL"
    )
    _apply_rial_to_toman_migration(db)
    _assign_missing_unique_codes(db)


def _schedule_interval(db):
    _ensure_column(db, "commitments", "interval_months INTEGER CHECK(interval_months BETWEEN 1 AND 12)")
    for row in db.execute("SELECT id FROM commitments WHERE interval_months IS NULL").fetchall():
        dates = [jdatetime.date.fromgregorian(date=date.fromisoformat(item[0])) for item in db.execute(
            "SELECT due_date FROM installments WHERE commitment_id = ? ORDER BY due_date, id", (row[0],)
        )]
        steps = {(right.year - left.year) * 12 + right.month - left.month for left, right in zip(dates, dates[1:])}
        interval = next(iter(steps)) if len(steps) == 1 else (1 if len(dates) < 2 else None)
        if interval is not None and 1 <= interval <= 12:
            db.execute("UPDATE commitments SET interval_months = ? WHERE id = ?", (interval, row[0]))


def _backfill_repayment(db):
    # Do not rewrite existing repayment terms or any historical installment/payment.
    db.execute("""UPDATE commitments SET repayment_amount = COALESCE(
        total_amount,
        (SELECT NULLIF(SUM(amount), 0) FROM installments WHERE commitment_id = commitments.id)
    ) WHERE repayment_amount IS NULL""")


def _assets_and_transactions(db):
    for definition in ("title TEXT NOT NULL DEFAULT ''", "counterparty TEXT NOT NULL DEFAULT ''", "status TEXT NOT NULL DEFAULT 'paid' CHECK(status IN ('paid','unpaid','cancelled'))"):
        _ensure_column(db, "transactions", definition)
    db.execute("UPDATE transactions SET title = COALESCE(NULLIF(note, ''), 'تراکنش قبلی') WHERE title = ''")
    db.execute("""CREATE TABLE IF NOT EXISTS assets (
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, kind TEXT NOT NULL,
        registered_on TEXT NOT NULL, initial_value INTEGER NOT NULL CHECK(initial_value >= 0),
        current_value INTEGER NOT NULL CHECK(current_value >= 0), note TEXT NOT NULL DEFAULT '')""")
    db.execute("""CREATE TABLE IF NOT EXISTS asset_values (
        id INTEGER PRIMARY KEY AUTOINCREMENT, asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
        changed_at TEXT NOT NULL, old_value INTEGER, new_value INTEGER NOT NULL, note TEXT NOT NULL DEFAULT '')""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_asset_values_asset ON asset_values(asset_id, id)")



def _payment_links_and_budgets(db):
    _ensure_column(db, "transactions", "payment_id INTEGER REFERENCES payments(id) ON DELETE SET NULL")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_transaction_payment ON transactions(payment_id) WHERE payment_id IS NOT NULL")
    db.execute("""CREATE TABLE IF NOT EXISTS monthly_budgets (
        month TEXT NOT NULL, category_id INTEGER NOT NULL REFERENCES categories(id),
        amount INTEGER NOT NULL CHECK(amount >= 0), PRIMARY KEY(month, category_id))""")



def _cash_dates_and_opening(db):
    _ensure_column(db, "transactions", "settled_on TEXT")
    _ensure_column(db, "transactions", "settled_date_assumed INTEGER NOT NULL DEFAULT 1")
    db.execute("UPDATE transactions SET settled_on=occurred_on WHERE status='paid' AND settled_on IS NULL")
    db.execute("""CREATE TABLE IF NOT EXISTS cash_opening (
        id INTEGER PRIMARY KEY CHECK(id=1), amount INTEGER NOT NULL CHECK(amount>=0), as_of_date TEXT NOT NULL)""")


def _bank_accounts(db):
    db.execute("CREATE TABLE IF NOT EXISTS banks (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)")
    for definition in ("bank_id INTEGER REFERENCES banks(id)", "account_number TEXT NOT NULL DEFAULT ''", "opening_amount INTEGER CHECK(opening_amount>=0)", "opening_date TEXT"):
        _ensure_column(db, "accounts", definition)


MIGRATIONS = (_legacy_schema, _schedule_interval, _backfill_repayment, _assets_and_transactions, _payment_links_and_budgets, _cash_dates_and_opening, _bank_accounts)


def run_migrations(db):
    db.execute("SAVEPOINT schema_upgrade")
    try:
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError("Database was created by a newer application version")
        for number, migration in enumerate(MIGRATIONS, start=1):
            if number > version:
                migration(db)
                db.execute(f"PRAGMA user_version = {number}")
        db.execute("RELEASE schema_upgrade")
    except Exception:
        db.execute("ROLLBACK TO schema_upgrade")
        db.execute("RELEASE schema_upgrade")
        raise
