"""情感分析：词典规则打底；配置 LLM_API_KEY 后优先大模型判定，失败自动回退词典。

label 取值：positive（良好）/ neutral（中性）/ negative（差）。
"""
from app.services import dashscope

_POSITIVE_WORDS = [
    "好用", "不错", "满意", "喜欢", "方便", "贴心", "温暖", "赞", "棒", "优秀",
    "流畅", "美观", "实用", "推荐", "开心", "帮助", "及时", "友好", "耐心", "干净",
    "实惠", "环保", "信任", "顺利", "感动", "靠谱", "超值", "完善", "惊喜", "有趣",
    "感谢", "支持", "高效", "清晰", "快捷", "舒服", "热心", "放心", "完美", "简单",
    "称赞", "好评", "人性化", "给力",
]
_NEGATIVE_WORDS = [
    "垃圾", "失望", "卡顿", "难用", "糟糕", "故障", "崩溃", "骗", "坑", "烦",
    "讨厌", "不满", "敷衍", "浪费", "虚假", "恶心", "落后", "难看", "混乱", "投诉",
    "退款", "离谱", "生气", "无语", "低效", "不行", "太烂", "差评", "吐槽", "难找",
    "闪退", "掉帧", "延迟高", "鸡肋", "反人类", "没诚意", "摆烂", "辣鸡", "很差", "差劲",
]
_NEGATIONS = ("不", "没", "无", "别", "非", "莫", "未", "毫不", "并不", "一点也不")


def lexicon_score(text: str) -> float:
    """中文情感词典打分，归一化到 [-1, 1]；含简单否定词反转。"""
    pos = neg = 0
    for word in _POSITIVE_WORDS:
        idx = text.find(word)
        while idx != -1:
            prefix = text[max(0, idx - 3):idx]
            if any(prefix.endswith(n) for n in _NEGATIONS):
                neg += 1
            else:
                pos += 1
            idx = text.find(word, idx + 1)
    for word in _NEGATIVE_WORDS:
        idx = text.find(word)
        while idx != -1:
            prefix = text[max(0, idx - 3):idx]
            if any(prefix.endswith(n) for n in _NEGATIONS):
                pos += 1
            else:
                neg += 1
            idx = text.find(word, idx + 1)
    total = pos + neg
    if total == 0:
        return 0.0
    return round((pos - neg) / total, 3)


def _llm_analyze(text: str) -> dict | None:
    try:
        data = dashscope.chat_json([
            {"role": "system", "content": (
                "你是情感分析引擎。对用户发给程序平台的评价做情感分类，"
                '只输出 JSON：{"label":"positive/neutral/negative","score":-1到1的小数}。'
                "positive=良好，neutral=中性，negative=差。"
            )},
            {"role": "user", "content": text[:500]},
        ])
        label = str(data.get("label") or "").strip().lower()
        score = float(data.get("score") or 0)
        if label in ("positive", "neutral", "negative"):
            return {"label": label, "score": round(max(-1.0, min(1.0, score)), 3), "engine": "llm"}
    except Exception:
        pass
    return None


def _label_from_score(score: float) -> str:
    if score >= 0.3:
        return "positive"
    if score <= -0.3:
        return "negative"
    return "neutral"


def analyze(text: str) -> dict:
    """返回 {"label": ..., "score": -1~1, "engine": "llm"/"lexicon"}。"""
    if dashscope.has_key():
        result = _llm_analyze(text)
        if result:
            return result
    score = lexicon_score(text)
    return {"label": _label_from_score(score), "score": score, "engine": "lexicon"}
