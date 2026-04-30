import os
import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from auth_utils import get_current_user, require_admin
from audit_log import write_log
from db import get_db
from models import User
from file_store import atomic_write_bytes, file_lock

from config import LEDGER_JSON_PATH, LEDGER_EXCEL_PATH, LEDGER_OUTPUT_DIR
from ledger_helpers import (
    extract_file_text, ocr_pdf_with_vision, detect_doc_type_by_content,
    extract_case_fields, load_cases_json, save_cases_json,
    find_matching_case_idx, merge_case_data, archive_legal_docs,
    validate_legal_upload,
)
from routers.chat import load_history, save_history

router = APIRouter(prefix="/api/ledger", tags=["ledger"])


# ── 提取（SSE 流式，不写入）──────────────────────────────────

@router.post("/extract")
async def extract_ledger(files: list[UploadFile] = File(...), vision_model: str = Form("")):
    """
    流式提取案件信息、比对台账、归档文书，但不写入 cases.json / Excel。
    SSE 最终事件携带 preview 数据供前端展示确认。
    """
    files_data = []
    for f in files:
        b = await f.read()
        try:
            safe_name = validate_legal_upload(f.filename or "", f.content_type, b)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        files_data.append({"name": safe_name, "bytes": b, "content_type": f.content_type})

    async def event_stream() -> AsyncGenerator[str, None]:
        def send(msg: str) -> str:
            return f"data: {json.dumps({'log': msg}, ensure_ascii=False)}\n\n"

        # Step 1: 提取文字
        docs = []
        for fd in files_data:
            yield send(f"**Step 1** 📄 提取文字：`{fd['name']}`")
            text = extract_file_text(fd["bytes"], fd["name"])
            if not text:
                yield send("→ 扫描件，启动视觉 OCR…")
                try:
                    text = ocr_pdf_with_vision(fd["bytes"], model=vision_model)
                except Exception as e:
                    yield send(f"⚠️ OCR 失败：{e}")
            yield send(f"→ 提取到 **{len(text)}** 字符")
            doc_type = detect_doc_type_by_content(text) if text else "其他"
            yield send(f"→ 文书类型：**{doc_type}**")
            docs.append({"filename": fd["name"], "text": text, "doc_type": doc_type})

        # Step 2: AI 提取字段
        yield send("**Step 2** 🤖 AI 抽取案件字段…")
        new_case = extract_case_fields(docs, status_fn=lambda m: None)
        yield send(f"→ 案件名称：**{new_case.get('案件名称') or '（未提取到）'}**")
        yield send(f"→ 案由：**{new_case.get('案由') or '（未提取到）'}**")
        yield send(f"→ 标的金额：**{new_case.get('标的金额') or '（未提取到）'}**")

        # Step 3: 比对台账
        yield send("**Step 3** 🔍 比对现有台账…")
        existing_cases = load_cases_json()
        match_idx = find_matching_case_idx(new_case, existing_cases, docs=docs)
        yield send(f"→ {'匹配到第 ' + str(match_idx + 1) + ' 条记录' if match_idx is not None else '未匹配，将新增'}")

        # Step 4: 准备预览数据（合并但不保存）
        if match_idx is not None:
            preview_case = merge_case_data(existing_cases[match_idx], new_case)
            case_name = preview_case.get("案件名称", "")
            stage_summary = "、".join(s["审级"] for s in preview_case.get("stages", []))
            action_text = f"已有案件「{case_name}」，将更新（审级：{stage_summary or '无'}）"
            is_new = False
        else:
            if not new_case.get("案件名称"):
                new_case["案件名称"] = files_data[0]["name"]
            preview_case = new_case
            case_name = preview_case.get("案件名称", "")
            action_text = f"新案件「{case_name}」，将新增至台账"
            is_new = True

        # Step 5: 归档文书（归档不可逆，提前执行）
        yield send("📁 归档文书文件…")
        archive_dir = archive_legal_docs(files_data, docs, case_name)
        yield send(f"→ 已归档至：`{archive_dir}`")

        yield send("✅ 提取完成，等待确认…")

        preview_payload = {
            "preview": True,
            "case_data": preview_case,
            "match_idx": match_idx,
            "is_new": is_new,
            "action_text": action_text,
            "archive_dir": archive_dir,
            "existing_count": len(existing_cases),
        }
        yield f"data: {json.dumps(preview_payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── 确认写入台账 ──────────────────────────────────────────────

