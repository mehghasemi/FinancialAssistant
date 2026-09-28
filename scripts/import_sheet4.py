from __future__ import annotations

"""CLI wrapper around app.services.excel_import.import_sheet4.

Usage:
    python scripts/import_sheet4.py "path\to\file.xlsx"

The same logic now also runs from the web UI (تنظیمات → ورود داده از اکسل),
via POST /api/imports/sheet4 — this script remains for command-line use.
"""

import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app.services.excel_import import ExcelImportError, import_sheet4  # noqa: E402


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("استفاده: python scripts/import_sheet4.py <path-to-xlsx>")
    path = Path(sys.argv[1])
    if not path.exists():
        raise SystemExit(f"فایل پیدا نشد: {path}")
    try:
        result = import_sheet4(path.read_bytes())
    except ExcelImportError as error:
        raise SystemExit(str(error))
    print(result)
