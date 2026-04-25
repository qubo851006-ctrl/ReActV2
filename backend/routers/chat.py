import json
from pathlib import Path
from fastapi import APIRouter
from pydantic import BaseModel
import httpx

from config import MODEL_CHAT, CHAT_HISTORY_PATH, ZHISHU_API_KEY, ZHISHU_BASE_URL
from llm_client import get_llm_client

router = APIRouter(prefix="/api/chat", tags=["chat"])

# 合法的意图名称集合，新增意图只需在此处和 INTENT_DESCRIPTIONS 中各加一行
_VALID_INTENTS = {
    "download_training_excel",
    "download_ledger_excel",
    "waiting_files",
    "waiting_ledger_files",
    "waiting_auth_file",
    "other",
}

_INTENT_DESCRIPTIONS = """- download_training_excel：用户想下载或导出培训统计表、培训台账、培训记录 Excel
- download_ledger_excel：用户想下载或导出案件台账、诉讼台账 Excel
- waiting_files：用户想统计培训签到、归档培训文件、新增培训记录（需上传文件，不是单纯下载）
- waiting_ledger_files：用户想处理案件台账、整理法律文书、新增案件记录（需上传文书，不是单纯下载）
- waiting_auth_file：用户想起草授权请示、根据呈批件生成授权文件
- other：以上都不符合，或用户只是聊天提问"""


# 通用对话可以主动触发的 stage（不含下载类，下载已由意图检测拦截）
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


def _classify_intent(client, message: str) -> str:
    """单次 LLM 调用识别意图，取代原来的 5 次独立检测调用。"""
    system_prompt = (
        f"你是意图分类器。根据用户消息，从以下意图中选择最匹配的一个，"
        f"只返回意图名称，不要有任何其他内容：\n\n{_INTENT_DESCRIPTIONS}"
    )
    resp = client.chat.completions.create(
        model=MODEL_CHAT,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
        max_tokens=20,
    )
    intent = resp.choices[0].message.content.strip().lower()
    return intent if intent in _VALID_INTENTS else "other"


def _general_chat(client, message: str, history: list) -> tuple[str, str]:
    """
    轻量 ReAct 通用对话：LLM 在单次调用中同时完成思考（Thought）和行动决策（Action）。

    - reply：返回给用户的自然语言回复
    - next_stage：若 LLM 判断用户有明确工作流需求则填入 stage 名，否则为 'idle'

    与原来纯文本回复的区别：LLM 现在知道系统有哪些功能，能主动引导用户，
    而不是总回复"请点击左侧卡片"这类无信息的提示。
    """
    system_prompt = f"""你是法务合规部的智能助手，负责回答问题并在适当时引导用户使用对应功能。

可触发的功能（仅当用户有明确需求时才填 next_stage）：
{_WORKFLOW_HINTS}

请严格用以下 JSON 格式回复，不要输出任何 JSON 以外的内容：
{{
  "reply": "对用户的回复，简洁友好，使用中文",
  "next_stage": "填入上方功能名称之一，或填 null 表示普通对话"
}}

注意：
- 只有当你确信用户有明确的操作需求时才填 next_stage，避免过度推销
- 如果用户描述模糊，先追问澄清，next_stage 填 null
- 不要提"点击按钮"等界面操作，只需说明系统可以帮用户做什么"""

    messages = [{"role": "system", "content": system_prompt}]
    for msg in history[-10:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": message})

    resp = client.chat.completions.create(model=MODEL_CHAT, messages=messages)
    raw = resp.choices[0].message.content.strip()

    # 解析 JSON；若模型输出不规范则降级为纯文本，next_stage 置 idle
    try:
        # 处理模型可能返回的 markdown 代码块包裹
        clean = raw
        if clean.startswith("```"):
            parts = clean.split("```")
            clean = parts[1].lstrip("json").strip() if len(parts) > 1 else clean
        data = json.loads(clean)
        reply = str(data.get("reply") or raw)
        stage = data.get("next_stage") or "idle"
        next_stage = stage if stage in _ACTIONABLE_STAGES else "idle"
    except Exception:
        reply = raw
        next_stage = "idle"

    return reply, next_stage


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


@router.get("/history")
def get_history():
    saved = load_history()
    if not saved:
        saved = [{
            "role": "assistant",
            "content": "你好！我是**培训统计助手**，可以帮您完成培训签到统计和文件归档，也可以回答您的各类问题。"
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


@router.post("")
def chat(req: ChatRequest):
    history = load_history()

    # 知识库模式
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
            history.append({"role": "user", "content": req.message})
            history.append({"role": "assistant", "content": reply})
            save_history(history)
            return {"reply": reply, "next_stage": "idle", "kb_conversation_id": new_conv_id}
        except Exception as e:
            reply = f"❌ 知识库查询失败：{e}"
            history.append({"role": "user", "content": req.message})
            history.append({"role": "assistant", "content": reply})
            save_history(history)
            return {"reply": reply, "next_stage": "idle", "kb_conversation_id": ""}

    client = get_llm_client()

    # 单次 LLM 调用识别意图（原来需要 5 次调用）
    intent = _classify_intent(client, req.message)

    # 意图 → 回复 + 下一阶段的映射表
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

    if intent in INTENT_RESPONSES:
        reply, next_stage = INTENT_RESPONSES[intent]
        history.append({"role": "user", "content": req.message})
        history.append({"role": "assistant", "content": reply})
        save_history(history)
        return {"reply": reply, "next_stage": next_stage, "kb_conversation_id": ""}

    # 通用对话（轻量 ReAct：LLM 在单次调用中回复并决定是否触发工作流）
    reply, next_stage = _general_chat(client, req.message, history)
    history.append({"role": "user", "content": req.message})
    history.append({"role": "assistant", "content": reply})
    save_history(history)
    return {"reply": reply, "next_stage": next_stage, "kb_conversation_id": ""}
