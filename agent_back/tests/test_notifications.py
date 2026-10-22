"""通知设置接口单元测试（GET/PUT /user/notifications，数据库 mock）。"""
import pytest
from fastapi import HTTPException

from conftest import FakeCursor, make_connection

from app.api.v1 import user as user_api
from app.schemas.user import NotificationUpdate

USER_ID = 7
ALL_OFF = {"notify_message": 0, "notify_exchange": 0, "notify_system": 0}
ALL_ON = {"notify_message": 1, "notify_exchange": 1, "notify_system": 1}


def _patch(monkeypatch, rows=None, rowcount=1):
    cursor = FakeCursor(rows=rows, rowcount=rowcount)
    monkeypatch.setattr(user_api, "connection", make_connection(cursor))
    return cursor


def test_get_notifications_returns_three_flags(monkeypatch):
    """GET 返回三个开关，且统一转成 0/1 整数。"""
    _patch(monkeypatch, rows=[{"notify_message": 1, "notify_exchange": 0, "notify_system": 1}])
    resp = user_api.get_notifications(USER_ID)
    assert resp["code"] == 0
    assert set(resp["data"].keys()) == {"notify_message", "notify_exchange", "notify_system"}
    assert resp["data"] == {"notify_message": 1, "notify_exchange": 0, "notify_system": 1}


def test_update_notifications_partial_only_writes_given_field(monkeypatch):
    """只传一个字段时，UPDATE 只写该列，不覆盖其他开关。"""
    cursor = _patch(monkeypatch, rows=[{"notify_message": 0, "notify_exchange": 1, "notify_system": 1}])
    resp = user_api.update_notifications(NotificationUpdate(notify_message=0), USER_ID)

    assert resp["data"] == {"notify_message": 0, "notify_exchange": 1, "notify_system": 1}
    update_sql, params = cursor.executed[0]
    assert update_sql == "UPDATE user SET notify_message=%s WHERE id=%s"
    assert list(params) == [0, USER_ID]


def test_update_notifications_empty_body_rejected(monkeypatch):
    """没有任何字段时直接 400，不触库。"""
    cursor = _patch(monkeypatch, rows=[])
    with pytest.raises(HTTPException) as exc:
        user_api.update_notifications(NotificationUpdate(), USER_ID)
    assert exc.value.status_code == 400
    assert "没有需要更新的字段" in exc.value.detail
    assert cursor.executed == []
