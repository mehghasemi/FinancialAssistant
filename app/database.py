from __future__ import annotations

import hashlib
import re
import jdatetime
import sqlite3
import json
from contextlib import closing, contextmanager
from datetime import datetime
import os
from pathlib import Path
import sys
from threading import RLock
from functools import wraps

from .migrations import SCHEMA_VERSION, allocate_unique_code, run_migrations


ROOT_DIR = Path(__file__).resolve().parents[1]
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", ROOT_DIR))
PORTABLE_MODE = bool(getattr(sys, "frozen", False)) and not os.getenv("FINANCIAL_ASSISTANT_DATA_DIR")
LEGACY_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "FinancialAssistant"
if getattr(sys, "frozen", False):
    default_data_dir = Path(sys.executable).resolve().parent / "data"
else:
    default_data_dir = ROOT_DIR / "data"
DATA_DIR = Path(os.getenv("FINANCIAL_ASSISTANT_DATA_DIR", default_data_dir))
DATABASE_PATH = DATA_DIR / "financial_assistant.db"


DATABASE_LOCK = RLock()


def database_operation(function):
    @wraps(function)
    def locked(*args, **kwargs):
        with DATABASE_LOCK:
            return function(*args, **kwargs)
    return locked


def write_audit_log(db: sqlite3.Connection, action: str, resource_type: str, resource_id: int, details: str = "") -> None:
    db.execute(
        """INSERT INTO audit_logs(action, resource_type, resource_id, details, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (action, resource_type, resource_id, details, datetime.now().astimezone().isoformat()),
    )


@database_operation
def create_database_backup(destination: str | Path) -> Path:
    backup_dir = Path(destination or DATA_DIR / "backups").expanduser().resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = jdatetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
    backup_path = backup_dir / f"financial_assistant_backup_{timestamp}.db"
    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(DATABASE_PATH)
    source = sqlite3.connect(DATABASE_PATH.resolve().as_uri() + "?mode=ro", uri=True)
    target = sqlite3.connect(backup_path)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return backup_path


@contextmanager
def connection(*, write: bool = False, database_path: Path | None = None):
    with DATABASE_LOCK:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(database_path or DATABASE_PATH)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


@database_operation
def initialize_database(*, target_path: Path | None = None) -> None:
    candidate = target_path or DATABASE_PATH
    if target_path is None and PORTABLE_MODE and not candidate.exists():
        legacy = LEGACY_DATA_DIR / "financial_assistant.db"
        if legacy.is_file():
            from .services.backups import restore_backup
            restore_backup(legacy, candidate)
    if candidate.exists():
        with closing(sqlite3.connect(candidate)) as current:
            version = current.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError("Database was created by a newer application version")
        if version < SCHEMA_VERSION and target_path is None:
            create_database_backup(DATA_DIR / "backups")
    with connection(database_path=candidate) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL DEFAULT 'bank',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                transaction_type TEXT NOT NULL CHECK (transaction_type IN ('income', 'expense')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY,
                transaction_type TEXT NOT NULL CHECK (transaction_type IN ('income', 'expense')),
                amount INTEGER NOT NULL CHECK (amount > 0),
                occurred_on TEXT NOT NULL,
                category_id INTEGER REFERENCES categories(id),
                account_id INTEGER REFERENCES accounts(id),
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS commitments (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                kind TEXT NOT NULL,
                total_amount INTEGER CHECK (total_amount IS NULL OR total_amount > 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS installments (
                id INTEGER PRIMARY KEY,
                commitment_id INTEGER NOT NULL REFERENCES commitments(id) ON DELETE CASCADE,
                due_date TEXT NOT NULL,
                amount INTEGER NOT NULL CHECK (amount > 0),
                note TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY,
                installment_id INTEGER NOT NULL REFERENCES installments(id) ON DELETE CASCADE,
                amount INTEGER NOT NULL CHECK (amount > 0),
                paid_on TEXT NOT NULL,
                account_id INTEGER REFERENCES accounts(id),
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY,
                action TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id INTEGER NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS release_history (
                version TEXT PRIMARY KEY,
                released_at TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                affected_areas TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS data_migrations (
                migration_key TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS import_runs (
                id INTEGER PRIMARY KEY,
                source_name TEXT NOT NULL,
                source_path TEXT NOT NULL,
                workbook_hash TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
                total_rows INTEGER NOT NULL DEFAULT 0,
                mapped_commitments INTEGER NOT NULL DEFAULT 0,
                mapped_installments INTEGER NOT NULL DEFAULT 0,
                mapped_payments INTEGER NOT NULL DEFAULT 0,
                mapped_budget_items INTEGER NOT NULL DEFAULT 0,
                imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                error_message TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS imported_rows (
                id INTEGER PRIMARY KEY,
                import_id INTEGER NOT NULL REFERENCES import_runs(id) ON DELETE CASCADE,
                sheet_name TEXT NOT NULL,
                source_row INTEGER NOT NULL,
                record_type TEXT NOT NULL DEFAULT 'raw',
                data_json TEXT NOT NULL,
                UNIQUE(import_id, sheet_name, source_row)
            );

            CREATE TABLE IF NOT EXISTS budget_items (
                id INTEGER PRIMARY KEY,
                fiscal_year INTEGER NOT NULL,
                category_name TEXT NOT NULL,
                jalali_month INTEGER NOT NULL CHECK (jalali_month BETWEEN 1 AND 12),
                amount INTEGER NOT NULL CHECK (amount >= 0),
                import_id INTEGER REFERENCES import_runs(id) ON DELETE SET NULL,
                source_key TEXT UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_transactions_occurred_on ON transactions(occurred_on);
            CREATE INDEX IF NOT EXISTS idx_installments_due_date ON installments(due_date);
            CREATE INDEX IF NOT EXISTS idx_payments_paid_on ON payments(paid_on);
            CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_imported_rows_import_sheet ON imported_rows(import_id, sheet_name);
            CREATE INDEX IF NOT EXISTS idx_budget_items_year_month ON budget_items(fiscal_year, jalali_month);
            """
        )

        run_migrations(db)
        db.execute(
            "INSERT OR IGNORE INTO app_settings(setting_key, setting_value) VALUES ('backup_enabled', 'true')"
        )
        db.execute(
            "INSERT OR IGNORE INTO app_settings(setting_key, setting_value) VALUES ('backup_directory', ?)",
            (str(DATA_DIR / "backups"),),
        )

        db.execute("""INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
                   VALUES ('0.28.0', '2026-10-08T18:26:26+03:30', 'انتخاب دوره و یکپارچه‌سازی منوها',
                   'پنجرهٔ سال و ماه؛ نمودارهای جداشده و چهار مورد نیازمند اقدام؛ منوهای گروهی و تنظیمات با کارت‌های میان‌بر.', 'رابط کاربری، داشبورد')""")
        db.execute("""INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
                   VALUES ('0.27.0', '2026-10-08T11:19:38+03:30', 'گردش پرداخت‌ها و داشبورد فشرده',
                   'فیلتر گردش بر اساس تاریخ پرداخت؛ داشبورد فشرده؛ ماندهٔ قابل پس‌انداز پس از کسر پرداخت‌نشده‌های ماه انتخابی.', 'داشبورد، گزارش گردش')""")
        db.execute("""INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
                   VALUES ('0.26.0', '2026-10-08T11:13:06+03:30', 'بررسی تاریخ پرداخت‌ها',
                   'تاریخ پرداخت کنار سررسید؛ گزارش اختلاف تاریخ و ماه و تأیید تاریخ‌های فرض‌شدهٔ وارداتی.', 'داشبورد، اقساط، پرداخت‌ها')""")
        db.execute("""INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
                   VALUES ('0.17.0', '2026-09-30T18:00:00+03:30', 'داشبورد فشرده و جمع جدول‌ها',
                           'کاهش فاصله‌های داشبورد و نمایش جمع نتایج فیلترشده در جدول‌های مالی.', 'رابط کاربری')""")
        if PORTABLE_MODE:
            location = str(DATA_DIR.resolve())
            previous = db.execute("SELECT setting_value FROM app_settings WHERE setting_key = 'portable_data_directory'").fetchone()
            if previous is None or previous[0] != location:
                db.execute("UPDATE app_settings SET setting_value = ? WHERE setting_key = 'backup_directory'", (str(DATA_DIR / "backups"),))
                db.execute("INSERT OR REPLACE INTO app_settings(setting_key, setting_value) VALUES ('portable_data_directory', ?)", (location,))

        db.execute("""INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
                   VALUES ('0.19.0', '2026-10-04T12:00:00+03:30', 'دارایی‌ها و گزارش مالی یکپارچه',
                           'نمایش آخرین تغییر اطلاعات؛ مدیریت دارایی و تاریخچهٔ ارزش؛ ویرایش و حذف درآمد و هزینه؛ گزارش فیلترپذیر اقساط و تعهدات بدون دوباره‌شماری؛ ورود زندهٔ مبالغ فارسی و مبلغ به حروف.', 'دارایی‌ها، تراکنش‌ها، گزارش و نمایش اعداد')""")
        db.execute("""INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
                   VALUES ('0.20.0', '2026-10-04T18:00:00+03:30', 'جمع‌بندی هزینه‌ها و جدول‌های مرتب‌شونده',
                           'تعهدات برنامه‌ریزی‌شده، سایر هزینه‌ها و مجموع هزینه‌ها؛ فرم کشویی تراکنش و مرتب‌سازی جدول‌ها.', 'گزارش مالی و رابط کاربری')""")
        db.execute("""INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
                   VALUES ('0.20.1', '2026-10-04T19:00:00+03:30', 'مبلغ به حروف فقط هنگام ورود اطلاعات',
                           'حذف مبلغ به حروف از جدول‌ها و خلاصه‌ها و حفظ آن در فیلدهای ورود و ویرایش مبلغ.', 'رابط کاربری')""")
        db.execute("""INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
                   VALUES ('0.21.0', '2026-10-04T20:00:00+03:30', 'خروج امن و داشبورد یکپارچه',
                           'پشتیبان هنگام خروج در صورت تغییر، نام شمسی بکاپ و پاک‌سازی توضیحات خودکار اکسل؛ خلاصهٔ یکپارچهٔ هزینه‌ها.', 'پشتیبان و داشبورد')""")
        db.execute("""INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
                   VALUES ('0.21.1', '2026-10-04T21:00:00+03:30', 'بکاپ با بستن برنامه و جدول فشرده',
                           'حذف دکمهٔ خروج؛ پشتیبان هنگام بستن پنجرهٔ EXE؛ پیام فارسی قطع اتصال؛ وضعیت متنی رنگی و سطرهای فشرده.', 'اجرا و جدول‌ها')""")
        db.execute("""INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
                   VALUES ('0.22.0', '2026-10-06T12:00:00+03:30', 'گزارش خواناتر و منوی مرتب',
                           'رنگ متن سطرها بر اساس پرداخت، راهنمای کارت‌ها، فیلتر بالای جدول، ساعت شمسی زنده و رویدادنگاری زیر تنظیمات.', 'رابط کاربری')""")
        db.execute("""INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
                   VALUES ('0.23.0', '2026-10-06T18:00:00+03:30', 'کنترل تراکنش تکراری و بودجهٔ ماهانه',
                           'هشدار و بررسی تراکنش‌های مشابه، اتصال هزینه به پرداخت قسط بدون دوباره‌شماری و بودجهٔ ماهانهٔ دسته‌های هزینه.', 'تراکنش، اقساط و بودجه')""")
        db.execute("""INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
                   VALUES ('0.24.0', '2026-10-07T16:22:00+03:30', 'اطلاعات پایه و جریان نقدی',
                   'تعریف بانک و حساب و موجودی، تفکیک معوقات و موجودی واقعی، سه نمودار مالی و دسترسی سریع به پشتیبان.', 'داشبورد، اطلاعات پایه، پشتیبان')""")
        db.execute("""INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
                   VALUES ('0.25.0', '2026-10-07T16:46:12+03:30', 'تقویم شمسی، بازیابی و راهنمای برنامه',
                   'انتخابگر مشترک تاریخ شمسی، ارقام و قالب یکسان؛ بازیابی از فایل پس از اعتبارسنجی و تهیهٔ پشتیبان از اطلاعات فعلی؛ دکمهٔ بکاپ زیر آخرین منو و راهنمای کامل بخش‌ها.', 'تاریخ‌ها، تنظیمات و راهنما')""")
        accounts = ("حساب اصلی", "کارت بانکی", "نقدی")
        db.execute("""INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
                   VALUES ('0.18.0', '2026-09-30T20:00:00+03:30', 'اجرای قابل‌حمل با اطلاعات کنار برنامه',
                           'نگهداری دیتابیس و بکاپ پیش‌فرض در پوشهٔ data کنار EXE و انتقال امن اطلاعات نسخهٔ قبلی با حفظ فایل اصلی.', 'اجرا و نگهداری اطلاعات')""")
        db.execute("""INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
                   VALUES ('0.16.1', '2026-09-30T16:00:00+03:30', 'اصلاح مبلغ اقساط متفاوت',
                           'یکسان‌سازی صریح مبلغ اقساط، محاسبهٔ بازپرداخت و خطای دقیق با حفظ پرداخت‌ها.', 'تعهدات')""")
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.16.0', '2026-09-30T12:00:00+03:30', 'داشبورد خلوت و کاربردی',
                       'سه کارت خلاصه، ظاهر سرمه‌ای و فیروزه‌ای، فهرست یکپارچهٔ معوق و امروز و هفت روز آینده و پیشرفت پرداخت ماه انتخابی.',
                       'داشبورد و رابط کاربری')"""
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.15.0', '2026-09-29T18:00:00+03:30', 'مدیریت تعهد و داشبورد سررسید',
                       'ویرایش یکپارچه، محاسبهٔ بازپرداخت از اقساط، حذف کامل با تأیید و نمایش ماه جاری و معوقات بر مبنای سررسید.',
                       'تعهدات و داشبورد')"""
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.14.0', '2026-09-29T17:00:00+03:30', 'ویرایش مستقل قسط و رویدادنگاری',
                       'به‌روزرسانی بازپرداخت با اختلاف مبلغ قسط؛ رویدادنگاری تاریخ‌دار با جزئیات و حفظ سوابق پس از پاک‌سازی.',
                       'اقساط، تعهدات، تنظیمات و رویدادها')"""
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.13.0', '2026-09-29T16:00:00+03:30', 'ستون‌ها و فیلترهای تعهدات',
                       'نمایش شروع و پایان، مبالغ و تعداد اقساط باقی‌مانده؛ فیلتر سال شمسی شروع و پایان، تسویه و قسط معوق.',
                       'فهرست تعهدات')"""
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.12.0', '2026-09-29T15:00:00+03:30', 'فهرست تعهدات و جزئیات اقساط',
                       'ستون‌ها و فیلترهای مستقل تعهد؛ مشاهدهٔ خلاصه و اقساط هر کد تعهد با امکان پرداخت و ویرایش.',
                       'تعهدات و اقساط')"""
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.11.1', '2026-09-29T14:00:00+03:30', 'نسخهٔ تجمیعی تنظیمات و ورود اکسل',
                       'تجمیع پاک‌سازی امن اطلاعات با پشتیبان اجباری، قالب و راهنمای اکسل و اعتبارسنجی کامل پیش از ثبت؛ حفظ تاریخچهٔ نسخه‌های قبلی.',
                       'نسخه، تنظیمات و ورود اکسل')"""
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.11.0', '2026-09-29T13:00:00+03:30', 'اعتبارسنجی پیش از ورود اکسل',
                       'بررسی همهٔ ردیف‌ها پیش از ثبت، اعلام خطا با شمارهٔ ردیف و جلوگیری از ورود ناقص یا متداخل.',
                       'ورود اکسل و تنظیمات')"""
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.10.0', '2026-09-29T12:00:00+03:30', 'راهنما و قالب ورود اکسل',
                       'دانلود قالب خالی اکسل همراه با راهنما، نمونه و توضیح سرتیترها در بخش ورود اطلاعات.',
                       'تنظیمات و ورود اکسل')"""
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.9.0', '2026-09-29T00:00:00+03:30', 'پاک‌سازی اطلاعات برای ورود مجدد',
                       'پاک کردن اطلاعات مالی و سوابق ایمپورت از تنظیمات با تأیید کاربر و پشتیبان اجباری؛ حفظ حساب‌ها و دسته‌بندی‌ها.',
                       'تنظیمات، اطلاعات مالی و ورود اکسل')"""
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.8.0', '2026-09-28T00:00:00+03:30', 'بازپرداخت و ویرایش کامل تعهد',
                       'اصلاح مدیریت داشبورد، دریافت بازپرداخت، ویرایش همهٔ اقساط با حفظ پرداخت و ارتقای امن اطلاعات.',
                       'داشبورد، تعهدات، اقساط، دیتابیس و اجرای ویندوز')"""
        )
        seed_references = not db.execute("SELECT 1 FROM app_settings WHERE setting_key='reference_defaults_initialized'").fetchone()
        if seed_references:
            db.executemany("INSERT OR IGNORE INTO accounts(name) VALUES (?)", ((name,) for name in accounts))

        categories = (
            ("درآمد شغلی", "income"),
            ("درآمد دیگر", "income"),
            ("خانه", "expense"),
            ("خوراک", "expense"),
            ("حمل‌ونقل", "expense"),
            ("درمان", "expense"),
            ("آموزش", "expense"),
            ("سایر", "expense"),
        )
        if seed_references:
            db.executemany("INSERT OR IGNORE INTO categories(name, transaction_type) VALUES (?, ?)", categories)
            db.execute("UPDATE accounts SET kind='cash' WHERE name='نقدی'")
            db.execute("INSERT INTO app_settings(setting_key,setting_value) VALUES ('reference_defaults_initialized','true')")
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.2.0', '2026-09-19T00:00:00+03:30', 'پایهٔ قابل استفاده',
                       'ثبت تراکنش، تعهد، سررسید و پرداخت جزئی با دیتابیس محلی.',
                       'رابط کاربری، API، منطق مالی، SQLite و مستندات')"""
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.4.0', '2026-09-19T00:00:00+03:30', 'واردسازی اکسل',
                       'بایگانی کامل ردیف‌های اکسل و تبدیل امن تعهدات مالی و بودجه‌ها به داده‌های عملیاتی.',
                       'دیتابیس محلی، واردسازی، تعهدات، اقساط و بودجه')"""
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.4.1', '2026-09-19T00:00:00+03:30', 'راهنمای سیستم',
                       'انتقال توضیح محل نگهداری داده‌ها از نوار کناری به صفحهٔ راهنمای سیستم.',
                       'رابط کاربری و راهنما')"""
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.5.0', '2026-09-19T00:00:00+03:30', 'مدیریت تعهدات و اقساط',
                       'تعریف یکجای تعهد، پیش‌نمایش اقساط، فیلتر گرید و ثبت پرداخت از همان ردیف.',
                       'تعهدات مالی، اقساط و پرداخت‌ها')"""
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.5.1', '2026-09-19T00:00:00+03:30', 'فیلتر یکتای تعهدات',
                       'نمایش هر ترکیب عنوان و مبلغ کل فقط یک‌بار در فیلتر تعهدات.',
                       'فیلتر اقساط')"""
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.5.2', '2026-09-19T00:00:00+03:30', 'تبدیل ریال به تومان',
                       'تبدیل یک‌بارهٔ مبالغ عملیاتی و نمایش جداکنندهٔ هزارگان.',
                       'مبالغ، فیلتر تعهدات و رابط کاربری')"""
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.6.0', '2026-09-19T00:00:00+03:30', 'پشتیبان‌گیری و ویرایش تعهدات',
                       'تنظیمات پشتیبان‌گیری، فیلتر وضعیت هوشمند و ویرایش کلی و جزئی تعهدات.',
                       'تنظیمات، پشتیبان‌گیری، تعهدات و اقساط')"""
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.6.1', '2026-09-19T00:00:00+03:30', 'گرید تعهدات',
                       'افزودن فهرست مستقل تعهدات و ویرایش کلی هر تعهد در همان گرید.',
                       'مدیریت تعهدات')"""
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.7.0', '2026-09-26T00:00:00+03:30', 'فهرست تجمیعی و ویرایش گروهی',
                       'نمایش یک‌بارهٔ هر عنوان، فیلترهای چندانتخابی، ویرایش همهٔ ریزتعهدهای هم‌عنوان و اصلاح پرداخت با تاریخچه.',
                       'مدیریت تعهدات، اقساط، پرداخت‌ها و رابط کاربری')"""
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.3.0', '2026-09-19T00:00:00+03:30', 'تقویم شمسی',
                       'ورود، نمایش و فیلتر تاریخ‌ها با تقویم جلالی و نام ماه‌های فارسی.',
                       'رابط کاربری، API، گزارش‌ها و مستندات')"""
        )


