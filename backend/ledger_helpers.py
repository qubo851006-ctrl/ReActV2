"""
案件台账相关辅助函数，从 training-manager/app.py 拆出。
"""
import gc
import re
import os
import json
import base64
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Callable

from llm_client import get_llm_client
from config import MODEL_CHAT, LEDGER_JSON_PATH, LEDGER_OUTPUT_DIR, LEGAL_ARCHIVE_ROOT
from file_store import atomic_write_bytes, atomic_write_text, file_lock
from model_routes import resolve_vision_model
from upload_validation import safe_upload_name


# ── 提取文书文字 ──────────────────────────────────────────────

def extract_file_text(file_bytes: bytes, filename: str) -> str:
    """从 PDF/DOCX/DOC 字节提取文字，PDF 优先 pdfplumber，失败则 OCR。"""
    ext = os.path.splitext(filename)[1].lower()
    text = ""
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name
    try:
        if ext == ".pdf":
            import pdfplumber
            with pdfplumber.open(tmp_path) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        text += t + "\n"
        elif ext in (".docx", ".doc"):
            from docx import Document
            doc = Document(tmp_path)
            text = "\n".join(p.text for p in doc.paragraphs)
    finally:
        os.unlink(tmp_path)
    return text.strip()


def ocr_pdf_with_vision(pdf_bytes: bytes, model: str | None = None) -> str:
    """用视觉模型逐页识别扫描版 PDF，返回全文。"""
    import fitz
    client = get_llm_client()
    selected_model = resolve_vision_model(model)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    all_texts = []
    for page in doc:
        pix = page.get_pixmap(dpi=150)
        img_b64 = base64.b64encode(pix.tobytes("jpeg", jpg_quality=85)).decode()
        response = client.chat.completions.create(
            model=selected_model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                    {"type": "text",
                     "text": "请将图片中的所有文字原文提取出来，保持段落结构，不要添加任何说明或总结。"},
                ],
            }],
        )
        t = response.choices[0].message.content.strip()
        if t:
            all_texts.append(t)
    doc.close()
    return "\n".join(all_texts)


def detect_doc_type_by_content(text: str) -> str:
    """用 AI 从内容判断文书类型。"""
    if not text:
        return "其他"
    client = get_llm_client()
    response = client.chat.completions.create(
        model=MODEL_CHAT,
        messages=[{"role": "user", "content": (
            "请判断以下法律文书是什么类型，只回复类型名称，从下列选项中选一个：\n"
            "起诉状、上诉状、再审申请书、一审判决书、二审判决书、判决书、裁定书、强制执行申请书、其他\n\n"
            f"文书内容（前500字）：\n{text[:500]}"
        )}],
        max_tokens=20,
    )
    raw = response.choices[0].message.content.strip()
    for t in ["强制执行申请书", "再审申请书", "一审判决书", "二审判决书", "裁定书", "上诉状", "起诉状", "判决书"]:
        if t in raw:
            return t
    return "其他"


# ── 字段提取 ──────────────────────────────────────────────────

PROMPT_SUSOSTATE = """你是法务专家，从以下起诉状/上诉状中提取关键信息，以JSON格式返回。

要求：
- 案号：法院受理案号，格式如"(2022)川01民初1234号"，找不到填 null
- 案件名称：格式"原告方 与 被告方 案由纠纷案"，简洁概括
- 案件发生时间：起诉/立案日期，格式 YYYY-MM-DD，找不到填 null
- 案由：如"房屋租赁合同纠纷"、"劳动争议"等
- 诉讼主体：列出所有原告和被告，格式"原告：XX\n被告一：XX\n被告二：XX"
- 主诉被诉：填"诉讼-主诉"或"诉讼-被诉"
- 标的金额：诉讼请求的金额总计，单位万元，保留两位小数，找不到填 null
- 基本情况：诉讼请求的完整内容，保持原文，不要省略

只返回JSON，不要其他文字：
{"案号":null,"案件名称":"","案件发生时间":"","案由":"","诉讼主体":"","主诉被诉":"","标的金额":null,"基本情况":""}

文书内容：
{text}"""

