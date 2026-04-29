import os
from dotenv import load_dotenv

load_dotenv(override=True)

MODEL_CHAT   = os.getenv("MODEL_CHAT",   "glm-5-outside")
MODEL_VISION = os.getenv("MODEL_VISION", "qwen2.5-vl-72b")

AIRCHINA_API_KEY  = os.getenv("AIRCHINA_API_KEY",  "")
AIRCHINA_BASE_URL = os.getenv("AIRCHINA_BASE_URL",  "")
ZHISHU_API_KEY    = os.getenv("ZHISHU_API_KEY",     "")
ZHISHU_BASE_URL   = os.getenv("ZHISHU_BASE_URL",    "")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


AI_HTTP_VERIFY_SSL = _env_bool("AI_HTTP_VERIFY_SSL", True)

# Data directories — all user-generated content stored under the project's data/ folder
_BACKEND_DIR       = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT      = os.path.dirname(_BACKEND_DIR)
DATA_ROOT          = os.path.join(_PROJECT_ROOT, "data")
CHAT_HISTORY_PATH  = os.path.join(DATA_ROOT, "chat_history.json")
LEDGER_OUTPUT_DIR  = os.path.join(DATA_ROOT, "案件台账")
LEDGER_JSON_PATH   = os.path.join(DATA_ROOT, "案件台账", "cases.json")
LEDGER_EXCEL_PATH  = os.path.join(DATA_ROOT, "案件台账", "诉讼案件台账.xlsx")
LEGAL_ARCHIVE_ROOT = os.path.join(DATA_ROOT, "案件文书")
AUTH_LEDGER_DIR    = os.path.join(DATA_ROOT, "授权台账")
AUTH_LEDGER_PATH   = os.path.join(DATA_ROOT, "授权台账", "授权委托台账.xlsx")
