"""助老模式服务：语音识别 → 意图理解 → 执行操作 → 生成口语化回复 的闭环。

- 语音识别：paraformer（voice_service.transcribe）；
- 意图理解：qwen 文本模型（llm_client.understand_intent），失败时用关键词规则兜底；
- 结果呈现：只输出「可以换 / 不行 / 已帮您联系」三种状态卡片。
"""
from pathlib import Path

from app.agents.prompts.elderly_prompts import ELDERLY_INTENT_PROMPT
from app.db.pool import connection
from app.services import accessibility_service, llm_client, notify_service, voice_service
from app.utils.i18n import get_text, lang_name, normalize_lang

# 意图枚举
INTENT_SEARCH = "search_item"
INTENT_PUBLISH = "publish_item"
INTENT_CONFIRM = "confirm_swap"
INTENT_HELP = "call_help"
INTENT_UNKNOWN = "unknown"

# 卡片三态
CARD_OK = "ok"
CARD_NO = "no"
CARD_CONTACTED = "contacted"


def _rule_intent(text: str) -> dict:
    """关键词规则兜底：LLM 不可用时保证助老闭环不中断。"""
    rules = [
        (("呼叫", "儿子", "女儿", "子女", "志愿者", "help"), INTENT_HELP),
        (("发布", "上传", "我有", "处理掉", "publish"), INTENT_PUBLISH),
        (("确认", "我要换", "就换", "联系对方", "confirm", "swap"), INTENT_CONFIRM),
        (("找", "想换", "想要", "有没有", "search", "want"), INTENT_SEARCH),
    ]
    lowered = text.lower()
    for keywords, intent in rules:
        if any(k in lowered or k in text for k in keywords):
            return {"intent": intent, "keyword": text if intent == INTENT_SEARCH else ""}
    return {"intent": INTENT_UNKNOWN, "keyword": ""}


def _understand(text: str, lang: str) -> dict:
    """意图理解：优先 LLM，异常时规则兜底。提示词按用户档案语言要求输出。"""
    try:
        return llm_client.understand_intent(
            text, ELDERLY_INTENT_PROMPT, language=lang_name(lang)
        )
    except RuntimeError:
        return _rule_intent(text)


def _resolve_lang(user_id: int, fallback: str) -> str:
    """交互语言以用户档案 preferred_lang 为准；档案不可读时回退请求参数。"""
    try:
        return accessibility_service.get_profile(user_id)["preferred_lang"]
    except Exception:
        return normalize_lang(fallback)


def _search_top_item(keyword: str) -> dict | None:
    """按关键词找一件可换物品（标题/描述模糊匹配，取最新）。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, title FROM item "
                "WHERE status=1 AND (title LIKE %s OR description LIKE %s) "
                "ORDER BY id DESC LIMIT 1",
                (f"%{keyword}%", f"%{keyword}%"),
            )
            return cursor.fetchone()


def _reply(intent: str, text: str, lang: str, card: dict | None,
           heard_text: str = "", action: dict | None = None) -> dict:
    """组装助老交互响应：口语化文本 + 播报参数 + 三态卡片。"""
    speech = voice_service.build_speech_text(text, mode="elderly", language=lang)
    return {
        "intent": intent,
        "response_text": text,
        # TTS 由前端 Web Speech API 完成，无音频文件 URL
        "response_audio_url": "",
        "action_result": {
            "card": card,
            "speech": speech,
            "heard_text": heard_text,
            "action": action,
        },
    }


def interact(audio_path: Path | None, user_id: int, text: str = "", lang: str = "zh_CN") -> dict:
    """助老交互主入口：audio 与 text 至少提供一个（audio 优先）。回复语言取自用户档案。"""
    lang = _resolve_lang(user_id, lang)
    heard_text = text.strip()
    if audio_path is not None and not heard_text:
        heard_text = voice_service.transcribe(audio_path).strip()

    if not heard_text:
        return _reply(INTENT_UNKNOWN, get_text("elderly.reply.not_heard", lang), lang, None)

    result = _understand(heard_text, lang)
    intent = result.get("intent") or INTENT_UNKNOWN
    keyword = (result.get("keyword") or "").strip()

    if intent == INTENT_SEARCH and keyword:
        item = _search_top_item(keyword)
        if item:
            card = {"status": CARD_OK, "label": get_text("elderly.card.ok", lang),
                    "item_id": item["id"], "item_title": item["title"]}
            text_out = f"{get_text('elderly.reply.found', lang)}{item['title']}"
            return _reply(intent, text_out, lang, card, heard_text)
        card = {"status": CARD_NO, "label": get_text("elderly.card.no", lang)}
        return _reply(intent, get_text("elderly.reply.not_found", lang), lang, card, heard_text)

    if intent == INTENT_PUBLISH:
        return _reply(intent, get_text("elderly.reply.publish_guide", lang), lang,
                      None, heard_text, action={"type": "navigate", "path": "/recognition"})

    if intent == INTENT_CONFIRM:
        card = {"status": CARD_CONTACTED, "label": get_text("elderly.card.contacted", lang)}
        return _reply(intent, get_text("elderly.reply.contacted", lang), lang, card, heard_text)

    if intent == INTENT_HELP:
        notify_service.push_help_alert(user_id, context=heard_text)
        card = {"status": CARD_CONTACTED, "label": get_text("elderly.card.contacted", lang)}
        return _reply(intent, get_text("elderly.reply.help_called", lang), lang, card, heard_text)

    return _reply(INTENT_UNKNOWN, get_text("elderly.reply.not_heard", lang), lang, None, heard_text)