PROMPT_JUDGMENT = """你是法务专家，从以下判决书/裁定书中提取关键信息，以JSON格式返回。

要求：
- 本案案号：本判决书的案号，如"(2023)川01民终24491号"，找不到填 null
- 关联案号：文中提到的上一审级案号（如"原审"/"一审"的案号），找不到填 null
- 审级：根据本案案号中的字样判断，严格按以下规则填写：
  * 案号含"民初"→填"一审"
  * 案号含"民终"→填"二审"
  * 案号含"民申"或文书标题含"再审"→填"再审"
  * 实在无法判断→填"一审"
- 生效判决日期：判决书落款日期，格式 YYYY-MM-DD，找不到填 null
- 处理结果：法院最终判决结论，包括驳回/支持、金额、各方义务，尽量简明（200字内）
- 服务律所：代理我方的律师事务所及律师姓名，找不到填 null

只返回JSON，不要其他文字：
{"本案案号":null,"关联案号":null,"审级":"","生效判决日期":"","处理结果":"","服务律所":null}

文书内容：
{text}"""

PROMPT_EXECUTION = """你是法务专家，从以下强制执行申请书中提取关键信息，以JSON格式返回。

只返回JSON，不要其他文字：
{"强制执行时间":null}

文书内容：
{text}"""


def _parse_json(raw: str) -> dict:
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def extract_case_fields(docs: list, status_fn: Callable | None = None) -> dict:
    client = get_llm_client()
    case = {
        "案件名称": "", "案件发生时间": None, "案由": "", "诉讼主体": "",
        "主诉被诉": "", "标的金额": None, "基本情况": "", "生效判决日期": None,
        "强制执行时间": None, "服务律所": None, "stages": [], "案号列表": [],
    }
    stage_order = {"一审": 1, "二审": 2, "再审": 3}
    stages_dict = {}

    for doc in docs:
        if not doc.get("text"):
            continue
        dtype = doc["doc_type"]
        fname = doc["filename"]
        if status_fn:
            status_fn(f"🤖 AI 抽取字段 [{dtype}]：{fname}")
        if dtype == "其他":
            continue
        try:
            if dtype in ("起诉状", "上诉状"):
                prompt = PROMPT_SUSOSTATE.replace("{text}", doc["text"][:8000])
                resp = client.chat.completions.create(
                    model=MODEL_CHAT,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=2000, temperature=0.1,
                )
                fields = _parse_json(resp.choices[0].message.content)
                if fields.get("案号"):
                    case["案号列表"].append(fields["案号"])
                for k in ["案件名称", "案件发生时间", "案由", "诉讼主体", "主诉被诉", "基本情况"]:
                    if not case[k] and fields.get(k):
                        case[k] = fields[k]
                if case["标的金额"] is None and fields.get("标的金额") is not None:
                    case["标的金额"] = fields["标的金额"]

            elif dtype in ("一审判决书", "二审判决书", "判决书", "裁定书", "再审申请书"):
                t = doc["text"]
                text_for_prompt = (t[:5000] + "\n…（中间省略）…\n" + t[-3000:]) if len(t) > 8000 else t
                prompt = PROMPT_JUDGMENT.replace("{text}", text_for_prompt)
                resp = client.chat.completions.create(
                    model=MODEL_CHAT,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=2000, temperature=0.1,
                )
                fields = _parse_json(resp.choices[0].message.content)
                本案案号 = fields.get("本案案号") or ""
                关联案号 = fields.get("关联案号") or ""
                for n in [本案案号, 关联案号]:
                    if n:
                        case["案号列表"].append(n)
                审级 = fields.get("审级", "").strip()
                if not 审级 and 本案案号:
                    if "民终" in 本案案号:
                        审级 = "二审"
                    elif "民初" in 本案案号:
                        审级 = "一审"
                    elif "民申" in 本案案号:
                        审级 = "再审"
                处理结果 = (fields.get("处理结果") or "").strip()
                if 审级:
                    stages_dict[审级] = 处理结果 or "（处理结果待补充）"
                if not case["服务律所"] and fields.get("服务律所"):
                    case["服务律所"] = fields["服务律所"]
                if fields.get("生效判决日期"):
                    case["生效判决日期"] = fields["生效判决日期"]

            elif dtype == "强制执行申请书":
                prompt = PROMPT_EXECUTION.replace("{text}", doc["text"][:4000])
                resp = client.chat.completions.create(
                    model=MODEL_CHAT,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=200, temperature=0.1,
                )
                fields = _parse_json(resp.choices[0].message.content)
                if not case["强制执行时间"] and fields.get("强制执行时间"):
                    case["强制执行时间"] = fields["强制执行时间"]

        except Exception as e:
            if status_fn:
                status_fn(f"⚠️ [{dtype}] {fname} 字段提取失败：{e}")

    case["stages"] = [
        {"审级": k, "处理结果": v}
        for k, v in sorted(stages_dict.items(), key=lambda x: stage_order.get(x[0], 9))
    ]
    return case


