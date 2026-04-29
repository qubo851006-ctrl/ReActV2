import httpx
from openai import OpenAI
from config import AIRCHINA_API_KEY, AIRCHINA_BASE_URL, AI_HTTP_VERIFY_SSL


def get_llm_client() -> OpenAI:
    return OpenAI(
        api_key=AIRCHINA_API_KEY,
        base_url=AIRCHINA_BASE_URL,
        http_client=httpx.Client(verify=AI_HTTP_VERIFY_SSL),
    )
