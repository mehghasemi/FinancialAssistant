"""Validate and recover snapshots to a new database, never overwrite live data."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3

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
