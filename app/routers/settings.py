from __future__ import annotations

import json

from fastapi import APIRouter, Query

from ..calendar import format_jalali_datetime
from ..config import APP_VERSION, MAX_PAGE_SIZE
from ..database import connection, create_database_backup, get_setting, set_setting, clear_financial_data, write_audit_log
from ..schemas import SettingsInput, ClearDataInput
from ..utils import serialize

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/health")
def health():
    return {"status": "ok", "application": "FinancialAssistant", "database": "sqlite", "version": APP_VERSION}


@router.get("/data-status")
def data_status():
    with connection() as db:
        row = db.execute("SELECT created_at FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
    return {"version": APP_VERSION, "last_changed_at": row[0] if row else None,
            "last_changed_label": format_jalali_datetime(row[0]) if row else None}


@router.get("/settings")
def settings():
    return {
        "backup_enabled": get_setting("backup_enabled", "true") == "true",
        "backup_directory": get_setting("backup_directory", ""),
    }


@router.put("/settings")
def update_settings(payload: SettingsInput):
    with connection(write=True) as db:
        before = dict(db.execute("SELECT setting_key, setting_value FROM app_settings WHERE setting_key IN ('backup_enabled', 'backup_directory')").fetchall())
        after = {"backup_enabled": "true" if payload.backup_enabled else "false", "backup_directory": payload.backup_directory}
        for key, value in after.items():
            db.execute("INSERT INTO app_settings(setting_key, setting_value) VALUES (?, ?) ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value, updated_at=CURRENT_TIMESTAMP", (key, value))
        write_audit_log(db, "update", "settings", 0, json.dumps({"before": before, "after": after}, ensure_ascii=False))
    return settings()


@router.post("/backups", status_code=201)
def create_backup():
    backup_path = create_database_backup(get_setting("backup_directory", ""))
    return {"path": str(backup_path)}


@router.post("/settings/clear-data")
def clear_data(payload: ClearDataInput):
    backup_path = clear_financial_data()
    return {"status": "cleared", "backup_path": str(backup_path)}


@router.get("/releases")
def releases(limit: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE)):
    with connection() as db:
        result = [serialize(row) for row in db.execute(
            """SELECT version, released_at, title, description, affected_areas
               FROM release_history ORDER BY released_at DESC LIMIT ?""", (limit,)
        ).fetchall()]
    for item in result:
        item["released_at"] = format_jalali_datetime(item["released_at"])
    return result


@router.get("/audit-logs")
def audit_logs(resource_type: str | None = None, resource_id: int | None = None,
               before_id: int | None = Query(default=None, ge=1),
               limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE)):
    clauses, params = [], []
    for column, value in (("resource_type", resource_type), ("resource_id", resource_id)):
        if value is not None:
            clauses.append(f"{column} = ?")
            params.append(value)
    if before_id is not None:
        clauses.append("id < ?")
        params.append(before_id)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with connection() as db:
        rows = [dict(row) for row in db.execute(
            "SELECT * FROM audit_logs" + where + " ORDER BY id DESC LIMIT ?", (*params, limit + 1))]
    more = len(rows) > limit
    rows = rows[:limit]
    for row in rows:
        row["created_at"] = format_jalali_datetime(row["created_at"])
        try:
            row["details"] = json.loads(row["details"])
        except (ValueError, TypeError):
            pass
    return {"items": rows, "next_cursor": rows[-1]["id"] if more else None}