def get_setting(key: str, default: str = "") -> str:
    with connection() as db:
        row = db.execute("SELECT setting_value FROM app_settings WHERE setting_key = ?", (key,)).fetchone()
    return row["setting_value"] if row else default


def clear_financial_data() -> Path:
    """Back up under a write lock, then atomically clear operational data."""
    with connection(write=True) as db:
        backup_path = create_database_backup(DATA_DIR / "backups")
        tables = ("cash_opening", "monthly_budgets", "asset_values", "assets", "payments", "installments", "commitments", "transactions", "budget_items", "imported_rows", "import_runs")
        counts = {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}
        db.execute("UPDATE audit_logs SET resource_type = 'archived_' || resource_type WHERE resource_type NOT LIKE 'archived_%'")
        for table in tables:
            db.execute(f"DELETE FROM {table}")
        db.execute("UPDATE accounts SET opening_amount=NULL,opening_date=NULL")
        write_audit_log(db, "delete", "system", 0, json.dumps({"before": counts, "backup_path": str(backup_path)}, ensure_ascii=False))
    return backup_path


def set_setting(key: str, value: str) -> None:
    with connection() as db:
        db.execute(
            """INSERT INTO app_settings(setting_key, setting_value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value, updated_at = CURRENT_TIMESTAMP""",
            (key, value),
        )


