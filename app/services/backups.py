"""Validate and recover snapshots to a new database, never overwrite live data."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import json

from ..migrations import SCHEMA_VERSION


REQUIRED_COLUMNS = {
    "accounts": {"id", "name"},
    "categories": {"id", "name", "transaction_type"},
    "transactions": {"id", "amount", "occurred_on", "transaction_type"},
    "commitments": {"id", "title", "kind", "total_amount"},
    "installments": {"id", "commitment_id", "amount", "due_date"},
    "payments": {"id", "installment_id", "amount", "paid_on"},
    "data_migrations": {"migration_key"},
}


def validate_backup(db: sqlite3.Connection) -> None:
    if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise ValueError("Backup integrity check failed")
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise ValueError("Backup requires a newer application version")
    for table, required in REQUIRED_COLUMNS.items():
        columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        if not required.issubset(columns):
            raise ValueError(f"Not a supported FinancialAssistant backup: {table}")
    if version >= 2:
        columns = {row[1] for row in db.execute("PRAGMA table_info(commitments)")}
        if not {"interval_months", "repayment_amount", "unique_code", "source_key"}.issubset(columns):
            raise ValueError("Backup schema does not match its version")
    if version >= 4:
        for table, required in {"assets": {"id", "title", "kind", "registered_on", "initial_value", "current_value", "note"}, "asset_values": {"id", "asset_id", "changed_at", "old_value", "new_value", "note"}, "transactions": {"title", "counterparty", "status"}}.items():
            columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
            if not required.issubset(columns):
                raise ValueError("Backup schema does not match its version")
    if version >= 5:
        for table, required in {"transactions":{"payment_id"}, "monthly_budgets":{"month","category_id","amount"}}.items():
            if not required.issubset({row[1] for row in db.execute(f"PRAGMA table_info({table})")}):
                raise ValueError("Backup schema does not match its version")
    if version >= 6:
        for table, required in {"transactions":{"settled_on","settled_date_assumed"}, "cash_opening":{"id","amount","as_of_date"}}.items():
            if not required.issubset({row[1] for row in db.execute(f"PRAGMA table_info({table})")}):
                raise ValueError("Backup schema does not match its version")
    if version >= 7:
        for table, required in {"banks":{"id","name"}, "accounts":{"bank_id","account_number","opening_amount","opening_date"}}.items():
            if not required.issubset({row[1] for row in db.execute(f"PRAGMA table_info({table})")}):
                raise ValueError("Backup schema does not match its version")
    if db.execute("PRAGMA foreign_key_check").fetchone():
        raise ValueError("Backup contains broken references")


def restore_backup(source: Path, destination: Path) -> Path:
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if source == destination or destination.exists():
        raise FileExistsError("Restore destination must be a new file")
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as snapshot:
        snapshot.execute("BEGIN")
        validate_backup(snapshot)
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents accidentally replacing a file created concurrently.
        with destination.open("xb"):
            pass
        try:
            with closing(sqlite3.connect(destination)) as restored:
                snapshot.backup(restored)
                validate_backup(restored)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
    return destination


def restore_uploaded_backup(content: bytes) -> Path:
    """Prepare fully, then replace SQLite contents atomically under the app lock."""
    from .. import database
    if not content.startswith(b"SQLite format 3\x00"):
        raise ValueError("فایل انتخاب‌شده دیتابیس SQLite نیست.")
    with tempfile.TemporaryDirectory(prefix="restore-", dir=database.DATA_DIR) as directory:
        uploaded, staged = Path(directory) / "upload.db", Path(directory) / "staged.db"
        uploaded.write_bytes(content)
        with closing(sqlite3.connect(uploaded)) as source:
            source.execute("PRAGMA trusted_schema=OFF")
            if source.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view')").fetchone():
                raise ValueError("ساختار فایل پشتیبان پشتیبانی نمی‌شود.")
        restore_backup(uploaded, staged)
        database.initialize_database(target_path=staged)
        with database.DATABASE_LOCK:
            # Paths belong to this machine, not the computer which made the backup.
            with database.connection() as current:
                local_settings = current.execute("SELECT setting_key,setting_value FROM app_settings WHERE setting_key IN ('backup_directory','backup_enabled','portable_data_directory')").fetchall()
            before_path = database.create_database_backup(database.DATA_DIR / "backups")
            with closing(sqlite3.connect(staged)) as source:
                for key, value in local_settings:
                    source.execute("INSERT INTO app_settings(setting_key,setting_value) VALUES (?,?) ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value", (key, value))
                database.write_audit_log(source, "restore", "system", 0, json.dumps({"backup_path": str(before_path)}, ensure_ascii=False))
                source.commit()
                validate_backup(source)
                # sqlite backup commits the replacement as one destination transaction.
                # No file rename, and no stale WAL/SHM sidecars.
                with closing(sqlite3.connect(database.DATABASE_PATH)) as destination:
                    source.backup(destination)
        return before_path
