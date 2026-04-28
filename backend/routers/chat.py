import json
import time as _time
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import httpx

from config import MODEL_CHAT, DATA_ROOT, ZHISHU_API_KEY, ZHISHU_BASE_URL
from llm_client import get_llm_client
from auth_utils import get_current_user
from models import User

_HISTORY_DIR = Path(DATA_ROOT) / "history"
_HISTORY_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/api/chat", tags=["chat"])

# ── 意图集合（新增意图在此加一行）────────────────────────────────
_VALID_INTENTS = {
    "download_training_excel",
    "download_ledger_excel",
    "waiting_files",
    "waiting_ledger_files",
    "waiting_auth_file",
    "query_company",
    "other",
}

# 工作流意图描述（供 _classify 使用，不含 query_company / other）
_INTENT_DESCRIPTIONS_WORKFLOW = """\
- download_training_excel：用户想下载或导出培训统计表、培训台账、培训记录 Excel
- download_ledger_excel：用户想下载或导出案件台账、诉讼台账 Excel
- waiting_files：用户想统计培训签到、归档培训文件、新增培训记录（需上传文件，不是单纯下载）
- waiting_ledger_files：用户想处理案件台账、整理法律文书、新增案件记录（需上传文书，不是单纯下载）
- waiting_auth_file：用户想起草授权请示、根据呈批件生成授权文件"""

# 通用对话可以主动触发的 stage
_ACTIONABLE_STAGES = {
    "waiting_files",
    "waiting_ledger_files",
    "waiting_auth_file",
    "waiting_ledger_merge_files",
    "waiting_audit_file",
}

_WORKFLOW_HINTS = """\
- waiting_files：用户有培训通知/签到表需要统计归档
- waiting_ledger_files：用户有法律文书（起诉状/判决书/裁定书/强制执行申请）需要录入台账
- waiting_auth_file：用户需要根据呈批件起草授权请示或授权书
- waiting_ledger_merge_files：用户需要合并合同/采购/财务多个系统导出的台账 Excel
- waiting_audit_file：用户需要对审计发现问题进行 AI 分类分析"""


# ── 辅助函数 ─────────────────────────────────────────────────────

def _sse(data: dict) -> str:
    """格式化 SSE 事件行。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _append_and_save(history: list, user_msg: str, assistant_msg: str, user_id: int, session_id: str):
    history.append({"role": "user", "content": user_msg})
    history.append({"role": "assistant", "content": assistant_msg})
    save_history(history, user_id, session_id)


# ── LLM 调用函数 ─────────────────────────────────────────────────

def _classify(client, message: str) -> dict:
    """
    【优化2+3】单次 LLM 调用，同时完成意图识别、公司名提取、next_stage 判断。

    返回格式：
      {"intent": "waiting_files"}                           # 工作流意图
      {"intent": "query_company", "company": "比亚迪"}      # 企业查询（含公司名）
      {"intent": "other", "next_stage": null}              # 普通对话
    """
    system_prompt = f"""你是法务合规部的智能助手意图分析器。只返回 JSON，不要其他内容。

【工作流意图】格式：{{"intent": "意图名"}}
{_INTENT_DESCRIPTIONS_WORKFLOW}

【企业查询】格式：{{"intent": "query_company", "company": "企业名称"}}
条件：用户提及具体公司名称并想查询工商/司法等信息

【普通对话】格式：{{"intent": "other", "next_stage": null}}
next_stage 可选值（仅当用户有明确操作需求时填入，否则填 null）：
waiting_files / waiting_ledger_files / waiting_auth_file / waiting_ledger_merge_files / waiting_audit_file"""

    resp = client.chat.completions.create(
        model=MODEL_CHAT,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
        max_tokens=80,
    )
    raw = resp.choices[0].message.content.strip()
    try:
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw
        data = json.loads(raw)
        intent = data.get("intent", "other")
        if intent not in _VALID_INTENTS:
            intent = "other"
        return {
            "intent": intent,
            "company": data.get("company"),
            "next_stage": data.get("next_stage"),
        }
    except Exception:
        return {"intent": "other", "company": None, "next_stage": None}


def _stream_reply(client, message: str, history: list):
    """
    【优化1】生成器：逐 token yield 文本块，供 SSE 流式推送。
    替代原来的 _general_chat（不再要求 JSON 格式输出）。
    """
    system_prompt = f"""你是法务合规部的智能助手，请用中文简洁友好地回答用户问题。

可以引导用户使用的功能：
{_WORKFLOW_HINTS}

