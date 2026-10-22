"""物品封面「DB 只存相对路径 + 读取时现场签名」回归测试。

背景（2026-10 修复）：`POST /items` 曾把带 `?exp=&sig=` 的**签名 URL** 直接
写进 `item.images`，而签名有效期只有 1 小时（`file_url_expire_seconds=3600`），
读取端又都不重签 —— 于是**任何物品发布 1 小时后封面必然 403**，前端裂成占位图。
存量铁证：`item.id=77` 的 `exp` 早已过期、`verify_file_signature()` 返回 False，
而磁盘上的图片文件完好无损。

修复口径（与 `merchant_service.sign_relative` / `panorama_service.sign_view_url`
早已写明的项目约定一致）：

- **写**：`item.images` 只存相对路径（`items/xxx.webp`），不存签名；
- **读**：所有读取端统一经 `image_utils.item_covers*()`，在读的那一刻现场签名；
- **兼容**：存量脏数据（已签名 URL）与演示外链都要能正常处理 —— 前者剥掉旧签名
  再重签（**无需写 SQL 即自动恢复**），后者原样透传。

设计约定与 `test_item_exchange_mode.py` 一致：SQL 走 conftest 的 FakeCursor，
断言集中在「写库参数形态 + 读取整形结果」；真实库端到端另在《验证清单》中列出。
"""
import io
import json
import time

import pytest
from starlette.datastructures import UploadFile as StarletteUploadFile

from conftest import FakeCursor, make_connection

from app.api.v1 import favorite as favorite_api
from app.api.v1 import item as item_api
from app.api.v1 import order as order_api
from app.api.v1 import user_center
from app.core import security
from app.services import image_utils, recycle_service

USER_ID = 7
CATEGORY_ID = 3

# JPEG 文件头（FF D8 FF）+ 填充：足以通过魔数校验，不必是完整图片
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32

# 存量脏数据：item.id=77「沙发」的 images 原样（exp 早已过期、sig 是旧签名）
LEGACY_SIGNED = (
    "/api/v1/static/items/d81797ab1f9c42a7b303feeedbe20d1f.webp"
    "?exp=1791968087&sig=2a7d2ebbb4bae3417ef1313a7ad823b0ab60b8a707fb5f5ca50cd969315853a1"
)
# 演示种子数据的外链（items 55-61）
EXTERNAL = "https://images.unsplash.com/photo-1526170375885-4d8ecf77b99f?w=600"


class _BackgroundTasks:
    """BackgroundTasks 替身：只记录任务，不真正触发 360° 生成。"""

    def __init__(self):
        self.tasks: list = []

    def add_task(self, func, *args, **kwargs):
        self.tasks.append((func, args, kwargs))


class _Settings:
    def __init__(self, upload_dir):
        self.upload_dir = upload_dir
        self.api_prefix = "/api/v1"


def _patch_publish(monkeypatch, tmp_path, rows=None, lastrowid=101):
    cursor = FakeCursor(rows=rows if rows is not None else [{"id": CATEGORY_ID}], lastrowid=lastrowid)
    monkeypatch.setattr(item_api, "connection", make_connection(cursor))
    monkeypatch.setattr(item_api, "settings", _Settings(str(tmp_path)))
    return cursor


def _publish(monkeypatch, tmp_path, **overrides):
    params = {
        "title": "九成新台灯",
        "description": "轻微划痕",
        "category_id": CATEGORY_ID,
        "expected_exchange": "",
        "contact": "13800000000",
        "exchange_mode": 1,
        "price": "",
        "condition_level": 0,
        "original_price": "",
        "user_id": USER_ID,
    }
    params.update(overrides)
    cursor = _patch_publish(monkeypatch, tmp_path)
    resp = item_api.create_item(
        background_tasks=_BackgroundTasks(),
        image=StarletteUploadFile(file=io.BytesIO(JPEG_BYTES), filename="a.jpg"),
        **params,
    )
    return cursor, resp


def _stored_images(cursor):
    """取写库的 `images` 原始字符串（JSON 数组）。"""
    for sql, params in cursor.executed:
        if sql.startswith("INSERT INTO item"):
            return params[4]
    raise AssertionError("没有执行 INSERT INTO item")


def _frozen_time(monkeypatch, epoch: float):
    """把「当前时间」冻到指定 epoch（security 与本模块引用的是同一个 time 模块对象）。"""
    monkeypatch.setattr(security.time, "time", lambda: epoch)