# ── 台账比对与合并 ─────────────────────────────────────────────

def load_cases_json() -> list:
    p = Path(LEDGER_JSON_PATH)
    if not p.exists():
        return []
    with file_lock(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)


def save_cases_json(cases: list):
    Path(LEDGER_JSON_PATH).parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(cases, ensure_ascii=False, indent=2)
    with file_lock(LEDGER_JSON_PATH):
        atomic_write_text(LEDGER_JSON_PATH, payload, encoding="utf-8")


def find_matching_case_idx(new_case: dict, existing_cases: list, docs: list = None):
    if not existing_cases:
        return None
    new_nums = set(filter(None, new_case.get("案号列表", [])))
    if new_nums:
        for i, c in enumerate(existing_cases):
            if new_nums & set(filter(None, c.get("案号列表", []))):
                return i

    new_lines = []
    for k in ["案件名称", "诉讼主体", "案由"]:
        if new_case.get(k):
            new_lines.append(f"{k}：{new_case[k]}")
    if docs:
        for doc in docs:
            if doc.get("text"):
                new_lines.append(f"文书原文片段（{doc.get('doc_type','未知')}）：{doc['text'][:400]}")

    summaries = "\n".join(
        f"{i}: {c.get('案件名称','未知')} | 主体：{c.get('诉讼主体','')[:80]} | 案由：{c.get('案由','')}"
        for i, c in enumerate(existing_cases)
    )
    prompt = (
        f'你是法务专家。判断"新上传文书"是否与"现有台账"中某个案件属于同一案件。\n\n'
        f'新上传文书信息：\n' + "\n".join(new_lines) +
        f'\n\n现有台账（编号: 案件名称 | 主体 | 案由）：\n{summaries}\n\n'
        f'注意：重点比对当事人姓名/公司名称和案由是否一致。\n'
        f'如果找到匹配，只回复编号数字（如：0）。如果没有匹配，回复 -1。不要有其他内容。'
    )
    client = get_llm_client()
    response = client.chat.completions.create(
        model=MODEL_CHAT,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=10,
    )
    try:
        idx = int(response.choices[0].message.content.strip())
        if 0 <= idx < len(existing_cases):
            return idx
    except ValueError:
        pass
    return None


def merge_case_data(existing: dict, new_data: dict) -> dict:
    result = {**existing}
    for field in ["案件名称", "案件发生时间", "案由", "诉讼主体", "主诉被诉", "基本情况"]:
        if not result.get(field) and new_data.get(field):
            result[field] = new_data[field]
    if result.get("标的金额") is None and new_data.get("标的金额") is not None:
        result["标的金额"] = new_data["标的金额"]
    result["案号列表"] = list(set(result.get("案号列表", []) + new_data.get("案号列表", [])))
    result["案号列表"] = [n for n in result["案号列表"] if n]
    for field in ["生效判决日期", "强制执行时间", "服务律所"]:
        if new_data.get(field):
            result[field] = new_data[field]
    stage_order = {"一审": 1, "二审": 2, "再审": 3}
    existing_stage_keys = {s["审级"] for s in result.get("stages", [])}
    for stage in new_data.get("stages", []):
        if stage["审级"] not in existing_stage_keys:
            result.setdefault("stages", []).append(stage)
    result["stages"] = sorted(result.get("stages", []), key=lambda x: stage_order.get(x["审级"], 9))
    return result