直接输出回复内容，不需要 JSON 格式。"""

    messages = [{"role": "system", "content": system_prompt}]
    for msg in history[-10:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": message})

    stream = client.chat.completions.create(
        model=MODEL_CHAT,
        messages=messages,
        stream=True,
        max_tokens=500,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


# ── Session 存储（每用户独立目录，每 session 一个文件）─────────

def _user_dir(user_id: int) -> Path:
    d = _HISTORY_DIR / f"user_{user_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _sessions_path(user_id: int) -> Path:
    return _user_dir(user_id) / "sessions.json"

def _session_msg_path(user_id: int, session_id: str) -> Path:
    return _user_dir(user_id) / f"{session_id}.json"

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _auto_title(messages: list) -> str:
    for m in messages:
        if m.get("role") == "user":
            t = m["content"][:20]
            return (t + "…") if len(m["content"]) > 20 else t
    return "新对话"

def load_sessions(user_id: int) -> list:
    """加载会话元数据列表，首次自动迁移旧版单文件。"""
    sp = _sessions_path(user_id)
    old_file = _HISTORY_DIR / f"user_{user_id}.json"
    # 迁移旧格式：history/user_{id}.json → user_{id}/sess_migrated.json
    if old_file.exists() and not sp.exists():
        try:
            old_msgs = json.loads(old_file.read_text(encoding="utf-8"))
        except Exception:
            old_msgs = []
        if old_msgs:
            _session_msg_path(user_id, "sess_migrated").write_text(
                json.dumps(old_msgs, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            now = _now_iso()
            init_sessions = [{"id": "sess_migrated", "title": _auto_title(old_msgs),
                               "created_at": now, "updated_at": now}]
            sp.write_text(json.dumps(init_sessions, ensure_ascii=False, indent=2), encoding="utf-8")
        old_file.rename(old_file.with_suffix(".bak"))
    if not sp.exists():
        return []
    try:
        return json.loads(sp.read_text(encoding="utf-8"))
    except Exception:
        return []

def save_sessions(sessions: list, user_id: int):
    try:
        _sessions_path(user_id).write_text(
            json.dumps(sessions, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass

def load_history(user_id: int, session_id: str) -> list:
    p = _session_msg_path(user_id, session_id)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []

def save_history(messages: list, user_id: int, session_id: str):
    try:
        _session_msg_path(user_id, session_id).write_text(
            json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # 同步更新 sessions.json 的 updated_at 和自动标题
        sessions = load_sessions(user_id)
        now = _now_iso()
        for s in sessions:
            if s["id"] == session_id:
                s["updated_at"] = now
                if s["title"] == "新对话":
                    s["title"] = _auto_title(messages)
                break
        sessions.sort(key=lambda s: s["updated_at"], reverse=True)
        save_sessions(sessions, user_id)
    except Exception:
        pass

def _create_session(user_id: int) -> dict:
    session_id = f"sess_{int(_time.time() * 1000)}"
    now = _now_iso()
    meta = {"id": session_id, "title": "新对话", "created_at": now, "updated_at": now}
    sessions = load_sessions(user_id)
    sessions.insert(0, meta)
    save_sessions(sessions, user_id)
    return meta


# ── HTTP 端点 ────────────────────────────────────────────────────

@router.get("/sessions")
def list_sessions(user: User = Depends(get_current_user)):
    sessions = load_sessions(user.id)
    return {"sessions": sessions}

@router.post("/sessions")
def create_session_ep(user: User = Depends(get_current_user)):
    meta = _create_session(user.id)
    return {"session_id": meta["id"], "title": meta["title"]}

class RenameRequest(BaseModel):
    title: str

@router.patch("/sessions/{session_id}")
def rename_session(session_id: str, body: RenameRequest, user: User = Depends(get_current_user)):
    sessions = load_sessions(user.id)
    for s in sessions:
        if s["id"] == session_id:
            s["title"] = body.title.strip() or "新对话"
            break
    save_sessions(sessions, user.id)
    return {"ok": True}

@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, user: User = Depends(get_current_user)):
    sessions = load_sessions(user.id)
    sessions = [s for s in sessions if s["id"] != session_id]
    save_sessions(sessions, user.id)
    msg_file = _session_msg_path(user.id, session_id)
    if msg_file.exists():
        msg_file.unlink()
    return {"ok": True}

@router.get("/history")
def get_history(session_id: str, user: User = Depends(get_current_user)):
    saved = load_history(user.id, session_id)
    if not saved:
        saved = [{
            "role": "assistant",
            "content": "你好！我是**法务合规部智能助手**，可以帮您完成培训统计、案件台账、授权请示、企业信息查询等工作，也可以回答您的各类问题。"
        }]
    return {"messages": saved}

@router.delete("/history")
def clear_history(session_id: str, user: User = Depends(get_current_user)):
    save_history([], user.id, session_id)
    sessions = load_sessions(user.id)
    for s in sessions:
        if s["id"] == session_id:
            s["title"] = "新对话"
            break
    save_sessions(sessions, user.id)
    return {"ok": True}


class ChatRequest(BaseModel):
    message: str
    use_kb: bool = False
    kb_conversation_id: str = ""
    session_id: str = ""


# 固定意图 → 固定回复映射（直接返回，不需要额外 LLM 调用）
INTENT_RESPONSES = {
    "download_training_excel": (
        "📥 正在为您打开培训统计表下载…",
        "download_training_excel",
    ),
    "download_ledger_excel": (
        "📥 正在为您打开案件台账下载…",
        "download_ledger_excel",
    ),
    "waiting_files": (
        "好的！请上传以下两个文件：\n\n"
        "- 📄 **培训通知**（PDF 格式）\n"
        "- ✍️ **签到表**（图片格式：JPG / PNG）",
        "waiting_files",
    ),
    "waiting_ledger_files": (
        "好的！请上传案件的法律文书文件（支持 **PDF / DOCX / DOC**，可多选）。\n\n"
        "系统会自动识别文书类型，并判断是否为台账中的已有案件：\n"
        "- 已有案件：追加审级处理结果或更新执行信息\n"
        "- 新案件：在台账末尾新增一行",
        "waiting_ledger_files",
    ),
    "waiting_auth_file": (
        "好的！请上传**呈批件 PDF**，系统将自动提取关键信息并生成授权请示 Word 文档。\n\n"
        "- 支持文字版 PDF（直接提取）\n"
        "- 支持扫描版 PDF（自动 OCR 识别）",
        "waiting_auth_file",
    ),
}


@router.post("")
def chat(req: ChatRequest, user: User = Depends(get_current_user)):
    uid = user.id
    sid = req.session_id
    def generate():
        history = load_history(uid, sid)

        # ── 知识库模式（外部服务，无法流式）────────────────────────
        if req.use_kb:
            try:
                url = f"{ZHISHU_BASE_URL}/chat-messages"
                headers = {
                    "Authorization": f"Bearer {ZHISHU_API_KEY}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "query": req.message,
                    "inputs": {},
                    "response_mode": "blocking",
                    "user": "training-manager",
                    "conversation_id": req.kb_conversation_id,
                }
                resp = httpx.post(url, json=payload, headers=headers, verify=False, timeout=120)
                resp.raise_for_status()
                data = resp.json()
                reply = data.get("answer", "（知识库未返回内容）")
                new_conv_id = data.get("conversation_id", "")
            except Exception as e:
                reply = f"❌ 知识库查询失败：{e}"
                new_conv_id = ""
            _append_and_save(history, req.message, reply, uid, sid)
            yield _sse({"type": "done", "reply": reply, "next_stage": "idle", "kb_conversation_id": new_conv_id})
            return

        client = get_llm_client()

        # ── 单次分类调用（优化2+3）───────────────────────────────────
        cls = _classify(client, req.message)
        intent = cls["intent"]

        # ── 固定回复意图（无需额外 LLM）─────────────────────────────
        if intent in INTENT_RESPONSES:
            reply, next_stage = INTENT_RESPONSES[intent]
            _append_and_save(history, req.message, reply, uid, sid)
            yield _sse({"type": "done", "reply": reply, "next_stage": next_stage, "kb_conversation_id": ""})
            return

        # ── 企业查询（MCP，无法流式）────────────────────────────────
        if intent == "query_company":
            company = cls.get("company") or req.message
            try:
                from utils.mcp_client import query_company, format_company_markdown
                result = query_company(company)
                reply = format_company_markdown(result)
            except ValueError as e:
                reply = f"❌ 未找到匹配企业：{e}"
            except Exception as e:
                reply = f"❌ 企业信息查询失败：{e}"
            _append_and_save(history, req.message, reply, uid, sid)
            yield _sse({"type": "done", "reply": reply, "next_stage": "idle", "kb_conversation_id": ""})
            return

        # ── 通用对话（流式输出，优化1）──────────────────────────────
        next_stage = cls.get("next_stage") or "idle"
        if next_stage not in _ACTIONABLE_STAGES:
            next_stage = "idle"

        accumulated = ""
        for chunk in _stream_reply(client, req.message, history):
            accumulated += chunk
            yield _sse({"type": "chunk", "text": chunk})

        _append_and_save(history, req.message, accumulated, uid, sid)
        yield _sse({"type": "done", "reply": "", "next_stage": next_stage, "kb_conversation_id": ""})

    return StreamingResponse(generate(), media_type="text/event-stream")
