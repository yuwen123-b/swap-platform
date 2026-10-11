"""utils.i18n 单元测试。"""
from app.utils.i18n import DEFAULT_LANG, get_text, normalize_lang


def test_get_text_zh():
    assert get_text("elderly.card.ok", "zh_CN") == "可以换"


def test_get_text_en():
    assert get_text("elderly.card.ok", "en_US") == "Swap OK"


def test_get_text_missing_key_fallback_to_key():
    assert get_text("no.such.key", "zh_CN") == "no.such.key"


def test_normalize_lang():
    assert normalize_lang("en_US") == "en_US"
    assert normalize_lang("fr_FR") == DEFAULT_LANG
    assert normalize_lang(None) == DEFAULT_LANG
