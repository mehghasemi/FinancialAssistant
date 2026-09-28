# FinancialAssistant — کدبیس شناسه (Index)

**آخرین بروزرسانی:** ۱۴۰۵/۰۶/۰۸ (fix-persian-dates)  
**حالت:** 
- تاریخ‌ها شمسی (خودکار تبدیل از ISO/میلادی)
- تابع `toJalaliDate()` برای تبدیل تاریخ‌ها
- Modal ویرایش: تاریخ اولین قسط شمسی

---

## Backend — Python

### `app/database.py` (۳۵۸ خط)
| تابع/کلاس | خط | توضیح |
|---|---|---|
| `connection()` | ۲۳-۲۸ | اتصال SQLite |
| `initialize_database()` | ۶۰-۲۰۰ | ایجاد/تصحیح جداول |
| `allocate_unique_code()` | ۲۰۲-۲۱۰ | تولید کد ۳ رقمی (001, 002, ...) |
| `_assign_missing_unique_codes()` | ۲۱۲-۲۲۰ | پرکردن کدهای قدیمی (migration) |
| `_apply_rial_to_toman_migration()` | ۲۲۲-۲۴۵ | تبدیل مقادیر ریال→توان |
| `write_audit_log()` | ۲۴۷-۲۶۰ | ثبت تغییرات |

**جداول اصلی:**
- `commitments`: id, title, kind, total_amount, **repayment_amount**, **unique_code**, source_key, created_at
- `installments`: id, commitment_id, due_date, amount, note, source_key
- `payments`: id, installment_id, amount, paid_on, account_id, note, source_key

---

### `app/routers/commitments.py` (۲۹۶ خط)
| Endpoint | متد | خط | توضیح |
|---|---|---|---|
| `/commitments` | POST | ۲۶-۴۵ | ساخت تعهد + اقساط (unique_code خودکار) |
| `/commitments` | GET | ۴۷-۸۰ | لیست تعهدات (شامل unique_code) |
| `/commitments/{id}` | PATCH | ۸۲-۱۱۰ | ویرایش تعهد (تکی، نه گروپی) |
| `/commitments/preview` | POST | ۱۱۲-۱۳۵ | پیش‌نمایش اقساط |
| `/installments` | GET | ۱۳۷-۱۸۵ | لیست اقساط |
| `/installments/{id}` | PATCH | ۱۸۷-۲۱۰ | ویرایش قسط (repayment validation) |
| `/payments` | POST | ۲۱۲-۲۳۰ | ثبت پرداخت |
| `/payments/{id}` | PATCH | ۲۳۲-۲۵۰ | ویرایش پرداخت |
| `/commitment-filters` | GET | ۲۶۲-۲۹۶ | فیلترهای جدول |

**اعتبارسنجی‌های اصلی:**
- خط ۲۹-۳۱: repayment_amount = sum(installments.amount) ✅
- خط ۱۹۲-۱۹۹: قسط‌ها: repayment_amount باید یکی باشد ✅

---

### `app/services/excel_import.py` (۱۶۷ خط)
| تابع | خط | توضیح |
|---|---|---|
| `import_sheet4()` | ۴۰-۱۶۵ | ایمپورت Sheet4 اکسل (idempotent) |
| `_cell_text()` | ۲۸-۳۰ | تمیز‌کردن متن |
| `_amount_value()` | ۳۲-۴۰ | تبدیل مبلغ ریال→توان (÷۱۰) |
| `ExcelImportError` | ۲۳-۲۵ | Exception اختصاصی |

**قوانین ایمپورت:**
- خط ۵: فقط Sheet4
- خط ۷۲: مبلغ ÷۱۰ (ریال→توان)
- خط ۸۷: unique_code خودکار روی تعهد
- خط ۱۰۰-۱۲۰: repayment_amount = sum اقساط گروه

---

### `app/routers/imports.py` (۲۰ خط)
| Endpoint | متد | خط |
|---|---|---|
| `/imports/sheet4` | POST | ۸-۲۰ |

---

## Frontend — JavaScript

### `static/app.js` (۳۶۷ خط)

#### متغیرهای عمومی
| متغیر | خط | توضیح |
|---|---|---|
| `api()` | ۱-۴ | fetch helper |
| `commitmentList` | ۱۰ | آرایهٔ تعهدات (تکی، نه گروپ) |
| `commitmentSort` | ۱۱ | {key, direction} |
| `commitmentGridFilters` | ۱۲ | Map فیلترها |

