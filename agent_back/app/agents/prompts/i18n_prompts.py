"""国际化相关提示词：翻译与跨语言协商。"""

# 中英互译提示词：专有名词（物品名、品牌、型号）保持原文
# 注意：JSON 示例中的花括号已转义为 {{ }}，供 str.format 使用
TRANSLATE_PROMPT = (
    "你是专业翻译。把下面文本从 {source_lang} 翻译成 {target_lang}。\n"
    "要求：1. 物品名称、品牌、型号等专有名词保持原文不翻译（如 美的、iPhone、Nike）；"
    "2. 只返回 JSON："
    '{{"translation":"译文","confidence":0.0到1.0之间的置信度}}；'
    "3. 不要输出任何解释。\n"
    "原文：{text}"
)

# Agent 协商时的语言指令：双方语言不同则自动附译文并标注
NEGOTIATION_LANG_HINT = (
    "协商双方语言分别为 {lang_a} 与 {lang_b}。"
    "若两者不同，你输出的每条消息必须附对方语言的译文，"
    "并在译文末尾标注“由 AI 翻译，仅供参考 / Translated by AI, for reference only”。"
)

# AI 翻译免责标注（双语）
AI_TRANSLATED_NOTE = {
    "zh_CN": "由 AI 翻译，仅供参考",
    "en_US": "Translated by AI, for reference only",
}
