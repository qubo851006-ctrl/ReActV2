import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from audit_log import write_log
from auth_utils import get_current_user, require_admin
from config import COMPLIANCE_LEDGER_EXCEL_PATH, COMPLIANCE_LEDGER_JSON_PATH
from db import get_db
from file_store import file_lock
from models import User
from routers.chat import load_history, save_history
from upload_validation import UploadValidationError, validate_pdf_upload
from utils.compliance_ledger import (
    append_record,
    create_compliance_workbook,
    extract_compliance_item,
    extract_pdf_text,
    load_records,
    load_responsible_persons,
    normalize_extracted_item,
    save_responsible_persons,
)

router = APIRouter(prefix="/api/compliance", tags=["compliance"])


class ResponsiblePersonsUpdate(BaseModel):
    persons: dict[str, str]


class ComplianceWriteRequest(BaseModel):
    title: str
    procedure: str
    undertaking_department: str = "法务合规部"
    background_materials: list[str] = Field(default_factory=list)
    review_rows: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    session_id: str = ""


@router.get("/responsible-persons")
def get_responsible_persons(_: User = Depends(get_current_user)):
    return {"persons": load_responsible_persons()}


@router.put("/responsible-persons")
def update_responsible_persons(
    body: ResponsiblePersonsUpdate,
    _: User = Depends(require_admin),
):
    return {"persons": save_responsible_persons(body.persons)}


@router.post("/extract")
async def extract_compliance(
    pdf_file: UploadFile = File(...),
    vision_model: str = Form(""),
    request: Request = None,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pdf_bytes = await pdf_file.read()
    try:
        safe_name = validate_pdf_upload(pdf_file.filename or "", pdf_file.content_type, pdf_bytes)
    except UploadValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    def _process() -> dict[str, Any]:
        text = extract_pdf_text(pdf_bytes, safe_name, vision_model)
        if not text.strip():
            raise ValueError("未能从 PDF 中提取可识别文本")
        return extract_compliance_item(text, load_responsible_persons())

    try:
        item = await asyncio.to_thread(_process)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"合规审查信息提取失败：{e}")

    write_log(db, user, "compliance_extract", f"提取合规审查台账：{item.get('title', safe_name)}", request)
    return {"item": item}


@router.post("/write")
def write_compliance(
    body: ComplianceWriteRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    body_data = body.model_dump() if hasattr(body, "model_dump") else body.dict()
    record = normalize_extracted_item(body_data)
    txn_lock = Path(COMPLIANCE_LEDGER_JSON_PATH).with_suffix(".txn")
    with file_lock(txn_lock):
        records = append_record(record, COMPLIANCE_LEDGER_JSON_PATH)
        create_compliance_workbook(records, COMPLIANCE_LEDGER_EXCEL_PATH)
        sequence = records[-1].get("sequence", len(records))

    reply = f"✅ 合规审查工作台账已更新！已新增第 {sequence} 项：{record.get('title', '')}"
    if body.session_id:
        history = load_history(user.id, body.session_id)
        history.append({"role": "assistant", "content": reply})
        save_history(history, user.id, body.session_id)
    write_log(db, user, "compliance_write", f"写入合规审查台账：{record.get('title', '')}", request)
    return {"ok": True, "count": len(records), "sequence": sequence, "reply": reply}


@router.get("/download")
def download_compliance(_: User = Depends(get_current_user)):
    path = Path(COMPLIANCE_LEDGER_EXCEL_PATH)
    if not path.exists():
        records = load_records(COMPLIANCE_LEDGER_JSON_PATH)
        if not records:
            raise HTTPException(status_code=404, detail="合规审查台账不存在，请先生成台账。")
        create_compliance_workbook(records, path)
    return FileResponse(
        path=str(path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="合规审查工作台账.xlsx",
    )
