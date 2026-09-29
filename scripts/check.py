"""Run scoped checks without starting the app or opening the user's database."""
from __future__ import annotations

import argparse
import ast
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PATTERNS = {
    "calendar": "test_jalali_calendar.py",
    "finance": "test_financial_flow.py",
    "import": "test_workbook_import.py",
    "api": "test_api.py",
    "recovery": "test_recovery.py",
    "all": "test_*.py",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=["syntax", *PATTERNS], default="all")
    args = parser.parse_args()
    paths = [ROOT / "launcher.py"]
    for folder in ("app", "scripts", "tests"):
        paths.extend(sorted((ROOT / folder).rglob("*.py")))
    for path in paths:
        ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    print(f"Python syntax: OK ({len(paths)} files)", flush=True)
    node = shutil.which("node")
    if node:
        result = subprocess.run([node, "--check", str(ROOT / "static/app.js")],
                                capture_output=True, text=True)
        if result.returncode:
            print(result.stderr, file=sys.stderr)
            return result.returncode
        print("JavaScript syntax: OK", flush=True)
    else:
        print("JavaScript syntax: SKIPPED (node not found)", flush=True)
    if args.scope == "syntax":
        return 0
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern=PATTERNS[args.scope])
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