_LEGAL_ALLOWED_EXTS = {".pdf", ".docx", ".doc"}
_WINDOWS_RESERVED = re.compile(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$', re.IGNORECASE)
_LEGAL_UPLOAD_MAX_BYTES = int(os.getenv("LEGAL_UPLOAD_MAX_BYTES", str(50 * 1024 * 1024)))
_LEGAL_ALLOWED_CONTENT_TYPES = {
    ".pdf": {"application/pdf", "application/octet-stream", ""},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/octet-stream",
        "",
    },
    ".doc": {"application/msword", "application/octet-stream", ""},
}


def _safe_basename(filename: str) -> str:
    name = Path(str(filename or "").replace("\\", "/")).name.strip()
    if not name or name in {".", ".."}:
        raise ValueError("Invalid upload filename")
    return name


def _sanitize_upload_name(filename: str) -> str:
    return safe_upload_name(filename, _LEGAL_ALLOWED_EXTS)


def validate_legal_upload(filename: str, content_type: str | None, data: bytes) -> str:
    from upload_validation import validate_legal_upload as _validate_legal_upload

    return _validate_legal_upload(filename, content_type, data)

def archive_legal_docs(files_data: list, docs: list, case_name: str) -> str:
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", case_name).strip() or "未知案件"
    safe_name = safe_name[:100]
    archive_root = Path(LEGAL_ARCHIVE_ROOT).resolve()
    target_dir = (archive_root / safe_name).resolve()
    if not target_dir.is_relative_to(archive_root):
        raise ValueError(f"archive_legal_docs: case_name 越出归档根目录: {case_name!r}")
    target_dir.mkdir(parents=True, exist_ok=True)
    base = target_dir  # 已经是 resolved 路径

    for fd, doc in zip(files_data, docs):
        name = fd.get("name", "")
        data = fd.get("bytes")
        if not name or not isinstance(data, (bytes, bytearray)):
            continue

        doc_type = doc.get("doc_type", "其他")
        safe_doc_type = re.sub(r'[\\/:*?"<>|]', "_", doc_type).strip() or "其他"
        if _WINDOWS_RESERVED.match(safe_doc_type):
            safe_doc_type = f"_{safe_doc_type}"

        # 防御 1：提取纯文件名，去掉任何路径前缀
        pure_name = _sanitize_upload_name(name)

        # 防御 2：扩展名白名单（点文件特殊处理）
        if pure_name.startswith(".") and "." not in pure_name[1:]:
            ext = ".bin"          # 点文件无真实扩展名，直接归为 bin
            stem_only = pure_name  # 保留整个点文件名作为 stem（如 ".pdf"）
        else:
            ext = Path(pure_name).suffix.lower()
            stem_only = Path(pure_name).stem
            if ext not in _LEGAL_ALLOWED_EXTS:
                ext = ".bin"

        # 防御 3：清理文件名中的非法字符 + 长度限制
        safe_stem = re.sub(r'[\\/:*?"<>|]', "_", stem_only).strip() or "文件"
        safe_stem = safe_stem[:200]
        safe_filename = safe_stem + ext

        dest_name = f"{safe_doc_type}_{safe_filename}"
        dest_path = (target_dir / dest_name).resolve()

        # 越界兜底：确认路径仍在归档根目录内
        if not dest_path.is_relative_to(base):
            logging.warning("archive_legal_docs: 路径越界已跳过 %s", dest_path)
            continue

        if dest_path.exists():
            i = 2
            while i <= 9999 and (target_dir / f"{safe_doc_type}_{safe_stem}_{i}{ext}").exists():
                i += 1
            if i > 9999:
                logging.warning("archive_legal_docs: 重名文件数超限，跳过 %s", safe_filename)
                continue
            dest_path = (target_dir / f"{safe_doc_type}_{safe_stem}_{i}{ext}").resolve()

        try:
            atomic_write_bytes(dest_path, bytes(data))
        except OSError as e:
            logging.warning("archive_legal_docs: 写入失败 %s: %s", dest_path, e)
            continue

    return str(target_dir)
