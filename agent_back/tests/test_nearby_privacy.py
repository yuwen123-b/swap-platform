"""附近物品查询的隐私过滤测试（数据库 mock，不连真实 MySQL）。

验证 location_public 隐私开关的四条规则：
1. 位置未公开的用户，其物品不出现在他人附近搜索结果中
2. 位置已公开的用户，其物品正常出现
3. 用户查看自己的物品不受自身 location_public 影响
4. 未登录（无 viewer_user_id）时按最严格策略，仅返回已公开物品
"""
from conftest import FakeCursor, make_connection

from app.services import item_query_service as query_service


def _patch(monkeypatch, rows=None):
    cursor = FakeCursor(rows=rows or [])
    monkeypatch.setattr(query_service, "connection", make_connection(cursor))
    return cursor


def _capture_sql(monkeypatch, **kwargs):
    """执行 find_nearby_items 并返回实际下发的 (sql, params)。"""
    cursor = _patch(monkeypatch)
    query_service.find_nearby_items(39.9, 116.4, 5.0, **kwargs)
    assert cursor.executed, "未执行任何 SQL"
    return cursor.executed[0]


def test_nearby_always_joins_user_for_privacy(monkeypatch):
    """查询必须 JOIN user 表，否则隐私过滤无从生效。"""
    sql, _ = _capture_sql(monkeypatch)
    assert "LEFT JOIN user u ON i.user_id = u.id" in sql
    assert "location_public" in sql


def test_nearby_anonymous_viewer_only_public(monkeypatch):
    """规则 4：未登录查看者只看到 location_public=1 的物品。"""
    sql, params = _capture_sql(monkeypatch)
    # 无 viewer 分支：条件为 COALESCE(u.location_public, 0) = 1，且不带 i.user_id 例外
    assert "COALESCE(u.location_public, 0) = 1" in sql
    assert "i.user_id = %s" not in sql
    assert params[-1] == 50  # 末位为 LIMIT，说明未追加 viewer_user_id


def test_nearby_logged_in_viewer_exempts_own_items(monkeypatch):
    """规则 3：登录查看者能看到自己的物品，即使自己未公开位置。"""
    sql, params = _capture_sql(monkeypatch, viewer_user_id=7)
    assert "(COALESCE(u.location_public, 0) = 1 OR i.user_id = %s)" in sql
    # viewer_user_id 应作为参数下发，且在 LIMIT 之前
    assert 7 in params
    assert params[-2] == 7


def test_nearby_privacy_condition_precedes_limit(monkeypatch):
    """隐私条件必须位于 ORDER BY / LIMIT 之前的 WHERE 子句中。"""
    sql, _ = _capture_sql(monkeypatch, viewer_user_id=7)
    assert sql.index("location_public") < sql.index("LIMIT")


def test_nearby_invalid_coordinates_short_circuit(monkeypatch):
    """坐标非法时直接返回空列表，不查库。"""
    cursor = _patch(monkeypatch)
    assert query_service.find_nearby_items("abc", 116.4) == []
    assert cursor.executed == []


def test_nearby_keyword_combines_with_privacy(monkeypatch):
    """关键词与隐私条件可叠加，参数顺序正确。"""
    sql, params = _capture_sql(monkeypatch, keyword="自行车", viewer_user_id=9)
    assert "(i.title LIKE %s OR i.description LIKE %s)" in sql
    # 参数顺序：status, lat, lat, lng, lng, kw, kw, viewer_user_id, limit
    assert params[5] == "%自行车%" and params[6] == "%自行车%"
    assert params[7] == 9
    assert params[-1] == 50
