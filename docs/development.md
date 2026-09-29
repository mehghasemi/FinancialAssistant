# توسعه و ساخت نسخهٔ اجرایی

روش استفادهٔ معمول کاربر، `release/FinancialAssistant.exe` است. دستورهای این صفحه برای توسعه‌دهنده‌اند.

## آماده‌سازی

از ریشهٔ پروژه، با Python سازگار با وابستگی‌ها (ساخت فعلی با Python 3.14):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
```

برای توسعه و تست بدون بسته‌بندی، `requirements-dev.txt` کافی است.

## اجرای کد

```powershell
.\scripts\dev.ps1
```

این اجرا با reload و دیتابیس توسعهٔ `data/financial_assistant.db` است. اگر `FINANCIAL_ASSISTANT_DATA_DIR` از قبل تنظیم شده، همان مسیر استفاده می‌شود. هم‌زمان با EXE روی پورت ۸۰۰۰ اجرا نشود. دادهٔ توسعه با دادهٔ EXE ادغام نمی‌شود.

## ساخت و تحویل

```powershell
.\scripts\build.ps1
```

فرمان، تست‌ها را اجرا می‌کند، EXE موقت می‌سازد و خود EXE را با `--self-test` روی دیتابیس موقت و پورت آزاد می‌آزماید. این بررسی HTTP، منابع رابط، پرداخت، بکاپ، بازیابی و خروج را پوشش می‌دهد؛ مرورگری باز نمی‌شود و دادهٔ کاربر دست‌نخورده می‌ماند. فقط پس از موفقیت، فایل `release/FinancialAssistant.exe` جایگزین می‌شود. نسخهٔ قبلی باید بسته باشد.

خروجی موقت و لاگ در `build/` هستند؛ فایل‌های `build/`، `release/`، دیتابیس و بکاپ در Git ثبت نمی‌شوند. محتویات `static/` در EXE بسته‌بندی می‌شوند؛ دادهٔ کاربر هرگز داخل بسته نیست.

برای بررسی دوبارهٔ یک EXE بدون بیلد:

```powershell
.\release\FinancialAssistant.exe --self-test
```