class LedgerWriteRequest(BaseModel):
    case_data: dict
    match_idx: int | None
    archive_dir: str
    session_id: str = ""


@router.post("/write")
def write_ledger_confirm(
    req: LedgerWriteRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    用户确认后将案件数据写入 cases.json 和 Excel。
    """
    output_dir = Path(LEDGER_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    txn_lock = Path(LEDGER_JSON_PATH).with_suffix(".txn")
    with file_lock(txn_lock):
        existing_cases = load_cases_json()
        updated_cases = list(existing_cases)

        if req.match_idx is not None and 0 <= req.match_idx < len(updated_cases):
            updated_cases[req.match_idx] = req.case_data
            action_text = f"已更新案件「{req.case_data.get('案件名称', '')}」"
            is_new = False
        else:
            updated_cases.append(req.case_data)
            action_text = f"已新增案件「{req.case_data.get('案件名称', '')}」"
            is_new = True

        json_path = Path(LEDGER_JSON_PATH)
        excel_path = Path(LEDGER_EXCEL_PATH)
        old_json = json_path.read_bytes() if json_path.exists() else None
        old_excel = excel_path.read_bytes() if excel_path.exists() else None

        tmp_excel = None
        try:
            from utils.write_excel import write_ledger as write_legal_ledger
            with tempfile.NamedTemporaryFile(suffix=".xlsx", dir=str(output_dir), delete=False) as tmp:
                tmp_excel = tmp.name
            write_legal_ledger(updated_cases, tmp_excel)
            save_cases_json(updated_cases)
            Path(tmp_excel).replace(excel_path)
        except Exception as e:
            if tmp_excel and os.path.exists(tmp_excel):
                try:
                    os.unlink(tmp_excel)
                except OSError:
                    pass
            if old_json is not None:
                atomic_write_bytes(json_path, old_json)
            elif json_path.exists():
                json_path.unlink()
            if old_excel is not None:
                atomic_write_bytes(excel_path, old_excel)
            elif excel_path.exists():
                excel_path.unlink()
            write_log(db, user, "ledger_write_failed", f"Ledger transaction failed: {e}", request)
            raise HTTPException(status_code=500, detail=f"台账写入失败：{e}")

    reply = (
        f"✅ {action_text}\n\n"
        f"📊 台账共 **{len(updated_cases)}** 个案件，Excel 已更新。\n\n"
        f"📁 文书已归档至：`{req.archive_dir}`"
    )
    history = load_history(user.id, req.session_id)
    history.append({"role": "assistant", "content": reply})
    save_history(history, user.id, req.session_id)

    write_log(db, user, "ledger_write", f"写入案件台账：{req.case_data.get('案件名称', '')}", request)
    return {"ok": True, "case_count": len(updated_cases), "reply": reply}



# ── 清空台账（仅管理员）────────────────────────────────────────

@router.post("/clear")
def clear_ledger(
    request: Request,
    session_id: str = "",
    db: DBSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    txn_lock = Path(LEDGER_JSON_PATH).with_suffix(".txn")
    with file_lock(txn_lock):
        p = Path(LEDGER_JSON_PATH)
        if p.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = p.with_name(f"cases_backup_{ts}.json")
            p.replace(backup)
            msg = f"✅ 台账已清空，备份已保存至：`{backup}`"
        else:
            msg = "台账本来就是空的，无需清空。"
    write_log(db, user, "ledger_clear", "清空案件台账", request)
    history = load_history(user.id, session_id)
    history.append({"role": "assistant", "content": msg})
    save_history(history, user.id, session_id)
    return {"message": msg}


# ── 下载 Excel ────────────────────────────────────────────────

@router.get("/download-excel")
def download_ledger_excel():
    if not os.path.exists(LEDGER_EXCEL_PATH):
        from fastapi import HTTPException
        raise HTTPException(404, "台账文件不存在")
    return FileResponse(
        LEDGER_EXCEL_PATH,
        filename="诉讼案件台账.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
