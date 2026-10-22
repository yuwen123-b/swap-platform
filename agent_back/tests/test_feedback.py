"""意见反馈接口单元测试（POST /user/feedback，写入 user_feedback 表，数据库 mock）。"""
import pytest
from fastapi import HTTPException

from conftest import FakeCursor, make_connection

from app.api.v1 import user as user_api
from app.schemas.user import UserFeedbackCreate

USER_ID = 7


def _patch(monkeypatch, rows=None, rowcount=1, lastrowid=101):
    cursor = FakeCursor(rows=rows, rowcount=rowcount, lastrowid=lastrowid)
    monkeypatch.setattr(user_api, "connection", make_connection(cursor))
    return cursor


def test_create_feedback_success_returns_id(monkeypatch):
    """成功写入 user_feedback，user_id 取自登录态，返回新记录 ID。"""
    cursor = _patch(monkeypatch, lastrowid=101)
    resp = user_api.create_user_feedback(
        UserFeedbackCreate(content="希望增加夜间模式", contact="138****8888"),
        USER_ID,
    )

    assert resp["code"] == 0
    assert resp["data"] == {"success": True, "feedback_id": 101}
    insert_sql, params = cursor.executed[0]
    assert "INSERT INTO user_feedback" in insert_sql
    assert params == (USER_ID, "希望增加夜间模式", "138****8888")


def test_create_feedback_empty_content_rejected(monkeypatch):
    """内容为空白 -> 400，不触库；联系方式留空应归一为 NULL。"""
    cursor = _patch(monkeypatch, rows=[])
    with pytest.raises(HTTPException) as exc:
        user_api.create_user_feedback(UserFeedbackCreate(content="   "), USER_ID)
    assert exc.value.status_code == 400
    assert "反馈内容不能为空" in exc.value.detail
    assert cursor.executed == []

    # 正常内容 + 不传联系方式：contact 归一为 None 写入
    cursor2 = _patch(monkeypatch, lastrowid=102)
    user_api.create_user_feedback(UserFeedbackCreate(content="很满意"), USER_ID)
    _sql, params2 = cursor2.executed[0]
    assert params2 == (USER_ID, "很满意", None)
