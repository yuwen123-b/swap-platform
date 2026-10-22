"""智能体「商家知识 + 商家/积分工具」单元测试（DB 与 LLM 全部 mock）。

覆盖三块：
1. **路由判定** —— 商家/积分问题必须进入带工具的分支，寒暄不能误入
2. **工具契约与分发** —— schema 结构、只读容错、user_id 由服务端注入（防模型编造）
3. **提示词组装** —— 平台知识已注入、原文约束仍在、范围协调句收尾，
   以及「禁止编造未上线的换积分选项」这条防回归断言
"""
import json

import pytest
from conftest import FakeCursor, make_connection

from app.agents.prompts import assistant_prompts
from app.agents.prompts.assistant_prompts import (
    MERCHANT_KEYWORDS,
    MERCHANT_TOOL_DIRECTIVE,
    PLATFORM_OVERVIEW,
    SCOPE_NOTICE,
    build_points_rules_block,
)
from app.agents.tools import merchant_tools
from app.services import agent, merchant_service, points_service

# ============================================================
# 1. 路由判定
# ============================================================


@pytest.mark.parametrize(
    "question",
    [
        "用旧书换商家服务怎么兑换",  # 最初报障的原句
        "怎么兑换商家服务",
        "有哪些商家",
        "我积分多少",
        "我有多少积分",
        "我的积分够换纸巾吗",
        "积分怎么用",
        "平台有哪些店铺",
        "附近有没有打印店",  # 同时含物品关键词，必须同类分支
        "我想换一本教材",  # 纯物品问题也必须进同一分支（工具集含 search_items）
        "兑换一本教材",  # 含「兑换」的物品问题 → 允许进分支，靠 LLM 选工具不会答错
    ],
)
def test_merchant_questions_enter_tool_branch(question):
    assert agent._is_item_query_request(question) is True


@pytest.mark.parametrize("question", ["你好", "你是谁", "今天天气怎么样", "谢谢"])
def test_greeting_does_not_enter_tool_branch(question):
    assert agent._is_item_query_request(question) is False


def test_merchant_keywords_are_merged_into_item_keywords():
    """商家关键词必须与物品关键词合并在同一分支（本次设计的核心取舍）。"""
    for word in MERCHANT_KEYWORDS:
        assert word in agent._ITEM_QUERY_KEYWORDS
    # 原有物品关键词一个都不能丢
    for word in ("想换", "求购", "附近有", "二手"):
        assert word in agent._ITEM_QUERY_KEYWORDS


# ============================================================
# 2. 工具契约与分发
# ============================================================


def test_merchant_tools_schema_shape():
    assert len(merchant_tools.MERCHANT_TOOLS) == 3
    names = set()
    for tool in merchant_tools.MERCHANT_TOOLS:
        assert tool["type"] == "function"
        fn = tool["function"]
        assert isinstance(fn["name"], str) and fn["name"]
        assert isinstance(fn["description"], str) and len(fn["description"]) > 10
        assert fn["parameters"]["type"] == "object"
        assert "properties" in fn["parameters"]
        names.add(fn["name"])
    assert names == {"get_merchant_list", "get_merchant_products", "get_points_balance"}
    assert merchant_tools.MERCHANT_TOOL_NAMES == frozenset(names)


def test_merchant_tools_do_not_accept_user_id():
    """关键设计：工具 schema 里不能有 user_id，否则模型可能编造 id 查他人积分。"""
    for tool in merchant_tools.MERCHANT_TOOLS:
        assert "user_id" not in tool["function"]["parameters"]["properties"]
    # get_points_balance 必须无参
    points_tool = next(t for t in merchant_tools.MERCHANT_TOOLS if t["function"]["name"] == "get_points_balance")
    assert points_tool["function"]["parameters"]["required"] == []


def test_call_merchant_tool_unknown_name():
    payload = json.loads(merchant_tools.call_merchant_tool("no_such_tool", {}, 1))
    assert "error" in payload


def _patch_merchant_db(monkeypatch, rows):
    cursor = FakeCursor(rows=rows)
    monkeypatch.setattr(merchant_tools, "connection", make_connection(cursor))
    return cursor