def database_fingerprint() -> str:
    """Snapshot fingerprint detects committed writes, including imports and deletes."""
    with connection() as db:
        return hashlib.sha256(db.serialize()).hexdigest()


def clean_import_notes() -> int:
    patterns = (
        r"واردشده از Sheet4 اکسل(?: \(کد گروه: [0-9۰-۹]+\))?",
        r"واردشده از شیت تعهدات مالی",
        r"واردشده از اکسل[؛،]?\s*",
    )
    changes = []
    with connection() as db:
        for table in ("installments", "payments", "transactions", "assets"):
            for row in db.execute(f"SELECT id, note FROM {table} WHERE note LIKE '%واردشده از%'"):
                cleaned = row["note"]
                for pattern in patterns:
                    cleaned = re.sub(pattern, "", cleaned)
                cleaned = cleaned.strip(" |؛،\n")
                if cleaned != row["note"]:
                    changes.append((table, row["id"], row["note"], cleaned))
    if not changes:
        return 0
    create_database_backup(get_setting("backup_directory", ""))
    with connection(write=True) as db:
        for table, identifier, before, after in changes:
            db.execute(f"UPDATE {table} SET note = ? WHERE id = ? AND note = ?", (after, identifier, before))
            write_audit_log(db, "update", table, identifier, json.dumps({"before": {"note": before}, "after": {"note": after}}, ensure_ascii=False))
    return len(changes)