#### توابع رندر
| تابع | خط | توضیح |
|---|---|---|
| `groupedCommitments()` | ۷۵-۸۶ | **نقشه:** هر item = یک ردیف (بدون گروپ) |
| `commitmentDisplay()` | ۶۷-۷۴ | محاسبهٔ status, distance |
| `renderCommitmentGrid()` | ۱۲۴-۱۶۵ | رندر جدول (۱۰ ستون: کد، عنوان، نوع، مبلغ، اقساط، ...) |
| `renderCommitmentFilters()` | ۱۰۴-۱۲۳ | فیلترها |
| `matchesCommitmentFilters()` | ۹۴-۱۰۲ | تطابق فیلتر (تکی، نه گروپی) |

#### توابع ویرایش (Inline Modal)
| تابع | خط | توضیح |
|---|---|---|
| `openGridCommitmentEdit()` | ۲۱۶-۲۲۲ | ویرایش تعهد **تکی** (نه گروپی) |
| `openInlineInstallmentEdit()` | ۲۱۰-۲۱۵ | ویرایش قسط |
| `openInlinePayment()` | ۱۶۸-۱۷۵ | ثبت پرداخت |

#### Event Listeners
| رویداد | خط | عنصر | عملیات |
|---|---|---|---|
| click | ۲۶۱ | `#commitmentRows` | `.edit-grid-group` (ویرایش تکی) |
| submit | ۲۶۲-۲۷۱ | commitment form | PATCH /commitments/{id} (تکی) |
| click | ۲۹۷ | `#commitmentGridFilters` | toggle فیلتر |

---

### `static/index.html` (۹۷ خط)

#### Grid Header
| ستون | خط | توضیح |
|---|---|---|
| کد یکتا | ۴۲ | unique_code (001, 002, 003, ...) |
| عنوان | ۴۲ | title |
| نوع | ۴۲ | kind |
| مبلغ کل | ۴۲ | total_amount (اطلاعاتی) |
| اقساط | ۴۲ | installment_count |
| جمع‌اقساط | ۴۲ | planned_amount |
| پرداخت | ۴۲ | paid_amount |
| وضعیت | ۴۲ | settled/partial/unpaid |
| فاصله | ۴۲ | روز مانده/گذشته |
| عملیات | ۴۲ | ویرایش (تکی) |

---

## Database Schema (جاری)

### commitments
```sql
id              INTEGER PRIMARY KEY
title           TEXT
kind            TEXT
total_amount    INTEGER         /* مبلغ اطلاعاتی، بدون اعتبارسنجی */
repayment_amount INTEGER        /* = SUM(installments.amount) → اعتبار سنجی */
unique_code     TEXT UNIQUE     /* 001, 002, 003, ... */
source_key      TEXT UNIQUE     /* برای idempotency ایمپورت */
created_at      TIMESTAMP
```

### installments
```sql
id              INTEGER PRIMARY KEY
commitment_id   INTEGER FOREIGN KEY → commitments(id)
due_date        TEXT (YYYY-MM-DD)
amount          INTEGER
note            TEXT
source_key      TEXT UNIQUE
```

### payments
```sql
id              INTEGER PRIMARY KEY
installment_id  INTEGER FOREIGN KEY → installments(id)
amount          INTEGER
paid_on         TEXT (YYYY-MM-DD)
account_id      INTEGER (nullable)
note            TEXT
source_key      TEXT UNIQUE
```

---

## مراجع سریع

### وقتی می‌خوای:
- **اضافه کردن فیلد تعهد:** `app/database.py` ۱۸۰-۱۹۰ + `app/schemas.py` ۱۰-۲۲
- **اضافه کردن Endpoint:** `app/routers/commitments.py` + schema
- **تغییر رندر جدول:** `static/app.js` ۱۲۴-۱۶۵ (renderCommitmentGrid)
- **تغییر ستون جدول:** `static/index.html` ۴۲ + `static/app.js` ۱۲۴ (HTML generation)
- **تغییر ویرایش:** `static/app.js` ۲۱۶-۲۲۲ (openGridCommitmentEdit) — **هفت تکی، نه گروپی**
- **تغییر فیلتر:** `static/app.js` ۱۰۴-۱۲۳ (renderCommitmentFilters)
- **تغییر ایمپورت:** `app/services/excel_import.py` ۴۰-۱۶۵

---

## نکات کلیدی (single-row-grid)

✅ **هر تعهد = یک ردیف مستقل**
- سه «خرجی خانه» = ۳ ردیف جداگانه (کدهای ۰۰۱، ۰۰۲، ۰۰۳)
- دکمهٔ "ویرایش" = **فقط آن ردیف**، نه همهٔ هم‌نام‌ها

✅ **Unique Code درستی**
- هر تعهد کدش توی جدول نشون داده می‌شه
- موقع ایمپورت: `allocate_unique_code()` اختصاص می‌دهد
- Migration: تعهدات قدیمی کدهاشان خودکار دریافت می‌کنند

✅ **repayment_amount**
- خط ۲۹-۳۱ commitments.py: sum(installments) = repayment_amount ✅
- دیگه total_amount سقفی نیست

