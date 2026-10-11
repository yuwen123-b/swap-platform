"""无障碍模式服务：模式设置、语音标签生成、用户无障碍档案。"""
from app.db.pool import connection
from app.services import llm_client
from app.utils.i18n import lang_name, normalize_lang

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

# 语音标签提示词：物品名+成色+颜色+特征，一句话；{language} 明确输出语言
_VOICE_LABEL_PROMPT = (
    "根据物品信息生成一句{language}语音标签，格式为「物品名+成色+颜色+特征」，"
    "必须使用{language}输出，不超过 30 字，只输出标签本身，不要解释。\n"
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


def generate_voice_label(item_id: int, language: str = "zh_CN") -> str:
    """为物品生成语音标签「物品名+成色+颜色+特征」，按指定语言输出；LLM 失败时降级字段拼接。"""
    lang = normalize_lang(language)
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT title, description, condition_level FROM item WHERE id=%s LIMIT 1",
                (item_id,),
            )
            item = cursor.fetchone()
    if not item:
        raise ValueError("物品不存在")

    prompt = _VOICE_LABEL_PROMPT.format(
        language=lang_name(lang),
        title=item["title"],
        description=(item.get("description") or "")[:200],
    )
    try:
        label = llm_client.chat_text([{"role": "user", "content": prompt}], timeout=30)
        label = label.strip().strip("。")
        if label and len(label) <= 40:
            return label
    except RuntimeError:
        pass
    # 降级：直接拼接物品名与成色（按语言）
    if lang == "en_US":
        condition = _CONDITION_TEXT_EN.get(item.get("condition_level") or 0, "good condition")
        return f"{item['title']}, {condition}"
    condition = _CONDITION_TEXT.get(item.get("condition_level") or 0, "成色良好")
    return f"{item['title']}，{condition}"