def test_get_merchant_list_returns_shops(monkeypatch):
    _patch_merchant_db(
        monkeypatch,
        [
            {"id": 1, "name": "社区打印店", "category": "打印", "address": "1 号楼", "contact": "138", "description": "打印", "product_count": 2},
            {"id": 2, "name": "24小时便利店", "category": "便利店", "address": "2 号楼", "contact": "139", "description": "日用", "product_count": 2},
        ],
    )
    payload = json.loads(merchant_tools.call_merchant_tool("get_merchant_list", {}, None))
    assert payload["total"] == 2
    assert payload["merchants"][0]["merchant_id"] == 1
    assert payload["merchants"][0]["name"] == "社区打印店"
    # 不含签名 URL 之类噪音
    assert "logo_url" not in payload["merchants"][0]


def test_get_merchant_list_empty_with_category_hint(monkeypatch):
    cursor = _patch_merchant_db(monkeypatch, [])
    payload = json.loads(merchant_tools.call_merchant_tool("get_merchant_list", {"category": "宠物"}, None))
    assert payload["merchants"] == []
    assert "宠物" in payload["message"]
    # category 进了 SQL 参数（精确匹配），不是前端过滤
    sql, params = cursor.executed[-1]
    assert "m.category=%s" in sql
    assert "宠物" in params


def test_get_merchant_products_rejects_non_integer_id(monkeypatch):
    payload = json.loads(merchant_tools.call_merchant_tool("get_merchant_products", {"merchant_id": "一号店"}, None))
    assert "error" in payload
    assert "get_merchant_list" in payload["error"]


def test_get_merchant_products_returns_none_for_unapproved_merchant(monkeypatch):
    """未通过审核的商家 → 工具层转成友好错误，不泄露「存在但被拒绝」。"""
    _patch_merchant_db(monkeypatch, [{"id": 9, "name": "待审店", "status": merchant_service.MERCHANT_STATUS_PENDING}])
    payload = json.loads(merchant_tools.call_merchant_tool("get_merchant_products", {"merchant_id": 9}, None))
    assert payload["error"] == "商家不存在或暂未开放"


def test_get_merchant_products_marks_free_item(monkeypatch):
    cursor = _patch_merchant_db(
        monkeypatch,
        [
            {"id": 4, "name": "绿源回收站", "category": "回收", "address": "3 号楼", "contact": "137", "status": 1},
            {"id": 8, "title": "旧家电估价券", "points_cost": 0, "stock": 999, "sold_count": 0},
            {"id": 7, "title": "旧衣回收抵扣券", "points_cost": 50, "stock": 80, "sold_count": 3},
        ],
    )
    payload = json.loads(merchant_tools.call_merchant_tool("get_merchant_products", {"merchant_id": 4}, None))
    assert payload["merchant"]["name"] == "绿源回收站"
    assert payload["products"][0]["is_free"] is True
    assert payload["products"][1]["is_free"] is False
    # 只查在售（status=1）
    sql, params = cursor.executed[-1]
    assert "status=%s" in sql
    assert merchant_service.PRODUCT_STATUS_ONLINE in params


def test_get_points_balance_requires_login():
    payload = json.loads(merchant_tools.call_merchant_tool("get_points_balance", {}, None))
    assert "error" in payload


def test_get_points_balance_ignores_llm_supplied_user_id(monkeypatch):
    """★ 关键：模型即使塞了 user_id，也必须被忽略，只查服务端注入的当前用户。"""
    cursor = _patch_merchant_db(
        monkeypatch,
        [{"points": 320, "carbon_total": 15.0, "exchange_count": 3}],
    )
    payload = json.loads(
        merchant_tools.call_merchant_tool("get_points_balance", {"user_id": 999}, viewer_user_id=26)
    )
    assert payload["user_id"] == 26
    assert payload["points"] == 320
    _sql, params = cursor.executed[0]
    assert params == (26,)


def test_get_points_balance_includes_level_and_progress(monkeypatch):
    _patch_merchant_db(monkeypatch, [{"points": 320, "carbon_total": None, "exchange_count": None}])
    payload = json.loads(merchant_tools.call_merchant_tool("get_points_balance", {}, 26))
    assert payload["points"] == 320
    assert payload["level"] == 2 and payload["level_label"] == "LV2"
    assert payload["next_level"] == "LV3"
    assert payload["next_level_gap"] == 181  # 501 - 320
    assert payload["carbon_total"] == 0.0
    assert payload["exchange_count"] == 0


def test_tool_failure_returns_error_instead_of_raising(monkeypatch):
    """工具抖动不能中断对话：一律返回 {"error": ...}。"""
    def _boom():
        raise RuntimeError("连接池耗尽")

    monkeypatch.setattr(merchant_tools, "connection", _boom)
    payload = json.loads(merchant_tools.call_merchant_tool("get_merchant_list", {}, None))
    assert "error" in payload


