"""elderly_service 单元测试（数据库与 LLM 全部 mock）。"""
from conftest import FakeCursor, make_connection

from app.services import elderly_service


def _patch_db(monkeypatch, rows):
    cursor = FakeCursor(rows=rows)
    monkeypatch.setattr("app.services.elderly_service.connection", make_connection(cursor))
    return cursor


def _patch_profile_lang(monkeypatch, lang="zh_CN"):
    """用户档案语言偏好：elderly_service 以档案 preferred_lang 为准。"""
    monkeypatch.setattr(
        "app.services.elderly_service.accessibility_service.get_profile",
        lambda user_id: {"preferred_lang": lang, "accessibility_mode": "normal",
                         "mobility_level": "free"},
    )


def test_empty_input_returns_not_heard(monkeypatch):
    _patch_profile_lang(monkeypatch)
    result = elderly_service.interact(None, user_id=1, text="", lang="zh_CN")
    assert result["intent"] == elderly_service.INTENT_UNKNOWN
    assert "再说一遍" in result["response_text"]
    assert result["action_result"]["card"] is None


def test_search_item_found(monkeypatch):
    _patch_db(monkeypatch, [{"id": 7, "title": "美的电饭煲"}])
    _patch_profile_lang(monkeypatch)
    monkeypatch.setattr(
        "app.services.elderly_service.llm_client.understand_intent",
        lambda text, prompt, **fmt: {"intent": "search_item", "keyword": "电饭煲"},
    )
    result = elderly_service.interact(None, user_id=1, text="我想换电饭煲")
    assert result["intent"] == "search_item"
    card = result["action_result"]["card"]
    assert card["status"] == "ok"
    assert card["label"] == "可以换"
    assert card["item_id"] == 7
    assert "美的电饭煲" in result["response_text"]
    # 播报参数：助老语速 0.8、单句 ≤20 字
    speech = result["action_result"]["speech"]
    assert speech["rate"] == 0.8
    assert all(len(s) <= 20 for s in speech["sentences"])


def test_search_item_not_found(monkeypatch):
    _patch_db(monkeypatch, [])
    _patch_profile_lang(monkeypatch)
    monkeypatch.setattr(
        "app.services.elderly_service.llm_client.understand_intent",
        lambda text, prompt, **fmt: {"intent": "search_item", "keyword": "航母"},
    )
    result = elderly_service.interact(None, user_id=1, text="我想换航母")
    assert result["action_result"]["card"]["status"] == "no"


def test_llm_failure_falls_back_to_rules_confirm(monkeypatch):
    _patch_profile_lang(monkeypatch)

    def boom(text, prompt, **fmt):
        raise RuntimeError("LLM 不可用")

    monkeypatch.setattr("app.services.elderly_service.llm_client.understand_intent", boom)
    result = elderly_service.interact(None, user_id=1, text="我要换这个")
    assert result["intent"] == elderly_service.INTENT_CONFIRM
    assert result["action_result"]["card"]["status"] == "contacted"


def test_call_help_pushes_notification(monkeypatch):
    _patch_profile_lang(monkeypatch)
    pushed = {}
    monkeypatch.setattr(
        "app.services.elderly_service.notify_service.push_help_alert",
        lambda user_id, context="": pushed.setdefault("args", (user_id, context)) or True,
    )
    monkeypatch.setattr(
        "app.services.elderly_service.llm_client.understand_intent",
        lambda text, prompt, **fmt: {"intent": "call_help", "keyword": ""},
    )
    result = elderly_service.interact(None, user_id=3, text="呼叫儿子")
    assert result["intent"] == elderly_service.INTENT_HELP
    assert pushed["args"][0] == 3
    assert "已通知" in result["response_text"]


def test_publish_intent_navigates(monkeypatch):
    _patch_profile_lang(monkeypatch)
    monkeypatch.setattr(
        "app.services.elderly_service.llm_client.understand_intent",
        lambda text, prompt, **fmt: {"intent": "publish_item", "keyword": ""},
    )
    result = elderly_service.interact(None, user_id=1, text="我要发布物品")
    assert result["action_result"]["action"] == {"type": "navigate", "path": "/recognition"}


def test_profile_lang_drives_reply_language(monkeypatch):
    """档案 preferred_lang=en_US 时，即便请求传 zh_CN，回复文本也应为英文。"""
    _patch_profile_lang(monkeypatch, lang="en_US")
    monkeypatch.setattr(
        "app.services.elderly_service.llm_client.understand_intent",
        lambda text, prompt, **fmt: {"intent": "publish_item", "keyword": ""},
    )
    result = elderly_service.interact(None, user_id=1, text="I want to publish", lang="zh_CN")
    # 英文文案来自后端 i18n/en_US.json，不应包含中文引导
    assert result["response_text"]
    assert all(ord(ch) < 0x4E00 or ord(ch) > 0x9FFF for ch in result["response_text"])
    assert result["action_result"]["speech"]["voice"] == "en-US"


def test_intent_prompt_contains_language_instruction():
    """提示词必须显式要求按用户语言处理（.format 花括号转义正确）。"""
    from app.agents.prompts.elderly_prompts import ELDERLY_INTENT_PROMPT

    rendered = ELDERLY_INTENT_PROMPT.format(text="我想换电饭煲", language="中文")
    assert "中文" in rendered
    assert '"intent"' in rendered
