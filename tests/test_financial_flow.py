import tempfile
import unittest
from datetime import date
from pathlib import Path

import app.database as database
from app.routers import commitments
from app import schemas
from app.calendar import parse_jalali_date


class FinancialFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_data_dir, self.old_database_path = database.DATA_DIR, database.DATABASE_PATH
        database.DATA_DIR = Path(self.temp_dir.name)
        database.DATABASE_PATH = Path(self.temp_dir.name) / "financial-assistant-test.db"
        database.initialize_database()

    def tearDown(self):
        database.DATA_DIR, database.DATABASE_PATH = self.old_data_dir, self.old_database_path
        self.temp_dir.cleanup()

    def test_commitment_updates_all_installments_and_payment_correction_is_audited(self):
        created = commitments.create_commitment(schemas.CommitmentInput(
            title="وام قدیم", kind="وام", total_amount=2000,
            installment_amount=1000, first_due_date=date(2026, 10, 1), installment_count=2,
        ))
        rows = commitments.installments(commitment_id=created["id"])
        commitments.update_commitment(created["id"], schemas.CommitmentUpdate(
            title="وام جدید", kind="بدهی", total_amount=2000,
        ))
        self.assertEqual(len(commitments.commitment_list()), 1)
        self.assertEqual({(row["title"], row["kind"]) for row in commitments.installments(commitment_id=created["id"])}, {("وام جدید", "بدهی")})
        payment = commitments.create_payment(schemas.PaymentInput(
            installment_id=rows[0]["id"], amount=1000, paid_on=date(2026, 10, 2),
        ))
        self.assertEqual(commitments.installments(commitment_id=created["id"])[0]["status"], "paid")
        commitments.update_payment(payment["id"], schemas.PaymentUpdate(amount=400, paid_on=date(2026, 10, 3)))
        self.assertEqual(commitments.installments(commitment_id=created["id"])[0]["status"], "partial")
        commitments.delete_payment(payment["id"])
        self.assertEqual(commitments.installments(commitment_id=created["id"])[0]["paid_amount"], 0)
        details = commitments.installment_details(rows[0]["id"])
        self.assertEqual(details["payments"], [])
        self.assertTrue(any(log["resource_type"] == "payment" and log["action"] == "delete" for log in details["history"]))
        self.assertTrue(any(log["resource_type"] == "commitment" and log["action"] == "update" for log in details["history"]))

    def test_commitment_list_has_one_row_and_next_unpaid_due_date(self):
        created = commitments.create_commitment(schemas.CommitmentInput(
            title="وام آزمایشی", kind="وام", total_amount=3000,
            installment_amount=1000, first_due_date=date(2026, 10, 1), installment_count=3,
        ))
        rows = commitments.installments(commitment_id=created["id"])
        self.assertEqual(len(commitments.commitment_list()), 1)
        self.assertEqual(commitments.commitment_list()[0]["next_unpaid_due_date"], "2026-10-01")
        self.assertEqual(set(commitments.commitment_list()[0]["due_dates"].split(",")), {
            parse_jalali_date(row["due_date"]).isoformat() for row in rows
        })
        commitments.create_payment(schemas.PaymentInput(installment_id=rows[0]["id"], amount=1000, paid_on=date(2026, 10, 1)))
        listed = commitments.commitment_list()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["next_unpaid_due_date"], parse_jalali_date(rows[1]["due_date"]).isoformat())

    def test_editing_commitment_group_updates_all_related_months(self):
        first = commitments.create_commitment(schemas.CommitmentInput(
            title="وام رسالت", kind="وام", total_amount=1000,
            installment_amount=1000, first_due_date=date(2026, 10, 1), installment_count=1,
        ))
        second = commitments.create_commitment(schemas.CommitmentInput(
            title="وام رسالت", kind="وام", total_amount=2000,
            installment_amount=1000, first_due_date=date(2026, 11, 1), installment_count=2,
        ))
        other = commitments.create_commitment(schemas.CommitmentInput(
            title="تعهد دیگر", kind="بدهی", total_amount=500,
            installment_amount=500, first_due_date=date(2026, 12, 1), installment_count=1,
        ))
        result = commitments.update_commitment_group(first["id"], schemas.CommitmentGroupUpdate(title="وام اصلاح‌شده", kind="بدهی"))
        self.assertEqual(result["updated_count"], 2)
        for commitment_id, total in ((first["id"], 1000), (second["id"], 2000)):
            rows = commitments.installments(commitment_id=commitment_id)
            self.assertTrue(all((row["title"], row["kind"], row["total_amount"]) == ("وام اصلاح‌شده", "بدهی", total) for row in rows))
            details = commitments.installment_details(rows[0]["id"])
            self.assertTrue(any(log["resource_type"] == "commitment" and log["details"].get("scope") == "group" for log in details["history"]))
        self.assertEqual(commitments.installments(commitment_id=other["id"])[0]["title"], "تعهد دیگر")

    def test_partial_payment_reduces_installment_balance(self):
        commitments.create_commitment(schemas.CommitmentInput(
            title="وام آزمایشی", kind="وام", total_amount=3_000_000,
            installment_amount=1_000_000, first_due_date=date(2026, 10, 1), installment_count=3,
        ))
        installment = commitments.installments(month="1405-07")[0]
        commitments.create_payment(schemas.PaymentInput(
            installment_id=installment["id"], amount=400_000,
            paid_on=date(2026, 10, 1), account_id=1,
        ))
        updated = commitments.installments(month="1405-07")[0]
        self.assertEqual(updated["status"], "partial")
        self.assertEqual(updated["paid_amount"], 400_000)
        self.assertEqual(updated["remaining_amount"], 600_000)

    def test_payment_cannot_exceed_remaining_balance(self):
        commitments.create_commitment(schemas.CommitmentInput(
            title="وام آزمایشی", kind="وام", installment_amount=1_000_000,
            first_due_date=date(2026, 10, 1), installment_count=1,
        ))
        installment = commitments.installments(month="1405-07")[0]
        with self.assertRaises(Exception):
            commitments.create_payment(schemas.PaymentInput(
                installment_id=installment["id"], amount=1_000_001,
                paid_on=date(2026, 10, 1), account_id=1,
            ))

    def test_commitment_preview_creates_all_installments_before_save(self):
        preview = commitments.preview_commitment(schemas.CommitmentInput(
            title="وام ده قسطه", kind="وام", total_amount=10_000_000,
            installment_amount=1_000_000, first_due_date=date(2026, 10, 1),
            installment_count=10, interval_months=1,
        ))
        self.assertEqual(len(preview["installments"]), 10)
        self.assertEqual(preview["planned_total"], 10_000_000)
        self.assertEqual(preview["first_due_date"], "۱۴۰۵/۰۷/۰۹")
        self.assertEqual(preview["last_due_date"], "۱۴۰۶/۰۴/۰۹")

    def test_installment_filter_by_commitment_and_status(self):
        first = commitments.create_commitment(schemas.CommitmentInput(
            title="وام اول", kind="وام", installment_amount=1_000_000,
            first_due_date=date(2026, 10, 1), installment_count=1,
        ))
        commitments.create_commitment(schemas.CommitmentInput(
            title="وام دوم", kind="وام", installment_amount=2_000_000,
            first_due_date=date(2026, 10, 1), installment_count=1,
        ))
        filtered = commitments.installments(commitment_id=first["id"], status="unpaid")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["title"], "وام اول")

    def test_installment_filter_by_unique_title_and_total(self):
        commitments.create_commitment(schemas.CommitmentInput(
            title="وام مشابه", kind="وام", total_amount=10_000_000,
            installment_amount=1_000_000, first_due_date=date(2026, 10, 1), installment_count=1,
        ))
        commitments.create_commitment(schemas.CommitmentInput(
            title="وام مشابه", kind="وام", total_amount=20_000_000,
            installment_amount=2_000_000, first_due_date=date(2026, 10, 1), installment_count=1,
        ))
        filtered = commitments.installments(commitment_title="وام مشابه", commitment_total=10_000_000)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["amount"], 1_000_000)

    def test_rial_to_toman_migration_runs_only_once(self):
        with database.connection() as db:
            db.execute("INSERT INTO commitments(title, kind, total_amount) VALUES ('تبدیل', 'وام', 1000)")
            commitment_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.execute("INSERT INTO installments(commitment_id, due_date, amount) VALUES (?, '2026-10-01', 500)", (commitment_id,))
            installment_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.execute("INSERT INTO payments(installment_id, amount, paid_on) VALUES (?, 200, '2026-10-01')", (installment_id,))
            db.execute("DELETE FROM data_migrations WHERE migration_key = 'rial_amounts_to_toman_20260919'")
            db.execute("PRAGMA user_version = 0")
        database.initialize_database()
        with database.connection() as db:
            self.assertEqual(db.execute("SELECT total_amount FROM commitments WHERE id = ?", (commitment_id,)).fetchone()[0], 100)
            self.assertEqual(db.execute("SELECT amount FROM installments WHERE id = ?", (installment_id,)).fetchone()[0], 50)
            self.assertEqual(db.execute("SELECT amount FROM payments WHERE installment_id = ?", (installment_id,)).fetchone()[0], 20)
        database.initialize_database()
        with database.connection() as db:
            self.assertEqual(db.execute("SELECT total_amount FROM commitments WHERE id = ?", (commitment_id,)).fetchone()[0], 100)

    def test_backup_and_commitment_edits(self):
        created = commitments.create_commitment(schemas.CommitmentInput(
            title="تعهد قابل ویرایش", kind="وام", total_amount=2_000_000,
            installment_amount=1_000_000, first_due_date=date(2026, 10, 1), installment_count=2,
        ))
        commitments.update_commitment(created["id"], schemas.CommitmentUpdate(
            title="تعهد ویرایش‌شده", kind="بدهی", total_amount=2_500_000,
        ))
        installment = commitments.installments(commitment_id=created["id"])[0]
        commitments.update_installment(installment["id"], schemas.InstallmentUpdate(
            due_date=date(2026, 10, 2), amount=1_100_000, note="تغییر دستی",
        ))
        updated = commitments.installments(commitment_id=created["id"])[0]
        self.assertEqual(updated["title"], "تعهد ویرایش‌شده")
        self.assertEqual(updated["kind"], "بدهی")
        self.assertEqual(updated["amount"], 1_100_000)
        self.assertEqual(updated["note"], "تغییر دستی")
        backup = database.create_database_backup(Path(self.temp_dir.name) / "backups")
        self.assertTrue(backup.is_file())
