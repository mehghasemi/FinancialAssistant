"""Recover a backup into a new data directory; never overwrite an existing database."""
from pathlib import Path
import argparse
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.backups import restore_backup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        output = restore_backup(args.source, args.data_dir / "financial_assistant.db")
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"Restore failed: {error}", file=sys.stderr)
        return 1
    print(f"Restored: {output}")
    print("Stop the app, set FINANCIAL_ASSISTANT_DATA_DIR to this directory, then restart.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
