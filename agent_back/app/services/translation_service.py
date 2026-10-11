"""内容多语言翻译服务：英文模式下自动翻译数据库中的中文内容。

- 使用 openai 库调用阿里云百炼（LLM_API_KEY / LLM_API_URL）；
- LRU 缓存：同一段文本只翻译一次，避免重复浪费 Token；
- 任何异常返回原文，保证业务接口不被翻译故障阻断。
"""
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from openai import OpenAI

from app.core.config import settings

# 用户指定的翻译提示词模板
TRANSLATE_PROMPT = "请把以下内容翻译为英文，只输出翻译结果，不要任何解释：\n{text}"

# 缓存上限，防止长文本无限占用内存
_CACHE_SIZE = 1024


def normalize_request_lang(accept_language: str | None) -> str:
    """解析 Accept-Language 请求头（兼容 'zh'/'en'、'zh-CN'、'en-US,en;q=0.9' 等），返回 'zh' / 'en'。"""
    if not accept_language:
        return "zh"
    for part in accept_language.split(","):
        code = part.split(";")[0].strip().lower()
        if code.startswith("en"):
            return "en"
        if code.startswith("zh"):
            return "zh"
    return "zh"


@lru_cache(maxsize=_CACHE_SIZE)
def _translate_to_en(text: str) -> str:
    """调用大模型把文本翻译为英文（带缓存；失败返回原文）。"""
    try:
        client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_api_url)
        completion = client.chat.completions.create(
            model=settings.llm_api_model,
            messages=[{"role": "user", "content": TRANSLATE_PROMPT.format(text=text)}],
            timeout=30,
        )
        return (completion.choices[0].message.content or "").strip() or text
    except Exception:  # noqa: BLE001 翻译失败不阻断业务
        return text


def translate_text(text: str, target_lang: str) -> str:
    """把文本翻译为目标语言；目标为中文或内容为空时直接返回原文。"""
    text = (text or "").strip()
    if not text or target_lang != "en":
        return text
    return _translate_to_en(text)


def translate_many(texts: list[str], target_lang: str, max_workers: int = 8) -> list[str]:
    """并发翻译多段文本（内部共享缓存），返回顺序与输入一致。"""
    if target_lang != "en":
        return texts
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(lambda t: translate_text(t, target_lang), texts))
