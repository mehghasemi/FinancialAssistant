from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from app import database, migrations
from app.services.backups import restore_backup


class RecoveryTests(unittest.TestCase):
    def test_version_four_upgrade_preserves_money_and_backfills_titles(self):
        with database.connection() as db:
            db.execute("INSERT INTO transactions(transaction_type,amount,occurred_on,note) VALUES ('income',1234567,'2026-09-23','قدیمی')")
            for column in ("title", "counterparty", "status"):
                db.execute(f"ALTER TABLE transactions DROP COLUMN {column}")
            db.execute("DROP TABLE asset_values")
            db.execute("DROP TABLE assets")
            db.execute("PRAGMA user_version = 3")
        database.initialize_database()
        database.initialize_database()
        with database.connection() as db:
            row = db.execute("SELECT amount,title,status FROM transactions").fetchone()
            self.assertEqual(tuple(row),(1234567,"قدیمی","paid"))
        self.assertEqual(len(list((self.directory / "backups").glob("*.db"))),1)
        restored = self.directory / "restored.db"
        restore_backup(self.path, restored)
        with closing(sqlite3.connect(restored)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0],4)

    def test_portable_migration_preserves_source_and_existing_destination(self):
        legacy = self.directory / "legacy"
        legacy.mkdir()
        source = legacy / "financial_assistant.db"
        restore_backup(self.path, source)
        source_bytes = source.read_bytes()
        destination_dir = self.directory / "portable" / "data"
        destination = destination_dir / "financial_assistant.db"
        with patch.object(database, "PORTABLE_MODE", True), patch.object(database, "LEGACY_DATA_DIR", legacy), patch.object(database, "DATA_DIR", destination_dir), patch.object(database, "DATABASE_PATH", destination):
            database.initialize_database()
            self.assertTrue(destination.is_file())
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(database.get_setting("backup_directory"), str(destination_dir / "backups"))
            database.set_setting("migration_test", "preserved")
            database.initialize_database()
            self.assertEqual(database.get_setting("migration_test"), "preserved")
            database.set_setting("portable_data_directory", "old-location")
            database.set_setting("backup_directory", "old-location/backups")
            database.initialize_database()
            self.assertEqual(database.get_setting("backup_directory"), str(destination_dir / "backups"))

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.path = self.directory / "test.db"
        for name, value in (("DATA_DIR", self.directory), ("DATABASE_PATH", self.path)):
            mock = patch.object(database, name, value)
            mock.start()
            self.addCleanup(mock.stop)
        database.initialize_database()

    def test_legacy_upgrade_is_idempotent_and_keeps_toman(self):
        with database.connection() as db:
            db.execute("ALTER TABLE commitments DROP COLUMN interval_months")
            db.execute("PRAGMA user_version = 0")
            db.execute("INSERT INTO commitments(id, title, kind, total_amount) VALUES (1, 'legacy', 'loan', 2000)")
            db.execute("INSERT INTO installments(commitment_id, due_date, amount) VALUES (1, '2026-09-23', 1000)")
        database.initialize_database()
        database.initialize_database()
        with database.connection() as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], migrations.SCHEMA_VERSION)
            row = db.execute("SELECT total_amount, interval_months, unique_code FROM commitments").fetchone()
            self.assertEqual(tuple(row), (2000, 1, "001"))
        self.assertEqual(len(list((self.directory / "backups").glob("*.db"))), 1)

    def test_failed_migration_rolls_back_structure_and_version(self):
        def failing(db):
            db.execute("CREATE TABLE must_rollback(id INTEGER)")
            raise RuntimeError("migration failed")
        with database.connection() as db:
            db.execute("PRAGMA user_version = 1")
        with patch.object(migrations, "MIGRATIONS", (lambda db: None, failing)):
            with self.assertRaises(RuntimeError):
                database.initialize_database()
        with database.connection() as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name = 'must_rollback'").fetchone())

    def test_repayment_backfill_uses_loan_without_changing_history(self):
        with database.connection() as db:
            db.execute("PRAGMA user_version = 2")
            db.execute("INSERT INTO commitments(id, title, kind, total_amount) VALUES (1, 'old', 'loan', 5000)")
            db.execute("INSERT INTO installments(id, commitment_id, amount, due_date) VALUES (1, 1, 6000, '2026-09-23')")
            db.execute("INSERT INTO payments(installment_id, amount, paid_on) VALUES (1, 2000, '2026-09-23')")
            db.execute("INSERT INTO commitments(id, title, kind, total_amount, repayment_amount) VALUES (2, 'known', 'loan', 5000, 6500)")
            db.execute("INSERT INTO commitments(id, title, kind) VALUES (3, 'no principal', 'loan')")
            db.execute("INSERT INTO installments(commitment_id, amount, due_date) VALUES (3, 7000, '2026-09-23')")
        database.initialize_database()
        database.initialize_database()
        with database.connection() as db:
            self.assertEqual([r[0] for r in db.execute("SELECT repayment_amount FROM commitments ORDER BY id")], [5000, 6500, 7000])
            self.assertEqual(db.execute("SELECT amount FROM installments WHERE id = 1").fetchone()[0], 6000)
            self.assertEqual(db.execute("SELECT amount FROM payments").fetchone()[0], 2000)

    def test_future_database_is_rejected_without_change(self):
        with database.connection() as db:
            db.execute("PRAGMA user_version = 999")
        before = self.path.read_bytes()
        with self.assertRaises(RuntimeError):
            database.initialize_database()
        self.assertEqual(self.path.read_bytes(), before)

    def test_backup_restores_exact_snapshot_without_overwriting(self):
        with database.connection() as db:
            db.execute("INSERT INTO transactions(transaction_type, amount, occurred_on) VALUES ('income', 1234, '2026-09-23')")
            db.execute("INSERT INTO commitments(id, title, kind) VALUES (1, 'sample', 'loan')")
            db.execute("INSERT INTO installments(id, commitment_id, amount, due_date) VALUES (1, 1, 1000, '2026-09-23')")
            db.execute("INSERT INTO payments(installment_id, amount, paid_on) VALUES (1, 400, '2026-09-23')")
            database.write_audit_log(db, "create", "payment", 1, "installment:1")
            expected = list(db.iterdump())
        first = database.create_database_backup(self.directory / "backups")
        second = database.create_database_backup(self.directory / "backups")
        self.assertNotEqual(first, second)
        with database.connection() as db:
            db.execute("DELETE FROM transactions")
        destination = self.directory / "recovered" / "financial_assistant.db"
        restore_backup(first, destination)
        with closing(sqlite3.connect(destination)) as db:
            self.assertEqual(db.execute("SELECT amount FROM transactions").fetchone()[0], 1234)
            self.assertEqual(list(db.iterdump()), expected)
        with self.assertRaises(FileExistsError):
            restore_backup(first, self.path)
        with database.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 0)

    def test_corrupt_or_unrelated_backup_is_rejected(self):
        source = self.directory / "invalid.db"
        destination = self.directory / "restored.db"
        source.write_bytes(b"not a database")
        with self.assertRaises(sqlite3.DatabaseError):
            restore_backup(source, destination)
        self.assertFalse(destination.exists())
        unrelated = self.directory / "other.db"
        with closing(sqlite3.connect(unrelated)) as db:
            db.execute("CREATE TABLE unrelated(id INTEGER)")
        with self.assertRaises(ValueError):
            restore_backup(unrelated, destination)
        self.assertFalse(destination.exists())
