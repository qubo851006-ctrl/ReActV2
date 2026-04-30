import base64
import os
import warnings
import httpx
from dotenv import load_dotenv
from openai import OpenAI
from config import AI_HTTP_VERIFY_SSL
from llm_client import build_ai_http_headers

warnings.filterwarnings("ignore")  # 屏蔽内网 SSL 警告
load_dotenv(override=True)

MODEL_VISION = os.getenv("MODEL_VISION", "qwen2.5-vl-72b")

# 两次识别结果允许的最大偏差，超过则标记为低置信度
_COUNT_DIFF_THRESHOLD = 2


def encode_image(image_path: str) -> str:
    """将图片转为 base64 字符串"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def get_client() -> OpenAI:
    return OpenAI(
        api_key=os.getenv("AIRCHINA_API_KEY"),
        base_url=os.getenv("AIRCHINA_BASE_URL"),
        http_client=httpx.Client(verify=AI_HTTP_VERIFY_SSL, headers=build_ai_http_headers()),
    )


def _call_vision(client: OpenAI, image_url: str, prompt: str) -> str:
    """向视觉模型发送一次请求，返回原始文本"""
    response = client.chat.completions.create(
        model=MODEL_VISION,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )
    return response.choices[0].message.content.strip()


def count_attendees(image_path: str) -> dict:
    """
    分析签到表图片，统计参与人数及提取抬头信息。
    包含自我反思步骤：第一次识别后进行二次验证，
    若两次结果偏差超过阈值则标记低置信度并取保守值。

    返回: {count, topic, location, date, confidence, reflection_note}
      - confidence: "high" | "low"
      - reflection_note: 反思检查的说明文字
    """
    client = get_client()

    image_data = encode_image(image_path)
    ext = image_path.split(".")[-1].lower()
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}
    mime_type = mime_map.get(ext, "image/jpeg")
    image_url = f"data:{mime_type};base64,{image_data}"

    first_prompt = """这是一张培训签到表图片。

第一步：提取抬头信息
- 培训主题、培训地点、培训时间

第二步：逐行列出所有有内容的姓名格
签到表分左右两栏，请从第1行开始，逐行检查左栏姓名格和右栏姓名格：
- 有手写内容的格子：写"有"
- 空白的格子：写"空"
格式示例：
行1：左=有，右=有
行2：左=有，右=空
行3：左=空，右=空（遇到连续空行可停止）

第三步：统计
把所有标记为"有"的格子数量加总，就是总人数。
注意：忽略表格底部任何手写的合计/估计数字。

请按以下格式输出，不要有多余内容：
主题：xxx
地点：xxx
时间：xxx
明细：（粘贴第二步的逐行结果）
人数：数字
"""

    # 第一次识别
    first_text = _call_vision(client, image_url, first_prompt)
    first_result = parse_sign_in_result(first_text)
    first_count = first_result["count"]

    # 反思提示：告知第一次结果，要求重新独立核查
    reflect_prompt = f"""这是同一张培训签到表图片。

有人刚才数了一遍，认为签到人数是 {first_count} 人。
请你独立重新核查一遍，不要受这个数字影响。

核查方法：
- 签到表分左右两栏，逐行检查每个姓名格
- 有手写内容的格子：写"有"，空白的格子：写"空"
- 把所有"有"的格子数量加总
- 忽略表格底部任何手写的合计数字

请按以下格式输出，不要有多余内容：
明细：（逐行结果）
人数：数字
"""

    # 第二次独立核查
    reflect_text = _call_vision(client, image_url, reflect_prompt)
    second_result = parse_sign_in_result(reflect_text)
    second_count = second_result["count"]

    # 综合两次结果
    diff = abs(first_count - second_count)
    if diff <= _COUNT_DIFF_THRESHOLD:
        # 两次结果接近，取较小值（保守估计，避免虚报）
        final_count = min(first_count, second_count)
        confidence = "high"
        reflection_note = f"两次识别结果一致（{first_count} / {second_count}），人数可信。"
    else:
        # 偏差较大，取较小值并标记低置信度
        final_count = min(first_count, second_count)
        confidence = "low"
        reflection_note = (
            f"⚠️ 两次识别结果存在偏差（第一次 {first_count} 人 / 核查 {second_count} 人），"
            f"已取较小值 {final_count} 人，建议人工复核签到表。"
        )

    return {
        "topic": first_result["topic"],
        "location": first_result["location"],
        "date": first_result["date"],
        "count": final_count,
        "confidence": confidence,
        "reflection_note": reflection_note,
    }


def parse_sign_in_result(text: str) -> dict:
    """解析 AI 返回的签到表信息"""
    result = {"topic": "", "location": "", "date": "", "count": 0}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("主题："):
            result["topic"] = line.replace("主题：", "").strip()
        elif line.startswith("地点："):
            result["location"] = line.replace("地点：", "").strip()
        elif line.startswith("时间："):
            result["date"] = line.replace("时间：", "").strip()
        elif line.startswith("人数："):
            count_str = line.replace("人数：", "").strip()
            try:
                result["count"] = int("".join(filter(str.isdigit, count_str)))
            except ValueError:
                result["count"] = 0
    return result
