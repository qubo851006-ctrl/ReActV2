import os
import tempfile
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from auth_utils import get_current_user
from audit_log import write_log
from db import get_db
from models import User
from routers.chat import load_history, save_history
from upload_validation import UploadValidationError, validate_image_upload, validate_pdf_upload

router = APIRouter(prefix="/api/training", tags=["training"])


# ── 提取（不写入台账）────────────────────────────────────────

@router.post("/extract")
async def extract_training(
    notice_pdf: UploadFile = File(...),
    signin_img: UploadFile = File(...),
    department: str = Form(""),
):
    """
    提取培训信息并归档文件，但不写入 Excel。
    返回提取结果供前端展示确认。
    """
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from utils.pdf_reader import extract_pdf_text
    from utils.image_analyzer import count_attendees
    from utils.classifier import classify_training
    from utils.archiver import archive_files
    from utils.excel_writer import EXCEL_PATH

    notice_bytes = await notice_pdf.read()
    signin_bytes = await signin_img.read()
    try:
        notice_name = validate_pdf_upload(notice_pdf.filename or "", notice_pdf.content_type, notice_bytes)
        signin_name = validate_image_upload(signin_img.filename or "", signin_img.content_type, signin_bytes)
    except UploadValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    with tempfile.TemporaryDirectory() as tmpdir:
        notice_path = os.path.join(tmpdir, notice_name)
        signin_path = os.path.join(tmpdir, signin_name)
        with open(notice_path, "wb") as f:
            f.write(notice_bytes)
        with open(signin_path, "wb") as f:
            f.write(signin_bytes)

        notice_text = extract_pdf_text(notice_path)
        sign_in_info = count_attendees(signin_path)
        category = classify_training(notice_text, sign_in_info["topic"])
        archive_path = archive_files(
            notice_path=notice_path,
            sign_in_path=signin_path,
            category=category,
            date=sign_in_info["date"],
            topic=sign_in_info["topic"],
        )

    return {
        "topic": sign_in_info["topic"] or "",
        "location": sign_in_info["location"] or "",
        "date": sign_in_info["date"] or "",
        "department": department or "",
        "count": sign_in_info["count"],
        "category": category,
        "archive_path": archive_path,
        "excel_path": EXCEL_PATH,
        "confidence": sign_in_info.get("confidence", "high"),
        "reflection_note": sign_in_info.get("reflection_note", ""),
    }


# ── 确认写入台账 ──────────────────────────────────────────────

class TrainingWriteRequest(BaseModel):
    topic: str
    location: str
    date: str
    department: str
    count: int
    category: str
    archive_path: str
    session_id: str = ""


@router.post("/write")
def write_training(
    req: TrainingWriteRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    用户确认后写入 Excel 台账并更新对话历史。
    """
    from utils.excel_writer import append_record, EXCEL_PATH

    append_record(
        date=req.date,
        topic=req.topic,
        location=req.location,
        department=req.department,
        count=req.count,
        category=req.category,
        archive_path=req.archive_path,
    )

    confidence_badge = "🟢 高置信度"  # 用户已确认，视为高置信
    reply = (
        f"✅ 培训记录已写入台账！\n\n"
        f"| 字段 | 内容 |\n|------|------|\n"
        f"| 培训主题 | {req.topic} |\n"
        f"| 培训地点 | {req.location} |\n"
        f"| 培训日期 | {req.date} |\n"
        f"| 主办部门 | {req.department or '未填写'} |\n"
        f"| 参与人数 | **{req.count} 人** |\n"
        f"| 培训类别 | {req.category} |\n"
        f"| 归档路径 | `{req.archive_path}` |"
    )
    write_log(db, user, "training_write", f"写入培训记录：{req.topic}", request)
    history = load_history(user.id, req.session_id)
    history.append({"role": "assistant", "content": reply})
    save_history(history, user.id, req.session_id)

    return {"ok": True, "excel_path": EXCEL_PATH}


# ── 下载统计表 ────────────────────────────────────────────────

@router.get("/download-excel")
def download_excel():
    from utils.excel_writer import EXCEL_PATH
    if not os.path.exists(EXCEL_PATH):
        from fastapi import HTTPException
        raise HTTPException(404, "统计表不存在")
    return FileResponse(
        EXCEL_PATH,
        filename="培训统计表.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
