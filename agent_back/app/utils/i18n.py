"""后端文案国际化：读取 i18n/*.json，提供 get_text(key, lang)。

语言文件位于 agent_back/i18n/ 目录下；键缺失时回退默认语言，再回退为键本身。
"""
import json
from functools import lru_cache
from pathlib import Path

I18N_DIR = Path(__file__).resolve().parents[2] / "i18n"
SUPPORTED_LANGS = ("zh_CN", "en_US")
DEFAULT_LANG = "zh_CN"

# 语言标识 -> 提示词中使用的人类可读语言名（要求 LLM 用该语言回复）
LANG_NAMES = {"zh_CN": "中文", "en_US": "英文"}


def lang_name(lang: str | None) -> str:
    return LANG_NAMES.get(normalize_lang(lang), "中文")


@lru_cache
def _load(lang: str) -> dict:
    path = I18N_DIR / f"{lang}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_lang(lang: str | None) -> str:
    """非法或缺失的语言标识回退为默认语言。"""
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG


def get_text(key: str, lang: str | None = DEFAULT_LANG) -> str:
    """按语言取文案；当前语言缺失时回退中文，再缺失返回 key 本身。"""
    lang = normalize_lang(lang)
    return _load(lang).get(key) or _load(DEFAULT_LANG).get(key) or key
