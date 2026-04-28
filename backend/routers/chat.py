import json
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import httpx

from config import MODEL_CHAT, CHAT_HISTORY_PATH, ZHISHU_API_KEY, ZHISHU_BASE_URL
from llm_client import get_llm_client

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


def _append_and_save(history: list, user_msg: str, assistant_msg: str):
    history.append({"role": "user", "content": user_msg})
    history.append({"role": "assistant", "content": assistant_msg})
    save_history(history)


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


# ── 历史记录 ─────────────────────────────────────────────────────

def load_history() -> list:
    p = Path(CHAT_HISTORY_PATH)
    if not p.exists():
        return []
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_history(messages: list):
    try:
        with open(CHAT_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ── HTTP 端点 ────────────────────────────────────────────────────

@router.get("/history")
def get_history():
    saved = load_history()
    if not saved:
        saved = [{
            "role": "assistant",
            "content": "你好！我是**法务合规部智能助手**，可以帮您完成培训统计、案件台账、授权请示、企业信息查询等工作，也可以回答您的各类问题。"
        }]
    return {"messages": saved}


@router.delete("/history")
def clear_history():
    save_history([])
    return {"ok": True}


class ChatRequest(BaseModel):
    message: str
    use_kb: bool = False
    kb_conversation_id: str = ""


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
def chat(req: ChatRequest):
    def generate():
        history = load_history()

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
            _append_and_save(history, req.message, reply)
            yield _sse({"type": "done", "reply": reply, "next_stage": "idle", "kb_conversation_id": new_conv_id})
            return

        client = get_llm_client()

        # ── 单次分类调用（优化2+3）───────────────────────────────────
        cls = _classify(client, req.message)
        intent = cls["intent"]

        # ── 固定回复意图（无需额外 LLM）─────────────────────────────
        if intent in INTENT_RESPONSES:
            reply, next_stage = INTENT_RESPONSES[intent]
            _append_and_save(history, req.message, reply)
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
            _append_and_save(history, req.message, reply)
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

        _append_and_save(history, req.message, accumulated)
        yield _sse({"type": "done", "reply": "", "next_stage": next_stage, "kb_conversation_id": ""})

    return StreamingResponse(generate(), media_type="text/event-stream")