def test_call_item_tool_dispatches_merchant_tool_with_viewer_id(monkeypatch):
    """agent._call_item_tool 必须能把商家工具转发出去，并带上当前用户。"""
    from app.services import agent

    seen = {}

    def _fake(name, args, viewer_user_id=None):
        seen["name"] = name
        seen["args"] = args
        seen["viewer"] = viewer_user_id
        return json.dumps({"ok": True}, ensure_ascii=False)

    monkeypatch.setattr(agent, "call_merchant_tool", _fake)
    result = json.loads(agent._call_item_tool("get_points_balance", {}, viewer_user_id=26))
    assert result == {"ok": True}
    assert seen == {"name": "get_points_balance", "args": {}, "viewer": 26}


def test_call_item_tool_still_handles_unknown_tool():
    from app.services import agent

    payload = json.loads(agent._call_item_tool("whatever_tool", {}))
    assert "error" in payload


# ============================================================
# 3. 提示词组装
# ============================================================


def _prompt_without_db(monkeypatch, rules=None):
    from app.services import agent

    monkeypatch.setattr(agent, "_read_effective_rules", lambda: (rules or {}))
    return agent._base_system_prompt(False)


def test_platform_knowledge_is_injected(monkeypatch):
    """根因修复：所有分支都必须拿到平台功能描述。"""
    prompt = _prompt_without_db(monkeypatch)
    for anchor in ("闲物焕新", "积分商城", "核销码", "社区商家", "免费送", "低价转让", "审核通过"):
        assert anchor in prompt
    assert PLATFORM_OVERVIEW in prompt


def test_original_role_and_constraints_are_untouched(monkeypatch):
    """原文一个字不改：角色定义与禁语黑名单必须原样保留。"""
    from app.services import agent

    prompt = _prompt_without_db(monkeypatch)
    assert agent.SYSTEM_PROMPT in prompt
    assert "社区百事通式工具型助手" in prompt
    assert "不要主动推荐用户去做别的操作" in prompt
    assert "禁止输出以下模板话术" in prompt


def test_scope_notice_closes_the_platform_block(monkeypatch):
    """范围协调句必须收尾，避免与「不主动推荐」约束互相打架。"""
    prompt = _prompt_without_db(monkeypatch)
    assert prompt.endswith(SCOPE_NOTICE)
    assert "仅在用户主动询问兑换、积分、商家、平台规则时使用" in prompt


def test_english_directive_stays_last(monkeypatch):
    from app.services import agent

    monkeypatch.setattr(agent, "_read_effective_rules", lambda: {})
    prompt = agent._base_system_prompt(True)
    assert prompt.endswith(agent.EN_LANGUAGE_DIRECTIVE)
    assert SCOPE_NOTICE in prompt


def test_prompt_describes_direct_recycle_option(monkeypatch):
    """★ 防回归（二期翻转）：任务书原稿曾让 AI 教用户「发布时选『换积分』」——当时该选项
    不存在，提示词因此有一句「没有『换积分』选项」。二期上线「交给平台回收」后，
    「发布时直接换积分」成为真实功能，那句否定句会变成谎言，已删除并改为正向描述。"""
    prompt = _prompt_without_db(monkeypatch)
    # 「交给平台回收」作为发布时的真实可选项出现
    assert "交给平台回收" in prompt
    # 旧否定句已删除（否则 AI 会否认刚上线的功能）
    assert "没有「发布时直接选『换积分』」这个选项" not in prompt
    # 断言式（错误）说法仍不存在
    assert "选'换积分'" not in prompt
    assert "选「换积分」或" not in prompt
    assert "选「换积分」和" not in prompt


def test_points_rules_use_live_values_and_fallback():
    live = build_points_rules_block({"points_publish": 30, "points_exchange": 60, "carbon_per_exchange": 8.0})
    assert "+30 积分" in live and "+60 积分" in live and "+8kg" in live
    # 缺字段 / 传 None → 回落默认值，不抛异常
    fallback = build_points_rules_block(None)
    assert "+10 积分" in fallback and "+20 积分" in fallback and "+5kg" in fallback
    partial = build_points_rules_block({"points_publish": 15})
    assert "+15 积分" in partial and "+20 积分" in partial


