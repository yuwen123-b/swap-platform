"""物品识别服务：OpenAI SDK 调用阿里云百炼多模态模型；未配置 Key 或调用失败时降级演示模式。

支持按请求语言（zh/en）输出对应语言的识别结果。
"""
import base64
import io
import json
import logging

from openai import OpenAI
from PIL import Image

from app.core.config import settings
from app.services.agent import CATEGORIES, _valid_recognition, mock_recognition

logger = logging.getLogger(__name__)

# 识别前把图片压到该边长内，控制请求体大小与多模态 token 消耗
MAX_SIDE = 1024
JPEG_QUALITY = 85
REQUEST_TIMEOUT = 60

ZH_SYSTEM_PROMPT = (
    "你是一个旧物识别专家，必须以 JSON 格式返回物品名称、分类、成色、标签。"
    "只输出一个 JSON 对象，不要输出任何多余文字，格式："
    '{"name":"物品名称",'
    '"category":"最匹配的分类，从这些里选一个：' + "/".join(CATEGORIES) + '",'
    '"condition_level":1到5的整数，5表示全新,'
    '"description":"30字以内的闲置转卖描述",'
    '"tags":["3个简短标签"]}'
)

# 英文分类（与 zh CATEGORIES 一一对应，顺序一致）
EN_CATEGORIES = {
    "数码电子": "Digital & Electronics",
    "家居家电": "Home & Appliances",
    "图书文具": "Books & Stationery",
    "服饰鞋包": "Clothing & Bags",
    "母婴用品": "Mom & Baby",
    "运动户外": "Sports & Outdoors",
    "美妆个护": "Beauty & Personal Care",
    "其他闲置": "Other pre-loved items",
}

# 英文提示词：JSON 键与中文保持一致（name/category/condition_level/description/tags），仅要求内容用英文
EN_SYSTEM_PROMPT = (
    "You are an item recognition expert. Output JSON format with keys: "
    "name, category, condition_level, description, tags. YOU MUST OUTPUT IN ENGLISH. "
    "category must be one of: " + " / ".join(EN_CATEGORIES.values()) + ". "
    "condition_level: integer from 1 (poor) to 5 (brand new). "
    "description: a pre-loved resale description within 30 words. "
    "tags: 3 short tags. Output only the JSON object, no extra text."
)


def is_configured() -> bool:
    """DASHSCOPE_API_KEY 是否已配置。"""
    return bool(settings.dashscope_api_key.strip())


def preprocess_image(data: bytes) -> tuple[bytes, str]:
    """用 Pillow 校验并压缩图片，返回 (jpeg_bytes, mime)；无法解析时抛 ValueError。"""
    try:
        with Image.open(io.BytesIO(data)) as img:
            img = img.convert("RGB")
            if max(img.size) > MAX_SIDE:
                img.thumbnail((MAX_SIDE, MAX_SIDE))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=JPEG_QUALITY)
            return buf.getvalue(), "image/jpeg"
    except Exception as exc:
        raise ValueError("图片无法解析，请换一张清晰的实物照片") from exc


def _valid_recognition_en(data: dict) -> dict | None:
    """英文识别结果归一化：分类限制在英文枚举内，成色钳位 1-5。"""
    name = str(data.get("name") or "").strip()
    if not name:
        return None
    category = str(data.get("category") or "").strip()
    if category not in EN_CATEGORIES.values():
        category = EN_CATEGORIES["其他闲置"]
    try:
        condition = int(data.get("condition_level") or 3)
    except (TypeError, ValueError):
        condition = 3
    condition = max(1, min(5, condition))
    tags = data.get("tags") if isinstance(data.get("tags"), list) else []
    return {
        "name": name[:64],
        "category": category,
        "condition_level": condition,
        "description": str(data.get("description") or "").strip()[:200],
        "tags": [str(t)[:16] for t in tags][:6],
    }


def mock_recognition_en() -> dict:
    """英文演示模式结果。"""
    return {
        "name": "Demo recognition result",
        "category": EN_CATEGORIES["其他闲置"],
        "condition_level": 4,
        "description": "Demo mode: configure the LLM_VL_MODEL multimodal model in .env for real recognition.",
        "tags": ["demo", "pre-loved", "eco"],
    }


def recognize_image(data: bytes, mime: str, lang: str = "zh") -> dict:
    """调用多模态模型识别物品，返回结构化结果（含 engine=llm）。失败时抛异常。"""
    jpeg_data, jpeg_mime = preprocess_image(data)
    image_base64 = base64.b64encode(jpeg_data).decode()

    system_prompt = EN_SYSTEM_PROMPT if lang == "en" else ZH_SYSTEM_PROMPT
    user_text = (
        "Recognize the pre-loved item in the image and return the JSON defined by the system prompt."
        if lang == "en"
        else "请识别图中的闲置物品，按 system 约定的 JSON 格式返回。"
    )
    client = OpenAI(api_key=settings.dashscope_api_key, base_url=settings.llm_api_url)
    completion = client.chat.completions.create(
        model=settings.llm_vl_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{jpeg_mime};base64,{image_base64}"}},
                    {"type": "text", "text": user_text},
                ],
            },
        ],
        timeout=REQUEST_TIMEOUT,
    )

    content = (completion.choices[0].message.content or "").strip()
    parsed = _extract_json(content)
    result = _valid_recognition_en(parsed) if lang == "en" else _valid_recognition(parsed)
    if not result:
        raise ValueError(f"识别结果缺少物品名称：{content[:200]}")
    result["engine"] = "llm"
    return result


def recognize_with_fallback(data: bytes, mime: str, lang: str = "zh") -> dict:
    """对外入口：未配置 Key 或调用/解析失败时，降级演示模式并附友好提示。"""
    if not is_configured():
        base = mock_recognition_en() if lang == "en" else mock_recognition()
        notice = (
            "DASHSCOPE_API_KEY is not configured; running in demo mode. Configure it in .env for real recognition."
            if settings.debug
            else "未配置 DASHSCOPE_API_KEY，当前为演示模式；在 .env 配置后即可真实识别。"
        )
        return {**base, "engine": "mock", "notice": notice}
    try:
        return recognize_image(data, mime, lang)
    except Exception:
        logger.exception("物品识别调用失败，降级演示模式")
        base = mock_recognition_en() if lang == "en" else mock_recognition()
        notice = (
            "AI recognition is temporarily unavailable; a demo result is returned. Please retry later."
            if lang == "en"
            else "AI 识别服务暂时不可用，已返回演示结果，请稍后重试。"
        )
        return {**base, "engine": "mock", "notice": notice}


def _extract_json(content: str) -> dict:
    """从模型回答中截取首个 {...} 片段并解析为 dict。"""
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"模型未返回 JSON：{content[:200]}")
    return json.loads(content[start:end + 1])
