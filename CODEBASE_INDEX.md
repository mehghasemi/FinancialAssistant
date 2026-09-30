# نقشهٔ کد FinancialAssistant

این فایل فقط راهنمای یافتن کد فعال است؛ جزئیات رفتار را از کد همان بخش بخوانید. فرمان‌های زیر با `.\.venv\Scripts\python.exe -B scripts/check.py --scope` اجرا می‌شوند.

| موضوع | فایل‌های مرجع | دامنهٔ بررسی |
|---|---|---|
| راه‌اندازی و اتصال مسیرها | `app/main.py`، `app/launcher.py`، `launcher.py`، `run.ps1`، `scripts/dev.ps1`، `scripts/build.ps1`، `app/smoke.py` | `api`؛ سپس اجرای محلی در صورت نیاز |
| تعهد، اقساط و پرداخت | `app/services/finance.py`، `app/routers/commitments.py`، `app/schemas.py`، `app/utils.py` | `finance` و `api` |
| تقویم شمسی | `app/calendar.py`، `app/utils.py` | `calendar` و برای تغییر محاسبهٔ اقساط `finance` |
| دیتابیس، مهاجرت و پشتیبان | `app/database.py`، `app/migrations.py`، `app/services/backups.py`، `scripts/restore_backup.py` | `all` |
| درآمد، هزینه و داشبورد | `app/routers/transactions.py`، `app/routers/dashboard.py` | `all`؛ پوشش مستقیم فعلی محدود است |
| ورود Sheet4 از رابط و CLI | `app/routers/imports.py`، `app/services/excel_import.py`، `scripts/import_sheet4.py` | `api`؛ آپلود و جلوگیری از ورود تکراری |
| واردسازی جامع اکسل | `scripts/import_workbook.py` | `import` |
| رابط فارسی | `static/index.html`، `static/app.js`، `static/styles.css` | `syntax` و بررسی رفتار بخش تغییرکرده در مرورگر |
| نسخه و تنظیمات اجرا | `app/config.py`، `requirements.txt` | `syntax` و بررسی مرتبط با تغییر |

- `finance`: فایل `tests/test_financial_flow.py`؛ `calendar`: فایل `tests/test_jalali_calendar.py`؛ `import`: فایل `tests/test_workbook_import.py`.
- `api`: فایل `tests/test_api.py`؛ `recovery`: فایل `tests/test_recovery.py`؛ وابستگی تست در `requirements-dev.txt`.
- `syntax` پایتون فعال و JavaScript را بررسی می‌کند؛ در نبود Node بررسی JavaScript صریحاً skipped می‌شود. همهٔ دامنه‌ها ابتدا بررسی نحوی را اجرا می‌کنند.
- تست‌ها دیتابیس موقت دارند؛ تست HTTP چرخهٔ عمر برنامه را درون فرایند تست اجرا می‌کند. سرور واقعی یا دیتابیس کاربر اجرا نمی‌شود؛ خطاها exit code غیرصفر دارند.
- اجرا: فقط `release/FinancialAssistant.exe`؛ `run.ps1` میان‌بر آن است؛ دادهٔ نسخهٔ اجرایی در `data/` کنار EXE است. راهنمای ساخت و توسعه: `docs/development.md`. نسخه‌های تکراری ریشه و `excel-import-ui/` حذف شده‌اند.
- جزئیات معماری: `docs/architecture.md`؛ قراردادها: `docs/api.md`؛ تاریخچه: `CHANGELOG.md`. هنگام اختلاف، کد اجرایی مرجع است.

قواعد ویرایش امن و ارتقای داده در `docs/architecture.md` و روش بازیابی در `docs/recovery.md` هستند.

- رویدادنگاری: API در app/routers/settings.py، ثبت در سرویس مالی و مسیرهای تراکنش، تنظیمات و ورود اکسل؛ نمایش در بخش auditLog رابط. بررسی: api و all برای تغییر ثبت داده.
