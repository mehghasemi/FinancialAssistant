from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..services.excel_import import ExcelImportError, import_sheet4

router = APIRouter(prefix="/api", tags=["imports"])


@router.post("/imports/sheet4")
async def import_sheet4_endpoint(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(422, "فقط فایل اکسل (xlsx) پذیرفته می‌شود.")
    content = await file.read()
    if not content:
        raise HTTPException(422, "فایل ارسالی خالی است.")
    try:
        return import_sheet4(content)
    except ExcelImportError as error:
        raise HTTPException(422, str(error)) from error