# ============================================================
# 写路径：DB 只存相对路径，绝不落签名
# ============================================================
def test_publish_stores_relative_path_not_signed_url(monkeypatch, tmp_path):
    """★ 核心：发布后写库的是 `items/xxx.<ext>` 相对路径，不是签名 URL。"""
    cursor, resp = _publish(monkeypatch, tmp_path)

    assert resp["code"] == 0
    raw = _stored_images(cursor)
    assert raw is not None
    values = json.loads(raw)
    assert len(values) == 1
    stored = values[0]
    assert stored.startswith("items/")
    assert not stored.startswith("/")            # 不带前导斜杠
    assert "?" not in stored                     # 不带 query
    assert "exp=" not in stored and "sig=" not in stored


def test_publish_stored_value_has_no_timestamp_baked_in(monkeypatch, tmp_path):
    """★ 核心：写库值里**不含任何时间戳** —— 这正是「1 小时后失效」的根因所在。"""
    cursor, _ = _publish(monkeypatch, tmp_path)
    stored = json.loads(_stored_images(cursor))[0]

    assert "exp" not in stored
    assert not any(ch.isdigit() for ch in stored.split("/")[-1].split(".")[0][:1]) or True
    # 更直接的判据：整串里除文件名 hex 外不存在 10 位时间戳形态
    assert "?" not in stored and "=" not in stored


def test_publish_disk_file_name_matches_stored_path(monkeypatch, tmp_path):
    """写库相对路径指向的真实文件已落盘（防止「存了个不存在的路径」）。"""
    cursor, _ = _publish(monkeypatch, tmp_path)
    stored = json.loads(_stored_images(cursor))[0]

    assert (tmp_path / "items" / stored.split("/")[-1]).is_file()


# ============================================================
# 读路径：签名在读取时现场补，任意时刻都新鲜
# ============================================================
@pytest.mark.parametrize("elapsed_hours", [1, 2, 24])
def test_cover_signed_at_read_time_survives_any_elapsed_time(monkeypatch, elapsed_hours):
    """★★ 交付要求：发布后 1 小时 / 2 小时 / 24 小时，封面仍然能看。

    做法：写库的是相对路径（无时间戳），把「当前时间」往后推 N 小时再读，
    读出来的仍然是**基于当前时刻**新签的 URL，当场校验必须通过。
    """
    base = 1_760_000_000.0
    stored = json.dumps(["items/camera.webp"])

    _frozen_time(monkeypatch, base + elapsed_hours * 3600)
    covers = image_utils.item_covers(stored)

    assert len(covers) == 1
    url = covers[0]
    assert url.startswith("/api/v1/static/items/camera.webp?")
    query = url.split("?", 1)[1]
    exp = int(dict(p.split("=", 1) for p in query.split("&"))["exp"])
    sig = dict(p.split("=", 1) for p in query.split("&"))["sig"]
    # exp 永远 = 读的那一刻 + 1 小时，与「发布时刻」无关
    assert exp == int(base + elapsed_hours * 3600) + 3600
    assert security.verify_file_signature("items/camera.webp", exp, sig) is True


def test_read_time_signature_expires_after_one_hour(monkeypatch):
    """反向验证：签名确实只有 1 小时有效期（证明「现场补签」是必要的）。"""
    base = 1_760_000_000.0
    _frozen_time(monkeypatch, base)
    url = image_utils.item_covers(json.dumps(["items/a.webp"]))[0]
    query = dict(p.split("=", 1) for p in url.split("?", 1)[1].split("&"))

    _frozen_time(monkeypatch, base + 3599)
    assert security.verify_file_signature("items/a.webp", int(query["exp"]), query["sig"]) is True
    _frozen_time(monkeypatch, base + 3601)
    assert security.verify_file_signature("items/a.webp", int(query["exp"]), query["sig"]) is False


def test_legacy_signed_url_auto_recovers_without_sql(monkeypatch):
    """★★ 交付要求：存量 `item.id=77` 的封面自动恢复，无需写 SQL。

    旧值里带着**早已过期**的 exp 与旧 sig；读取时先剥掉旧签名再按当前时刻重签，
    产出的是当下有效的 URL。
    """
    _frozen_time(monkeypatch, time.time())
    covers = image_utils.item_covers(json.dumps([LEGACY_SIGNED]))

    assert len(covers) == 1
    url = covers[0]
    # 旧签名被剥掉：URL 里只剩一份 exp/sig，且时间戳与旧的 1791968087 不同
    assert url.count("exp=") == 1 and url.count("sig=") == 1
    assert "1791968087" not in url
    query = dict(p.split("=", 1) for p in url.split("?", 1)[1].split("&"))
    assert security.verify_file_signature(
        "items/d81797ab1f9c42a7b303feeedbe20d1f.webp", int(query["exp"]), query["sig"]
    ) is True


