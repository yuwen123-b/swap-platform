import json
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile

from app.core.config import settings
from app.core.image_check import detect_image_ext
from app.core.response import success
from app.core.security import get_current_user_id, get_optional_user_id
from app.db.pool import connection
from app.schemas.recycle import RecycleSubmitRequest
from app.services import recycle_service
from app.services.image_utils import item_covers_json
from app.services.item_query_service import _haversine_km
from app.services.panorama_service import sign_view_url
from app.services.three_d_service import is_enabled as model_3d_enabled
from app.services.three_d_service import sign_model_url

router = APIRouter()

MAX_IMAGE_SIZE = 5 * 1024 * 1024

# 发布字段长度限制：与前端、DB 列宽保持一致
MAX_TITLE_LEN = 50
MAX_DESCRIPTION_LEN = 500
MAX_CONTACT_LEN = 100

# ============================================================
# 交易方式（与 `item.exchange_mode` 列注释同口径，**不翻转**）
#   1=免费送 2=等价互换 3=低价转让 4=平台回收（二期新增）
# 前端文案：免费送 / 交换 / 低价转让 / 交给平台回收
# ⚠️ mode=4 **不走 order 流程**：物品交给平台后立即得积分并下架，
#    order.create_order 里有显式断言拒绝 mode=4（见 order.py 的映射表注释），
#    这里与映射表两侧都要维护，避免后续误以为它会进订单。
# ============================================================
EXCHANGE_MODES = (1, 2, 3, 4)
EXCHANGE_MODE_GIVE = 1
EXCHANGE_MODE_SWAP = 2
EXCHANGE_MODE_SELL = 3
EXCHANGE_MODE_RECYCLE = 4

# 低价转让价区间（DECIMAL(10,2)）：与产品口径一致
MIN_PRICE = Decimal("0.01")
MAX_PRICE = Decimal("99999")
# 原价区间：仅作展示参考，宽松上限避免误伤
MIN_ORIGINAL_PRICE = Decimal("0")
MAX_ORIGINAL_PRICE = Decimal("9999999.99")

# 成色 1~5；0 表示「未填写」（DB 列默认 0，历史发布数据也是 0）
MIN_CONDITION = 1
MAX_CONDITION = 5

# 距离排序最多参与排序的物品行数：距离需在 Python 侧计算，无法交给 SQL 排序，
# 因此限制扫描行数，避免超大表一次性全表取回。
DISTANCE_SORT_SCAN_LIMIT = 500


def _parse_money(raw, *, low: Decimal, high: Decimal, label: str) -> Decimal:
    """把 Form 传来的金额字符串安全解析为 DECIMAL(10,2)。

    空串 / None 视为「未填写」，返回 Decimal('0.00')（由调用方决定是否必填）。
    解析失败或超出区间一律 400 + 中文提示：金额是钱，宁可拒绝也不静默改成 0。
    """
    if raw is None or str(raw).strip() == "":
        return Decimal("0.00")
    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        raise HTTPException(400, f"{label}必须是数字") from None
    if value.is_nan() or value.is_infinite():
        raise HTTPException(400, f"{label}必须是数字")
    value = value.quantize(Decimal("0.01"))
    if value < low or value > high:
        raise HTTPException(400, f"{label}需在 {low} - {high} 元之间")
    return value



