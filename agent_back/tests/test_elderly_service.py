"""elderly_service 单元测试（数据库与 LLM 全部 mock）。"""
import pytest
from conftest import FakeCursor, make_connection

from app.services import elderly_service


@pytest.fixture(autouse=True)
def _mock_tts(monkeypatch):
    """默认关闭 TTS：单测不触达外部合成服务，response_audio_url 固定为空。"""
    monkeypatch.setattr("app.services.voice_service.synthesize", lambda *a, **k: "")


def _patch_db(monkeypatch, rows):
    cursor = FakeCursor(rows=rows)
    monkeypatch.setattr("app.services.elderly_service.connection", make_connection(cursor))
    return cursor


def test_empty_input_returns_not_heard(monkeypatch):
    result = elderly_service.interact(None, user_id=1, text="")
    assert result["intent"] == elderly_service.INTENT_UNKNOWN
    assert "再说一遍" in result["response_text"]
    assert result["action_result"]["card"] is None


def test_search_item_found(monkeypatch):
    _patch_db(monkeypatch, [{"id": 7, "title": "美的电饭煲"}])
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
    monkeypatch.setattr(
        "app.services.elderly_service.llm_client.understand_intent",
        lambda text, prompt, **fmt: {"intent": "search_item", "keyword": "航母"},
    )
    result = elderly_service.interact(None, user_id=1, text="我想换航母")
    assert result["action_result"]["card"]["status"] == "no"


def test_llm_failure_falls_back_to_rules_confirm(monkeypatch):
    def boom(text, prompt, **fmt):
        raise RuntimeError("LLM 不可用")

    monkeypatch.setattr("app.services.elderly_service.llm_client.understand_intent", boom)
    result = elderly_service.interact(None, user_id=1, text="我要换这个")
    assert result["intent"] == elderly_service.INTENT_CONFIRM
    assert result["action_result"]["card"]["status"] == "contacted"


def test_call_help_pushes_notification(monkeypatch):
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
    monkeypatch.setattr(
        "app.services.elderly_service.llm_client.understand_intent",
        lambda text, prompt, **fmt: {"intent": "publish_item", "keyword": ""},
    )
    result = elderly_service.interact(None, user_id=1, text="我要发布物品")
    assert result["action_result"]["action"] == {"type": "navigate", "path": "/recognition"}


def test_intent_prompt_format_works():
    """提示词 .format 花括号转义正确，{text} 占位符可替换。"""
    from app.agents.prompts.elderly_prompts import ELDERLY_INTENT_PROMPT

    rendered = ELDERLY_INTENT_PROMPT.format(text="我想换电饭煲")
    assert "我想换电饭煲" in rendered
    assert '"intent"' in rendered


def test_response_contains_entities(monkeypatch):
    """响应必须包含 entities 实体（keyword 透传，intent 不重复出现）。"""
    _patch_db(monkeypatch, [{"id": 7, "title": "美的电饭煲"}])
    monkeypatch.setattr(
        "app.services.elderly_service.llm_client.understand_intent",
        lambda text, prompt, **fmt: {"intent": "search_item", "keyword": "电饭煲"},
    )
    result = elderly_service.interact(None, user_id=1, text="我想换电饭煲")
    assert result["entities"] == {"keyword": "电饭煲"}


def test_tts_audio_url_returned(monkeypatch):
    """已配置 TTS 时，响应的 response_audio_url 应为后端合成的静态音频地址。"""
    _patch_db(monkeypatch, [{"id": 7, "title": "美的电饭煲"}])
    monkeypatch.setattr(
        "app.services.elderly_service.llm_client.understand_intent",
        lambda text, prompt, **fmt: {"intent": "search_item", "keyword": "电饭煲"},
    )
    monkeypatch.setattr(
        "app.services.voice_service.synthesize",
        lambda text, lang, rate: "/api/v1/static/tts/abc123.mp3",
    )
    result = elderly_service.interact(None, user_id=1, text="我想换电饭煲")
    assert result["response_audio_url"] == "/api/v1/static/tts/abc123.mp3"
    assert result["action_result"]["card"]["status"] == "ok"


def test_tts_unavailable_falls_back_to_empty_url(monkeypatch):
    """TTS 不可用（返回空串）时闭环不中断：response_audio_url 为空，文本回复正常。"""
    _patch_db(monkeypatch, [{"id": 7, "title": "美的电饭煲"}])
    monkeypatch.setattr(
        "app.services.elderly_service.llm_client.understand_intent",
        lambda text, prompt, **fmt: {"intent": "search_item", "keyword": "电饭煲"},
    )
    monkeypatch.setattr("app.services.voice_service.synthesize", lambda *a, **k: "")
    result = elderly_service.interact(None, user_id=1, text="我想换电饭煲")
    assert result["response_audio_url"] == ""
    assert "美的电饭煲" in result["response_text"]
    assert result["action_result"]["speech"]["rate"] == 0.8