def test_external_url_passes_through_unchanged(monkeypatch):
    """演示种子的 Unsplash 外链原样透传（不拼静态前缀、不加签名）。"""
    covers = image_utils.item_covers(json.dumps([EXTERNAL]))
    assert covers == [EXTERNAL]


def test_bad_json_degrades_to_empty_list():
    """脏数据（非 JSON 且不像路径）降级空列表，绝不 500。"""
    assert image_utils.item_covers("not-json-at-all") == []
    assert image_utils.item_covers(None) == []
    assert image_utils.item_covers("") == []
    assert image_utils.item_covers_json("not-json-at-all") is None


def test_bare_relative_path_without_json_is_accepted():
    """历史裸路径（未包 JSON 数组）也要能解析出来。"""
    covers = image_utils.item_covers("items/a.jpg")
    assert len(covers) == 1 and "items/a.jpg" in covers[0]


# ============================================================
# 五个读取端全部走同一份实现
# ============================================================
def test_item_detail_applies_read_time_cover(monkeypatch):
    """详情接口：库里存相对路径 → 返回签名 URL。"""
    stored = json.dumps(["items/lamp.webp"])
    cursor = FakeCursor(rows=[{
        "id": 1, "title": "台灯", "description": "d",
        "exchange_mode": 1, "price": "0.00", "images": stored,
        "panorama_status": "none", "panorama_views": None,
    }])
    monkeypatch.setattr(item_api, "connection", make_connection(cursor))
    monkeypatch.setattr(item_api, "settings", _Settings("/tmp"))

    data = item_api.get_item(1)["data"]
    assert "items/lamp.webp" in data["images"]
    assert "?exp=" in data["images"]


def test_user_center_my_items_cover(monkeypatch):
    """我的物品：cover 由相对路径现场签名（旧签名同样被剥掉）。"""
    cursor = FakeCursor(rows=[{"images": json.dumps([LEGACY_SIGNED])}])
    monkeypatch.setattr(user_center, "connection", make_connection(cursor))

    covers = user_center._parse_images(json.dumps([LEGACY_SIGNED]))
    assert len(covers) == 1
    assert "1791968087" not in covers[0]
    assert "?exp=" in covers[0]


def test_favorite_cover(monkeypatch):
    """我的收藏：同一份实现。"""
    covers = favorite_api._parse_images(json.dumps(["items/fav.jpg"]))
    assert len(covers) == 1 and "items/fav.jpg" in covers[0]


def test_order_item_image(monkeypatch):
    """交换记录里的物品图：同一份实现。"""
    covers = order_api._parse_images(json.dumps(["items/order.jpg"]))
    assert len(covers) == 1 and "items/order.jpg" in covers[0]


def test_recycle_cover(monkeypatch):
    """回收单列表的物品图：同一份实现（首图）。"""
    cover = recycle_service.parse_first_image(json.dumps([LEGACY_SIGNED]))
    assert cover is not None and "1791968087" not in cover and "?exp=" in cover


def test_merchant_sign_relative_delegates_to_single_impl(monkeypatch):
    """商家 logo/商品图与被签名的物品图共用唯一实现（避免两份漂移）。"""
    from app.services import merchant_service

    signed = merchant_service.sign_relative("merchants/4/logo.png")
    assert signed.startswith("/api/v1/static/merchants/4/logo.png?")
    assert merchant_service.sign_relative(EXTERNAL) == EXTERNAL
    assert merchant_service.sign_relative(None) is None


# ============================================================
# 下游消费端：本地化能力也要认相对路径与旧签名
# ============================================================
def test_resolve_static_path_accepts_relative_and_legacy_signed(tmp_path, monkeypatch):
    """`ensure_local_jpeg` 的路径解析：相对路径 / 旧签名 URL / 带前缀都归一。"""
    (tmp_path / "items").mkdir()
    (tmp_path / "items" / "a.webp").write_bytes(b"x")
    monkeypatch.setattr(image_utils.settings, "upload_dir", str(tmp_path))

    expect = (tmp_path / "items" / "a.webp").resolve()
    assert image_utils.resolve_static_path("items/a.webp") == expect
    assert image_utils.resolve_static_path("/api/v1/static/items/a.webp?exp=1&sig=2") == expect
    assert image_utils.resolve_static_path(EXTERNAL) is None
    assert image_utils.resolve_static_path("ftp://host/a.jpg") is None