def _coerce_coord(value) -> float | None:
    """把 DECIMAL/字符串坐标安全转 float；None 或非法值一律返回 None。"""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_saved_coordinates(user_id: int) -> tuple[float, float] | None:
    """读取用户在个人中心保存的坐标；未设置（或为 0,0 占位）时返回 None。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT latitude, longitude FROM user WHERE id=%s LIMIT 1", (user_id,))
            row = cursor.fetchone()
    if not row:
        return None
    lat = _coerce_coord(row.get("latitude"))
    lng = _coerce_coord(row.get("longitude"))
    if lat is None or lng is None or (lat == 0 and lng == 0):
        return None
    return lat, lng


def _list_items_by_distance(
    conditions: list[str],
    params: list,
    page: int,
    size: int,
    latitude: float | None,
    longitude: float | None,
    viewer_id: int | None,
):
    """「离我最近」：按到参照点的球面距离升序返回物品列表。

    参照点优先级：显式查询参数 latitude/longitude > 登录用户已保存的位置。
    距离取物品自身坐标（item.latitude/longitude），物品未落坐标时回退到其所有者的位置
    ——发布接口并不写入 item 坐标，因此实际数据依赖所有者在下设置的位置。
    距离算法复用 item_query_service 的 Haversine，不另写一份。

    隐私规则（与 find_nearby_items 一致）：仅所有者已公开位置
    （user.location_public=1）或查看者自己的物品参与距离排序；其余物品保持默认
    顺序排在列表末尾，且不返回 distance_km，避免借「排序」泄露未公开位置。
    """
    lat = _coerce_coord(latitude)
    lng = _coerce_coord(longitude)
    if lat is None or lng is None:
        if viewer_id is None:
            raise HTTPException(status_code=400, detail="请先登录并在个人中心设置您的位置")
        saved = _load_saved_coordinates(viewer_id)
        if saved is None:
            # 已登录但未设置位置：不作为错误返回，给前端可识别的引导标记 + 明确提示
            return success(
                {
                    "items": [],
                    "total": 0,
                    "page": page,
                    "size": size,
                    "distance_sorted": True,
                    "nearby_count": 0,
                    "need_location": True,
                },
                "请先在个人中心设置您的位置",
            )
        lat, lng = saved

    where = " AND ".join(conditions)
    sql = f"""SELECT i.*, c.name AS category_name,
                     u.latitude  AS owner_latitude,
                     u.longitude AS owner_longitude,
                     COALESCE(u.location_public, 0) AS owner_location_public
              FROM item i
              LEFT JOIN category c ON i.category_id = c.id
              LEFT JOIN user u ON i.user_id = u.id
              WHERE {where}
              ORDER BY i.id DESC
              LIMIT %s"""
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params + [DISTANCE_SORT_SCAN_LIMIT])
            rows = cursor.fetchall()

    located: list = []
    unlocated: list = []
    for row in rows:
        item_lat = _coerce_coord(row.get("latitude"))
        item_lng = _coerce_coord(row.get("longitude"))
        if item_lat is None or item_lng is None:
            item_lat = _coerce_coord(row.get("owner_latitude"))
            item_lng = _coerce_coord(row.get("owner_longitude"))
        owner_public = int(row.get("owner_location_public") or 0) == 1
        if item_lat is not None and item_lng is not None and (owner_public or row.get("user_id") == viewer_id):
            row["distance_km"] = round(_haversine_km(lat, lng, item_lat, item_lng), 2)
            located.append(row)
        else:
            unlocated.append(row)
    located.sort(key=lambda r: r["distance_km"])

    ordered = located + unlocated
    offset = (page - 1) * size
    page_rows = ordered[offset:offset + size]
    # 列表不透出 panorama_views 大 JSON（仅保留 panorama_status 供卡片 360° 角标）
    for it in page_rows:
        it["panorama_views"] = None
        # 封面读取时现场签名（DB 只存相对路径，落库签名 1 小时就过期）
        it["images"] = item_covers_json(it.get("images"))
    return success(
        {
            "items": page_rows,
            "total": len(ordered),
            "page": page,
            "size": size,
            "distance_sorted": True,
            "nearby_count": len(located),
        },
    )


@router.get("")
def list_items(page: int = Query(1, ge=1), size: int = Query(12, ge=1, le=100), category_id: int | None = None, exchange_mode: str | None = None, keyword: str | None = None, sort_by: str | None = None, status: int = 1, latitude: float | None = Query(None, description="距离排序的参照纬度，不传则取登录用户已保存的位置"), longitude: float | None = Query(None, description="距离排序的参照经度，不传则取登录用户已保存的位置"), viewer_id: int | None = Depends(get_optional_user_id)):
    conditions = ["i.status=%s"]
    params: list = [status]
    if category_id:
        conditions.append("i.category_id=%s")
        params.append(category_id)
    if exchange_mode:
        conditions.append("i.exchange_mode=%s")
        params.append(exchange_mode)
    if keyword:
        conditions.append("(i.title LIKE %s OR i.description LIKE %s)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    where = " AND ".join(conditions)
    offset = (page - 1) * size

    # 「离我最近」：距离需按参照点实算，单独走一条分支（含隐私过滤与未设位置引导）
    if sort_by == "distance":
        return _list_items_by_distance(conditions, params, page, size, latitude, longitude, viewer_id)

    # 排序白名单：值 -> ORDER BY 片段，避免用户输入直接拼接 SQL
    sort_map = {
        None: "i.id DESC",
        "created_at": "i.created_at DESC, i.id DESC",
        "carbon_value": "i.carbon_value DESC, i.id DESC",
    }
    if sort_by not in sort_map:
        raise HTTPException(status_code=400, detail="不支持的排序方式")
    order_sql = sort_map[sort_by]

    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM item i WHERE {where}", params)
            total = cursor.fetchone()["total"]
            cursor.execute(
                f"""SELECT i.*, c.name AS category_name
                    FROM item i
                    LEFT JOIN category c ON i.category_id = c.id
                    WHERE {where}
                    ORDER BY {order_sql}
                    LIMIT %s OFFSET %s""",
                params + [size, offset],
            )
            items = cursor.fetchall()
    # 列表不透出 panorama_views 大 JSON（仅保留 panorama_status 供卡片 360° 角标）
    for it in items:
        it["panorama_views"] = None
        # 封面读取时现场签名（DB 只存相对路径，落库签名 1 小时就过期）
        it["images"] = item_covers_json(it.get("images"))
    return success({"items": items, "total": total, "page": page, "size": size})


@router.get("/{item_id}")
def get_item(item_id: int):
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM item WHERE id=%s LIMIT 1", (item_id,))
            item = cursor.fetchone()
    if not item:
        raise HTTPException(404, "物品不存在")
    # 交易方式整形：交换模式回落 1（免费送，与 DB 列默认值一致）；
    # 价格只在「低价转让」下有意义，其余模式归 0，避免前端把历史脏值当成售价展示。
    try:
        mode = int(item.get("exchange_mode")) if item.get("exchange_mode") is not None else EXCHANGE_MODE_GIVE
    except (TypeError, ValueError):
        mode = EXCHANGE_MODE_GIVE
    item["exchange_mode"] = mode
    if mode == EXCHANGE_MODE_SELL:
        try:
            item["price"] = float(Decimal(str(item.get("price") or 0)).quantize(Decimal("0.01")))
        except (InvalidOperation, TypeError, ValueError):
            item["price"] = 0.0
    else:
        item["price"] = 0.0
    # 360° 字段整形：仅 ready 时透出视角图 dict，其余状态置 None（坏 JSON 静默降级）
    # 视角图 URL 读取时补 HMAC 签名（DB 存相对路径，静态路由强制校验签名）
    raw_views = item.get("panorama_views")
    item["panorama_views"] = None
    if item.get("panorama_status") == "ready" and raw_views:
        try:
            views = json.loads(raw_views).get("views")
            if isinstance(views, dict) and views:
                item["panorama_views"] = {
                    name: sign_view_url(url) for name, url in views.items()
                }
        except (TypeError, ValueError):
            pass
    # 3D 模型字段整形：
    # - model_url 仅 ready 时透出，且读取时补 HMAC 签名（DB 只存相对路径）；
    # - model_3d_enabled 透出后端开关，前端据此决定是否显示「生成 3D」入口，
    #   省掉一次额外请求（开关在后端硬校验，前端只是跟着隐藏按钮）。
    # - model_error 仅 failed 时透出失败原因（上游报错原文；混元分支已归一化成中文），
    #   前端直接展示，否则「点了没反应」这类问题只能靠终端日志定位。
    raw_model = item.get("model_url")
    item["model_url"] = (
        sign_model_url(raw_model) if item.get("model_status") == "ready" and raw_model else None
    )
    item["model_status"] = item.get("model_status") or "none"
    item["model_error"] = (
        item.get("model_error") if item["model_status"] == "failed" else None
    )
    item["model_3d_enabled"] = model_3d_enabled()
    # 封面读取时现场签名（DB 只存相对路径；历史脏数据里已带 ?exp=&sig= 的旧值
    # 由 normalize_image_ref 剥掉旧签名后重签，无需写 SQL 即自动恢复）
    item["images"] = item_covers_json(item.get("images"))
    return success(item)


@router.post("")
def create_item(
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    description: str = Form(...),
    category_id: int = Form(...),
    expected_exchange: str = Form(""),
    contact: str = Form(...),
    exchange_mode: int = Form(EXCHANGE_MODE_GIVE),
    price: str = Form(""),
    condition_level: int = Form(0),
    original_price: str = Form(""),
    image: UploadFile | None = File(None),
    user_id: int = Depends(get_current_user_id),
):
    title = title.strip()
    description = description.strip()
    contact = contact.strip()
    # 必填字段检查（strip 后判空，避免纯空白绕过）
    if not title or not description or not contact:
        raise HTTPException(400, "物品名称、描述和联系方式不能为空")
    # 长度限制
    if len(title) > MAX_TITLE_LEN:
        raise HTTPException(400, f"物品名称不能超过 {MAX_TITLE_LEN} 字")
    if len(description) > MAX_DESCRIPTION_LEN:
        raise HTTPException(400, f"物品描述不能超过 {MAX_DESCRIPTION_LEN} 字")
    if len(contact) > MAX_CONTACT_LEN:
        raise HTTPException(400, f"联系方式不能超过 {MAX_CONTACT_LEN} 字")

    # ---------- 交易方式 + 金额 ----------
    # exchange_mode：1=免费送 2=等价互换 3=低价转让 4=平台回收（不翻转，与 DB 列注释一致）
    if exchange_mode not in EXCHANGE_MODES:
        raise HTTPException(400, "交易方式只能是 1=免费送 / 2=交换 / 3=低价转让 / 4=平台回收")
    if exchange_mode == EXCHANGE_MODE_SELL:
        # 低价转让必须带合法转让价；空值会被 _parse_money 解析为 0，这里显式拦下
        if price is None or str(price).strip() == "":
            raise HTTPException(400, "选择低价转让时请填写转让价")
        item_price = _parse_money(price, low=MIN_PRICE, high=MAX_PRICE, label="转让价")
    else:
        # 免费送 / 交换 / 平台回收不带金额：无论前端传什么都归 0，避免脏值入库
        # （回收的「金额」是服务端按成色算的 accept_points，不走 price 列）
        item_price = Decimal("0.00")

    # ---------- 成色 / 原价（可选，DB 列已存在） ----------
    if condition_level not in range(0, MAX_CONDITION + 1):
        raise HTTPException(400, f"成色等级只能是 0（未填写）或 {MIN_CONDITION}-{MAX_CONDITION}")
    item_original_price = _parse_money(
        original_price, low=MIN_ORIGINAL_PRICE, high=MAX_ORIGINAL_PRICE, label="原价"
    )
    expected_item = expected_exchange.strip() or None

    # 图片必填：至少上传 1 张（前端未选择文件时 image 为 None 或 filename 为空）
    if image is None or not image.filename:
        raise HTTPException(400, "请至少上传 1 张物品图片")

    image_url: str | None = None
    image_path: Path | None = None
    # 图片必填校验已前置，此处 image 与 filename 必定非空
    # 先读内容再做魔数校验：不信任 Content-Type，以文件头判断真实类型
    data = image.file.read(MAX_IMAGE_SIZE + 1)
    if len(data) > MAX_IMAGE_SIZE:
        raise HTTPException(400, "图片大小不能超过 5MB")
    if not data:
        raise HTTPException(400, "图片内容为空")
    ext = detect_image_ext(data)
    if not ext:
        raise HTTPException(400, "文件内容不是有效图片，仅支持 jpg/png/webp/gif 格式")
    items_dir = Path(settings.upload_dir).resolve() / "items"
    items_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{ext}"
    image_path = items_dir / filename
    image_path.write_bytes(data)
    # ⚠ DB 只存**相对路径**（items/xxx.webp），签名在读取时现场补。
    # 此前这里把「带 ?exp=&sig= 的签名 URL」落库，而签名只有 1 小时有效期（
    # file_url_expire_seconds=3600），导致任何物品发布 1 小时后封面必然 403
    # 裂成占位图（存量铁证：item.id=77 的 exp 已过期、verify 为 False，文件却完好）。
    # 这也是 merchant_service.sign_relative docstring 早已写明的项目约定。
    relative_path = f"items/{filename}"
    image_url = relative_path

    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM category WHERE id=%s LIMIT 1", (category_id,))
            if not cursor.fetchone():
                raise HTTPException(400, "所选分类不存在")
            images_json = json.dumps([image_url]) if image_url else None
            cursor.execute(
                """INSERT INTO item
                       (user_id, category_id, title, description, images,
                        expected_item, contact, status,
                        exchange_mode, price, condition_level, original_price)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, 4, %s, %s, %s, %s)""",
                (user_id, category_id, title, description, images_json,
                 expected_item, contact,
                 exchange_mode, item_price, condition_level, item_original_price),
            )
            item_id = cursor.lastrowid
    # 360° 视图生成：BackgroundTasks 后台执行，不阻断发布（惰性 import 避免循环依赖）
    if image_path is not None:
        try:
            from app.services import panorama_service
            background_tasks.add_task(panorama_service.run_generate, item_id, image_path)
        except Exception:  # noqa: BLE001
            pass
    return success({"id": item_id, "status": 4}, "提交成功，等待审核")


# ============================================================
# 平台回收（二期）：用户把已发布物品交给平台回收
# ============================================================
@router.put("/{item_id}/recycle")
def submit_recycle(
    item_id: int,
    req: RecycleSubmitRequest,
    user_id: int = Depends(get_current_user_id),
):
    """提交平台回收：按成色估价 → 立即发积分 → 建回收单（同一事务）。

    全部写入（item 状态 + 回收单 + 积分流水）在同一事务内，任一环节失败
    整体回滚。估价由服务端按 `item.condition_level` 从常量表计算，
    **绝不接受前端传值**（否则用户可伪造 500 分）。
    """
    with connection() as conn:
        with conn.cursor() as cursor:
            result = recycle_service.submit_recycle(
                cursor, user_id, item_id, req.pickup_method, req.pickup_address
            )
    return success(result, "提交成功，平台将安排取件")
