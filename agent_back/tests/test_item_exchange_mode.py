"""发布物品「交易方式 + 转让价 + 成色 / 原价」单元测试（数据库 mock，不连真实 MySQL）。

对应需求 1（增加「低价转让」交易方式）的后端部分：
- `POST /items` 接收 exchange_mode(1/2/3) / price / condition_level / original_price
- mode=3（低价转让）时 price 必填且落在 0.01 - 99999
- mode≠3 时 price 一律归 0（免费送 / 交换不带金额）
- `GET /items/{id}` 整形：只有 mode=3 才透出真实 price，其余归 0

设计约定与 test_user_orders.py 一致：SQL 走 conftest 的 FakeCursor，
断言集中在「SQL 形状 + 参数 + 返回结构」；真实库端到端另在《验证清单》中列出。
"""
import io

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile as StarletteUploadFile

from conftest import FakeCursor, make_connection

from app.api.v1 import item as item_api

USER_ID = 7
CATEGORY_ID = 3

# JPEG 文件头（FF D8 FF）+ 填充字节：足以通过魔数校验，不必是完整图片
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32


class _BackgroundTasks:
    """BackgroundTasks 替身：记录被排入的任务，不真正执行（避免跑 360° 生成）。"""

    def __init__(self):
        self.tasks: list = []

    def add_task(self, func, *args, **kwargs):
        self.tasks.append((func, args, kwargs))


class _Settings:
    """settings 替身：把图片落到 pytest 的 tmp_path，不污染真实 uploads/ 目录。"""

    def __init__(self, upload_dir):
        self.upload_dir = upload_dir
        self.api_prefix = "/api/v1"


def _patch(monkeypatch, tmp_path, rows=None, lastrowid=101):
    cursor = FakeCursor(rows=rows if rows is not None else [{"id": CATEGORY_ID}], lastrowid=lastrowid)
    monkeypatch.setattr(item_api, "connection", make_connection(cursor))
    monkeypatch.setattr(item_api, "settings", _Settings(str(tmp_path)))
    return cursor


def _image():
    return StarletteUploadFile(file=io.BytesIO(JPEG_BYTES), filename="a.jpg")


def _publish(monkeypatch, tmp_path, **overrides):
    """调用 create_item 的通用壳：默认一个合法的「免费送」发布。"""
    params = {
        "title": "九成新儿童自行车",
        "description": "轻微划痕，后座可拆卸",
        "category_id": CATEGORY_ID,
        "expected_exchange": "",
        "contact": "13800000000",
        "exchange_mode": 1,
        "price": "",
        "condition_level": 0,
        "original_price": "",
        "image": _image(),
        "user_id": USER_ID,
    }
    params.update(overrides)
    kwargs = {
        "background_tasks": _BackgroundTasks(),
        "title": params["title"],
        "description": params["description"],
        "category_id": params["category_id"],
        "expected_exchange": params["expected_exchange"],
        "contact": params["contact"],
        "exchange_mode": params["exchange_mode"],
        "price": params["price"],
        "condition_level": params["condition_level"],
        "original_price": params["original_price"],
        "image": params["image"],
        "user_id": params["user_id"],
    }
    cursor = _patch(monkeypatch, tmp_path)
    resp = item_api.create_item(**kwargs)
    return cursor, resp


def _item_insert(cursor):
    """取 create_item 的 INSERT INTO item 语句与参数。"""
    for sql, params in cursor.executed:
        if sql.startswith("INSERT INTO item"):
            return sql, params
    raise AssertionError("没有执行 INSERT INTO item")


# ============================================================
# 三种交易方式：写入 exchange_mode / price
# ============================================================
def test_publish_give_mode_writes_mode_1_and_zero_price(monkeypatch, tmp_path):
    """免费送（1）：price 归 0，expected_item 为空写 NULL。"""
    cursor, resp = _publish(monkeypatch, tmp_path, exchange_mode=1, price="")

    assert resp["code"] == 0
    assert resp["data"] == {"id": 101, "status": 4}
    sql, params = _item_insert(cursor)
    assert "exchange_mode, price, condition_level, original_price" in sql
    # params: user_id, category_id, title, description, images, expected_item, contact,
    #         exchange_mode, price, condition_level, original_price
    assert params[7] == 1
    assert str(params[8]) == "0.00"
    assert params[5] is None


def test_publish_swap_mode_ignores_price(monkeypatch, tmp_path):
    """交换（2）：即使前端传了 price 也归 0；expect_item 正常落库。"""
    cursor, _ = _publish(
        monkeypatch, tmp_path, exchange_mode=2, price="999", expected_exchange="绘本、儿童玩具"
    )

    _, params = _item_insert(cursor)
    assert params[7] == 2
    assert str(params[8]) == "0.00"
    assert params[5] == "绘本、儿童玩具"


def test_publish_sell_mode_writes_price(monkeypatch, tmp_path):
    """低价转让（3）：price 落库并量化到 2 位小数。"""
    cursor, _ = _publish(monkeypatch, tmp_path, exchange_mode=3, price="88.5")

    _, params = _item_insert(cursor)
    assert params[7] == 3
    assert str(params[8]) == "88.50"


