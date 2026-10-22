"""无障碍模式服务：模式设置、语音标签生成、用户无障碍档案。"""
import json
from pathlib import Path

from app.core.config import settings
from app.db.pool import connection
from app.services import llm_client
from app.services.image_utils import normalize_image_ref

# 无障碍模式枚举
MODE_NORMAL = "normal"
MODE_VISUAL = "visually_impaired"
MODE_MOBILITY = "mobility_impaired"
VALID_MODES = (MODE_NORMAL, MODE_VISUAL, MODE_MOBILITY)

# 行动能力枚举
MOBILITY_FREE = "free"
MOBILITY_LIMITED = "limited"
MOBILITY_ASSISTED = "assisted"
VALID_MOBILITY = (MOBILITY_FREE, MOBILITY_LIMITED, MOBILITY_ASSISTED)

# 成色文案（item.condition_level 的口语化映射，按语言）
_CONDITION_TEXT = {0: "全新", 1: "九成新", 2: "八成新", 3: "有使用痕迹"}
_CONDITION_TEXT_EN = {0: "brand new", 1: "90% new", 2: "80% new", 3: "gently used"}

# 语音标签提示词：物品名+成色+颜色+特征，一句话
_VOICE_LABEL_PROMPT = (
    "根据物品信息生成一句中文语音标签，格式为「物品名+成色+颜色+特征」，"
    "不超过 30 字，只输出标签本身，不要解释。\n"
    "物品名：{title}\n描述：{description}"
)

# 语音标签提示词（多模态版）：图片与文本结合，颜色/成色优先依据图片判断
_VOICE_LABEL_IMAGE_PROMPT = (
    "根据物品图片与文字信息生成一句中文语音标签，格式为「物品名+成色+颜色+特征」，"
    "颜色与成色优先依据图片判断，不超过 30 字，只输出标签本身，不要解释。\n"
    "物品名：{title}\n描述：{description}"
)


def set_mode(user_id: int, mode: str) -> dict:
    """设置用户无障碍模式，返回对应 UI 配置。"""
    if mode not in VALID_MODES:
        raise ValueError(f"不支持的无障碍模式：{mode}")
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE user SET accessibility_mode=%s WHERE id=%s", (mode, user_id))
            if cursor.rowcount == 0:
                raise ValueError("用户不存在")
    return {"success": True, "ui_config": ui_config_for(mode)}


def set_mobility(user_id: int, mobility_level: str) -> dict:
    """设置用户行动能力等级。"""
    if mobility_level not in VALID_MOBILITY:
        raise ValueError(f"不支持的行动能力等级：{mobility_level}")
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE user SET mobility_level=%s WHERE id=%s", (mobility_level, user_id))
            if cursor.rowcount == 0:
                raise ValueError("用户不存在")
    return {"success": True, "mobility_level": mobility_level}


def ui_config_for(mode: str) -> dict:
    """按模式给出前端 UI 配置：语音导航、高对比度、是否跳过自取。"""
    return {
        "mode": mode,
        "voice_navigation": mode == MODE_VISUAL,
        "high_contrast": mode == MODE_VISUAL,
        "skip_self_pickup": mode == MODE_MOBILITY,
        "volunteer_entry": mode == MODE_MOBILITY,
    }


def get_profile(user_id: int) -> dict:
    """读取用户无障碍档案，缺列或用户不存在时返回默认值。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT mobility_level, accessibility_mode, preferred_lang FROM user WHERE id=%s LIMIT 1",
                (user_id,),
            )
            row = cursor.fetchone()
    if not row:
        raise ValueError("用户不存在")
    return {
        "mobility_level": row.get("mobility_level") or MOBILITY_FREE,
        "accessibility_mode": row.get("accessibility_mode") or MODE_NORMAL,
        "preferred_lang": row.get("preferred_lang") or "zh_CN",
    }


def _first_local_image(images_json: str | None) -> Path | None:
    """解析物品图片 JSON，返回首图本地文件路径；无图、解析失败或文件不存在返回 None。

    2026-10 起 item.images 只存**相对路径**（`items/xxx.webp`），读取时才签名；
    历史脏数据里可能仍是带 `?exp=&sig=` 的签名 URL——统一经 `normalize_image_ref`
    归一成相对路径，两种形态都能解析（与 TTS / 物品图片同一挂载规则）；
    校验解析结果必须落在 uploads 目录内，防路径穿越。
    """
    if not images_json:
        return None
    try:
        urls = json.loads(images_json)
    except (TypeError, ValueError):
        return None
    if not isinstance(urls, list) or not urls:
        return None
    ref = normalize_image_ref(urls[0])
    if not ref or ref.startswith(("http://", "https://")):
        return None
    root = Path(settings.upload_dir).resolve()
    path = (root / ref).resolve()
    if root not in path.parents or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        return None
    return path if path.is_file() else None


def _label_from_image(image_path: Path, item: dict) -> str | None:
    """多模态生成语音标签（qwen-vl 分析物品图片+文本）；失败返回 None。"""
    prompt = _VOICE_LABEL_IMAGE_PROMPT.format(
        title=item["title"],
        description=(item.get("description") or "")[:200],
    )
    try:
        label = llm_client.describe_image(str(image_path), prompt).strip().strip("。").strip('"')
        return label or None
    except RuntimeError:
        return None


def _label_from_text(item: dict) -> str | None:
    """纯文本生成语音标签（无图或多模态失败时兜底）；失败返回 None。"""
    prompt = _VOICE_LABEL_PROMPT.format(
        title=item["title"],
        description=(item.get("description") or "")[:200],
    )
    try:
        label = llm_client.chat_text([{"role": "user", "content": prompt}], timeout=30)
        return label.strip().strip("。") or None
    except RuntimeError:
        return None


def generate_voice_label(item_id: int, language: str = "zh_CN") -> str:
    """为物品生成语音标签「物品名+成色+颜色+特征」，中文输出。

    生成链路三级降级：qwen-vl 多模态分析物品首图（颜色/成色更准确）
    → 纯文本生成 → 字段拼接，任何一级失败都不抛异常。
    """
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT title, description, condition_level, images FROM item WHERE id=%s LIMIT 1",
                (item_id,),
            )
            item = cursor.fetchone()
    if not item:
        raise ValueError("物品不存在")

    label = None
    image_path = _first_local_image(item.get("images"))
    if image_path:
        label = _label_from_image(image_path, item)
    if not label:
        label = _label_from_text(item)
    if label and len(label) <= 40:
        return label

    # 最终降级：直接拼接物品名与成色
    condition = _CONDITION_TEXT.get(item.get("condition_level") or 0, "成色良好")
    return f"{item['title']}，{condition}"