def test_base_prompt_reads_live_rules_from_config(monkeypatch):
    """提示词里的分值必须来自 sys_config，不能写死。"""
    from app.services import agent

    cursor = FakeCursor(
        rows=[{"config_value": "10"}, {"config_value": "20"}, {"config_value": "5.0"}]
    )
    monkeypatch.setattr(agent, "connection", make_connection(cursor))
    rules = agent._read_effective_rules()
    assert rules == {"points_publish": 10, "points_exchange": 20, "carbon_per_exchange": 5.0}
    # 同一份 rules 拿去拼提示词（假游标一次性取空，真实库可重复读）
    monkeypatch.setattr(agent, "_read_effective_rules", lambda: rules)
    prompt = agent._base_system_prompt(False)
    assert "+10 积分" in prompt and "+20 积分" in prompt and "+5kg" in prompt


def test_base_prompt_survives_db_failure(monkeypatch):
    """sys_config 不可用不能让对话 500，必须回落**代码默认值**。

    注意：代码默认值（20 / 50）与 DB 现值（10 / 20）并不一致，
    这里断言的是「回落成功」，不是「等于 DB 值」。
    """
    from app.services import agent

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(agent, "connection", _boom)
    rules = agent._read_effective_rules()
    assert rules["points_publish"] == points_service.DEFAULT_POINTS_PUBLISH
    assert rules["points_exchange"] == points_service.DEFAULT_POINTS_EXCHANGE
    prompt = agent._base_system_prompt(False)
    assert f"+{points_service.DEFAULT_POINTS_PUBLISH} 积分" in prompt


def test_merchant_tool_directive_mentions_tools(monkeypatch):
    """分支指令必须点名三个工具，否则模型不知道有工具可用。"""
    assert "get_merchant_list" in MERCHANT_TOOL_DIRECTIVE
    assert "get_merchant_products" in MERCHANT_TOOL_DIRECTIVE
    assert "get_points_balance" in MERCHANT_TOOL_DIRECTIVE
    # 流程类问题不必调工具（避免「怎么兑换」也去查库）
    assert "不必调用工具" in MERCHANT_TOOL_DIRECTIVE


def test_scope_notice_is_the_exact_agreed_wording():
    assert SCOPE_NOTICE.strip() == (
        "以上平台功能说明仅在用户主动询问兑换、积分、商家、平台规则时使用。"
        "其他问题仍遵守原有约束，不主动推荐用户去做别的操作。"
    )
    assert assistant_prompts.SCOPE_NOTICE == SCOPE_NOTICE


# ============================================================
# 4. 服务层只读函数
# ============================================================


def test_list_approved_shops_only_returns_approved():
    cursor = FakeCursor(rows=[])
    merchant_service.list_approved_shops(cursor)
    sql, params = cursor.executed[0]
    assert "m.status=%s" in sql
    assert params[0] == merchant_service.MERCHANT_STATUS_APPROVED
    assert "LIMIT %s" in sql


def test_list_approved_shops_clamps_limit():
    cursor = FakeCursor(rows=[])
    merchant_service.list_approved_shops(cursor, limit=9999)
    assert cursor.executed[0][1][-1] == merchant_service.AGENT_SHOP_LIMIT


def test_list_shop_products_by_id_keyword_and_limit():
    cursor = FakeCursor(
        rows=[
            {"id": 1, "name": "社区打印店", "category": "打印", "status": 1},
            {"id": 1, "title": "打印券10张", "points_cost": 50, "stock": 95, "sold_count": 5},
        ]
    )
    result = merchant_service.list_shop_products_by_id(cursor, merchant_id=1, keyword="打印")
    assert result["products"][0]["title"] == "打印券10张"
    sql, params = cursor.executed[-1]
    assert "title LIKE %s" in sql
    assert "%打印%" in params


def test_get_effective_rules_returns_defaults_when_config_empty():
    cursor = FakeCursor(rows=[None, None, None])
    rules = points_service.get_effective_rules(cursor)
    assert rules == {
        "points_publish": points_service.DEFAULT_POINTS_PUBLISH,
        "points_exchange": points_service.DEFAULT_POINTS_EXCHANGE,
        "carbon_per_exchange": points_service.DEFAULT_CARBON_PER_EXCHANGE,
    }


def test_get_points_snapshot_returns_none_for_missing_user():
    cursor = FakeCursor(rows=[None])
    assert points_service.get_points_snapshot(cursor, 404) is None


def test_get_points_snapshot_rejects_bad_user_id():
    cursor = FakeCursor(rows=[])
    assert points_service.get_points_snapshot(cursor, "abc") is None
    assert cursor.executed == []
