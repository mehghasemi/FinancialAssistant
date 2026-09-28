# نصب تغییرات: Fix Persian Dates

## مراحل نصب:

### ۱) فایل‌ها را جایگزین کن
```powershell
$src = "D:\MyData\MyApp-AI\NewFileForFinancialAssistant\final-package"
$dst = "D:\MyData\MyApp-AI\FinancialAssistant"

# Frontend
Copy-Item "$src\static\app.js" "$dst\static\app.js" -Force
```

### ۲) تست برنامه
```powershell
cd D:\MyData\MyApp-AI\FinancialAssistant
.\.venv\Scripts\python.exe -c "from app.main import app; print('OK')"
```

### ۳) اجرای برنامه
```powershell
.\run.ps1
```

### ۴) تست در مرورگر
- **منو:** مدیریت تعهدات
- **گرید:** دکمهٔ "ویرایش" یک تعهد
- **تاریخ اولین قسط:** باید شمسی باشد (مثلاً ۱۴۰۵/۰۶/۲۸)

---

## تغییرات خلاصه

✅ **تابع تبدیل تاریخ:**
- `toJalaliDate()` — تاریخ میلادی (ISO) → شمسی

✅ **استفاده در Modal ویرایش:**
- تاریخ اولین قسط شمسی نمایش داده می‌شود
- Input فیلد: شمسی