def test_publish_condition_and_original_price_written(monkeypatch, tmp_path):
    """成色 / 原价（可选）写入 item：估价页回填依赖这两个字段。"""
    cursor, _ = _publish(
        monkeypatch, tmp_path, exchange_mode=1, condition_level=4, original_price="1200"
    )

    _, params = _item_insert(cursor)
    assert params[9] == 4
    assert str(params[10]) == "1200.00"


# ============================================================
# 价格校验
# ============================================================
def test_publish_sell_without_price_400(monkeypatch, tmp_path):
    """低价转让不填转让价：400，且不下发任何 SQL（校验在落库之前）。"""
    cursor = _patch(monkeypatch, tmp_path)
    with pytest.raises(HTTPException) as exc:
        item_api.create_item(
            background_tasks=_BackgroundTasks(),
            title="台灯", description="九成新", category_id=CATEGORY_ID,
            expected_exchange="", contact="13800000000",
            exchange_mode=3, price="", condition_level=0, original_price="",
            image=_image(), user_id=USER_ID,
        )

    assert exc.value.status_code == 400
    assert "转让价" in exc.value.detail
    assert cursor.executed == []


@pytest.mark.parametrize(
    "price,expected_hint",
    [
        ("0", "0.01 - 99999"),
        ("-5", "0.01 - 99999"),
        ("100000", "0.01 - 99999"),
        ("abc", "必须是数字"),
    ],
)
def test_publish_sell_price_out_of_range_400(monkeypatch, tmp_path, price, expected_hint):
    """转让价越界 / 非数字：400 且中文提示。"""
    _patch(monkeypatch, tmp_path)
    with pytest.raises(HTTPException) as exc:
        item_api.create_item(
            background_tasks=_BackgroundTasks(),
            title="台灯", description="九成新", category_id=CATEGORY_ID,
            expected_exchange="", contact="13800000000",
            exchange_mode=3, price=price, condition_level=0, original_price="",
            image=_image(), user_id=USER_ID,
        )

    assert exc.value.status_code == 400
    assert expected_hint in exc.value.detail


def test_publish_sell_price_boundary_ok(monkeypatch, tmp_path):
    """边界值 0.01 与 99999 都合法。"""
    cursor, _ = _publish(monkeypatch, tmp_path, exchange_mode=3, price="0.01")
    _, params = _item_insert(cursor)
    assert str(params[8]) == "0.01"

    cursor2, _ = _publish(monkeypatch, tmp_path, exchange_mode=3, price="99999")
    _, params2 = _item_insert(cursor2)
    assert str(params2[8]) == "99999.00"


def test_publish_invalid_exchange_mode_400(monkeypatch, tmp_path):
    """exchange_mode 只能是 1/2/3；9 直接 400。"""
    _patch(monkeypatch, tmp_path)
    with pytest.raises(HTTPException) as exc:
        item_api.create_item(
            background_tasks=_BackgroundTasks(),
            title="台灯", description="九成新", category_id=CATEGORY_ID,
            expected_exchange="", contact="13800000000",
            exchange_mode=9, price="", condition_level=0, original_price="",
            image=_image(), user_id=USER_ID,
        )

    assert exc.value.status_code == 400
    assert "交易方式" in exc.value.detail


def test_publish_invalid_condition_level_400(monkeypatch, tmp_path):
    """成色只能是 0（未填）或 1-5；6 直接 400。"""
    _patch(monkeypatch, tmp_path)
    with pytest.raises(HTTPException) as exc:
        item_api.create_item(
            background_tasks=_BackgroundTasks(),
            title="台灯", description="九成新", category_id=CATEGORY_ID,
            expected_exchange="", contact="13800000000",
            exchange_mode=1, price="", condition_level=6, original_price="",
            image=_image(), user_id=USER_ID,
        )

    assert exc.value.status_code == 400
    assert "成色等级" in exc.value.detail


# ============================================================
# 详情接口整形：只有低价转让才透出 price
# ============================================================
def test_get_item_hides_price_for_give_and_swap(monkeypatch):
    """免费送 / 交换：即便库里有历史脏 price，也归 0 再返回。"""
    for mode in (1, 2):
        _patch(monkeypatch, "/tmp", rows=[{
            "id": 1, "title": "台灯", "description": "d",
            "exchange_mode": mode, "price": "50.00",
            "panorama_status": "none", "panorama_views": None,
        }])
        data = item_api.get_item(1)["data"]
        assert data["exchange_mode"] == mode
        assert data["price"] == 0.0


def test_get_item_keeps_price_for_sell(monkeypatch):
    """低价转让：price 透出为 float。"""
    _patch(monkeypatch, "/tmp", rows=[{
        "id": 2, "title": "台灯", "description": "d",
        "exchange_mode": 3, "price": "88.50",
        "panorama_status": "none", "panorama_views": None,
    }])
    data = item_api.get_item(2)["data"]
    assert data["exchange_mode"] == 3
    assert data["price"] == 88.5


def test_get_item_exchange_mode_fallback(monkeypatch):
    """exchange_mode 缺失 / 非法：回落 1（免费送），price 归 0，不 500。"""
    _patch(monkeypatch, "/tmp", rows=[{
        "id": 3, "title": "台灯", "description": "d",
        "exchange_mode": None, "price": "9.00",
        "panorama_status": "none", "panorama_views": None,
    }])
    data = item_api.get_item(3)["data"]
    assert data["exchange_mode"] == 1
    assert data["price"] == 0.0
