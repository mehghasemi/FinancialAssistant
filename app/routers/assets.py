from __future__ import annotations

import json
from datetime import datetime
from fastapi import APIRouter, HTTPException
from ..database import connection, write_audit_log
from ..calendar import format_jalali_date, format_jalali_datetime
from ..schemas import AssetInput

router = APIRouter(prefix="/api/assets", tags=["assets"])


@router.get("")
def list_assets():
    with connection() as db:
        items = [dict(row) for row in db.execute("SELECT * FROM assets ORDER BY registered_on DESC, id DESC")]
    for item in items:
        item["registered_on"] = format_jalali_date(item["registered_on"])
    return items


def save_asset(payload, identifier=None):
    with connection(write=True) as db:
        before = None
        if identifier is not None:
            before = db.execute("SELECT * FROM assets WHERE id=?", (identifier,)).fetchone()
            if not before:
                raise HTTPException(404, "دارایی پیدا نشد.")
        values = (payload.title, payload.kind, payload.registered_on.isoformat(), payload.initial_value, payload.current_value, payload.note)
        if before is None:
            identifier = db.execute("INSERT INTO assets(title,kind,registered_on,initial_value,current_value,note) VALUES (?,?,?,?,?,?)", values).lastrowid
        else:
            db.execute("UPDATE assets SET title=?,kind=?,registered_on=?,initial_value=?,current_value=?,note=? WHERE id=?", (*values, identifier))
        if before is None or before["current_value"] != payload.current_value:
            db.execute("INSERT INTO asset_values(asset_id,changed_at,old_value,new_value,note) VALUES (?,?,?,?,?)", (identifier, datetime.now().astimezone().isoformat(), before["current_value"] if before else None, payload.current_value, payload.change_note))
        write_audit_log(db, "update" if before else "create", "asset", identifier, json.dumps({"before": dict(before) if before else None, "after": payload.model_dump(mode="json")}, ensure_ascii=False))
    return {"id": identifier}


@router.post("", status_code=201)
def create_asset(payload: AssetInput):
    return save_asset(payload)


@router.patch("/{identifier}")
def update_asset(identifier: int, payload: AssetInput):
    return save_asset(payload, identifier)


@router.get("/{identifier}/history")
def asset_history(identifier: int):
    with connection() as db:
        if not db.execute("SELECT 1 FROM assets WHERE id=?", (identifier,)).fetchone():
            raise HTTPException(404, "دارایی پیدا نشد.")
        rows = [dict(row) for row in db.execute("SELECT * FROM asset_values WHERE asset_id=? ORDER BY id DESC", (identifier,))]
    for row in rows:
        row["changed_at"] = format_jalali_datetime(row["changed_at"])
    return rows
