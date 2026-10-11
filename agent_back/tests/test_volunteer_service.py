"""volunteer_service 单元测试。"""
import pytest
from conftest import FakeCursor, make_connection

from app.services import volunteer_service


def _patch_db(monkeypatch, rows, rowcount=1, lastrowid=10):
    cursor = FakeCursor(rows=rows, rowcount=rowcount, lastrowid=lastrowid)
    monkeypatch.setattr("app.services.volunteer_service.connection", make_connection(cursor))
    return cursor


def test_create_task_without_volunteer_pending_and_push(monkeypatch):
    pushed = {}
    monkeypatch.setattr(
        "app.services.volunteer_service.notify_service.push_volunteer_task",
        lambda task_id, item_title, note="": pushed.setdefault("called", (task_id, item_title, note)),
    )
    _patch_db(monkeypatch, [{"title": "美的电饭煲"}], lastrowid=77)
    result = volunteer_service.create_task("EX-001", requester_id=1, item_id=3, note="腿脚不便")
    assert result["task_id"] == 77
    assert result["status"] == "pending"
    assert pushed["called"][0] == 77


def test_create_task_with_volunteer_accepted_no_push(monkeypatch):
    pushed = {}
    monkeypatch.setattr(
        "app.services.volunteer_service.notify_service.push_volunteer_task",
        lambda task_id, item_title, note="": pushed.setdefault("called", True),
    )
    _patch_db(monkeypatch, [{"title": "椅子"}], lastrowid=88)
    result = volunteer_service.create_task(
        "EX-002", requester_id=2, item_id=4, volunteer_id=10
    )
    assert result["status"] == "accepted"
    assert "called" not in pushed


def test_list_tasks(monkeypatch):
    rows = [
        {"id": 1, "requester_id": 1, "volunteer_id": None, "status": "pending", "item_title": "A"},
        {"id": 2, "requester_id": 2, "volunteer_id": 1, "status": "done", "item_title": "B"},
    ]
    _patch_db(monkeypatch, rows)
    tasks = volunteer_service.list_tasks(1)
    assert len(tasks) == 2


def test_update_status_illegal_transition(monkeypatch):
    _patch_db(monkeypatch, [{"status": "done", "volunteer_id": 5}])
    with pytest.raises(ValueError, match="不能从 done 变更为 cancelled"):
        volunteer_service.update_status(1, volunteer_id=5, status="cancelled")


def test_update_status_accepted_sets_volunteer(monkeypatch):
    _patch_db(monkeypatch, [{"status": "pending", "volunteer_id": None}])
    result = volunteer_service.update_status(1, volunteer_id=5, status="accepted")
    assert result["status"] == "accepted"
