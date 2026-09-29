# همراه مالی

وب‌اپ شخصیِ محلی برای مدیریت درآمد، هزینه، بودجه و تعهدات مالی.

## اجرا در ویندوز

روی `release/FinancialAssistant.exe` دوبار کلیک کنید. مرورگر پس از آماده‌شدن برنامه باز می‌شود. پنجرهٔ برنامه را باز نگه دارید و برای خروج امن در همان پنجره `Ctrl+C` بزنید؛ بستن تب مرورگر، سرویس را متوقف نمی‌کند.

`run.ps1` فقط میان‌بری برای همین EXE است و نسخهٔ جداگانه‌ای اجرا نمی‌کند. دادهٔ اجرای عادی در `%LOCALAPPDATA%/FinancialAssistant/financial_assistant.db` قرار دارد. تغییر محل داده فقط با `FINANCIAL_ASSISTANT_DATA_DIR` انجام می‌شود؛ دیتابیس قبلی توسعه در `data/` خودکار منتقل یا حذف نمی‌شود.

برای نصب و به‌روزرسانی [راهنمای اجرا](INSTALL.md) و برای اجرای کد، تست و ساخت EXE [راهنمای توسعه](docs/development.md) را ببینید.

## معماری

- رابط کاربری: HTML/CSS/JavaScript
- API محلی: FastAPI
- دیتابیس محلی: SQLite
- لایهٔ داده: اتصال مستقیم SQLite و ارتقای تدریجی schema در `app/migrations.py`
- اجرا: یک سرویس محلی که فقط روی `localhost` در دسترس است

جداسازی «تعهد»، «سررسید» و «پرداخت» اصل محوری مدل داده است. با این کار پرداختِ جزئی، پرداخت با تأخیر و گزارش‌های برنامه‌ای در برابر واقعی، قابل اتکا می‌شوند.

جزئیات فازها در [docs/project-phases.md](docs/project-phases.md) آمده است.

## مستندات

برای یافتن فایل و تست مرتبط، [نقشهٔ کد](CODEBASE_INDEX.md) را ببینید. بررسی استاندارد: `.\.venv\Scripts\python.exe -B scripts/check.py --scope all`؛ دامنه‌های محدودتر: `syntax`، `calendar`، `finance` و `import`.

وابستگی‌های تست: `.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`. دامنهٔ `api` برای تست HTTP و `recovery` برای مهاجرت و بازیابی است. [راهنمای بازیابی بکاپ](docs/recovery.md).

- [معماری](docs/architecture.md)
- [قرارداد API](docs/api.md)
- [تاریخچهٔ تغییرات](CHANGELOG.md)
- [تنظیمات نمونه](.env.example)
