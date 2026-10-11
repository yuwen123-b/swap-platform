"""翻译服务：qwen 文本模型中英互译。

- 专有名词（物品名、品牌、型号）保持原文，由提示词约束；
- 返回结果带 confidence；LLM 不可用时抛出 RuntimeError 由上层降级。
"""
from app.agents.prompts.i18n_prompts import AI_TRANSLATED_NOTE, TRANSLATE_PROMPT
from app.services import llm_client
from app.utils.i18n import normalize_lang

# 语言显示名，用于提示词
_LANG_NAME = {"zh_CN": "中文", "en_US": "英文"}


def translate(text: str, source_lang: str, target_lang: str) -> dict:
    """中英互译，返回 {translated_text, confidence, note}。"""
    source_lang = normalize_lang(source_lang)
    target_lang = normalize_lang(target_lang)
    text = (text or "").strip()
    if not text:
        raise ValueError("翻译内容不能为空")
    if source_lang == target_lang:
        return {"translated_text": text, "confidence": 1.0, "note": ""}

    prompt = TRANSLATE_PROMPT.format(
        source_lang=_LANG_NAME[source_lang], target_lang=_LANG_NAME[target_lang], text=text
    )
    result = llm_client.translate_text(text, prompt)
    return {
        "translated_text": result["translation"],
        "confidence": result["confidence"],
        # 按目标语言附 AI 翻译免责标注
        "note": AI_TRANSLATED_NOTE[target_lang],
    }
