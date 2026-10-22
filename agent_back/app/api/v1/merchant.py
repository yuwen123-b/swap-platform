"""商家端闭环接口（商家端 + 用户端，共 16 个接口）。

- 商家端：入驻申请 / 我的店铺（读+改） / 我的商品（增改/上下架） / 核销列表 / 核销
  / 数据看板 / 结算自查
- 用户端：浏览商家 / 看某店商品 / 兑换 / 我的兑换记录

两者共用前缀 `/api/v1/merchant`（在 `app/main.py` 中与 `/api/merchant` 双挂载，
与 `_NEW_ROUTERS` 里其它增量模块同口径），因此**路径必须互不歧义**：

| 路径 | 段落 | 说明 |
|---|---|---|
| `/products` | 2 | 商家自己的商品（静态） |
| `/products/{id}` | 3 | 改商品，PUT |
| `/products/{id}/offline` | 3 | 下架，PUT |
| `/shops` | 2 | 用户浏览商家 |
| `/shops/{id}/products` | 3 | 某店商品，GET |

**为什么商家列表是 `/shops` 而不是报告初稿的 `/list`**：`/merchant/{id}/products`
这类通配段在 FastAPI 里会被编译成正则 `[^/]+`，一旦与静态段同段落数重叠，
静态路由**不会**被优先回退（匹配失败直接 422）。改用 `/shops` 前缀后，
用户侧所有路径都以字面量段开头，与商家侧 `/products*` 完全隔离，无歧义。

鉴权：user_id 一律从 JWT 解析（`Depends(get_current_user_id)`），不接受前端传入。
响应外壳统一 `success()`（`{code:0, message, data}`），与管理端的 `ok()`（`code:200`）刻意不混用。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.config import settings
from app.core.response import success
from app.core.security import get_current_user_id
from app.db.pool import connection
from app.schemas.merchant import (
    MerchantApplyRequest,
    MerchantInfoUpdate,
    MerchantProductCreate,
    MerchantProductUpdate,
    RedeemRequest,
    VerifyRequest,
)
from app.services import merchant_service
from app.services.merchant_service import (
    MERCHANT_STATUS_APPROVED,
    MERCHANT_STATUS_CLOSED,
    MERCHANT_STATUS_PENDING,
    MERCHANT_STATUS_REJECTED,
    PRODUCT_STATUS_OFFLINE,
    PRODUCT_STATUS_ONLINE,
)

logger = logging.getLogger(__name__)

# 字段长度上限（用中文报错在接口层校验，不用 Pydantic 的 max_length —— 
# 全局 RequestValidationError 处理器会把 Pydantic 英文报错原样透出）
MAX_NAME_LEN = 100
MAX_CATEGORY_LEN = 50
MAX_CONTACT_LEN = 100
MAX_ADDRESS_LEN = 200
MAX_DESCRIPTION_LEN = 2000
MAX_TITLE_LEN = 100
MAX_IMAGE_URL_LEN = 500
MAX_POINTS_COST = 1_000_000
MAX_STOCK = 1_000_000
MAX_CODE_LEN = 16

LIST_DEFAULT_SIZE = 10
LIST_MAX_SIZE = 50


def _ensure_enabled() -> None:
    """商家端总开关：`MERCHANT_ENABLED=false` 时整块接口返回 403。

    做成 router 级依赖，新增接口自动继承，不会漏开关。
    管理端接口不受此开关影响（管理员仍需能审核与结算）。
    """
    if not settings.merchant_enabled:
        raise HTTPException(403, "商家端功能未开启")


router = APIRouter(dependencies=[Depends(_ensure_enabled)])


# ============================================================
# 参数清洗
# ============================================================
def _clean_text(value, max_len: int, label: str, required: bool = False) -> str | None:
    text = "" if value is None else str(value).strip()
    if required and not text:
        raise HTTPException(400, f"{label}不能为空")
    if len(text) > max_len:
        raise HTTPException(400, f"{label}不能超过 {max_len} 个字符")
    return text or None


def _clean_int(value, low: int, high: int, label: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise HTTPException(400, f"{label}必须是整数")
    if number < low or number > high:
        raise HTTPException(400, f"{label}必须在 {low} 到 {high} 之间")
    return number


def _clamp(value, low: int, high: int) -> int:
    """分页参数夹紧（而非报 422）：越界属客户端习惯差异，夹紧更友好。"""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(number, high))


def _normalize_status(value, label: str) -> int | None:
    if value is None or value == "":
        return None
    return _clean_int(value, 0, 9, label)


def _page_params(page: int, size: int) -> tuple[int, int]:
    return _clamp(page, 1, 10 ** 6), _clamp(size, 1, LIST_MAX_SIZE)


# ============================================================
# 商家端：入驻与店铺
# ============================================================
@router.post("/apply")
def apply_merchant(req: MerchantApplyRequest, user_id: int = Depends(get_current_user_id)):
    """商家入驻申请。

    一个账号只能开一家店（`uk_merchant_user`）：
    - 首次申请 → INSERT，status=0；
    - 待审核 / 已被拒 → UPDATE 原行重提，status 回到 0 并清空审核意见；
    - 已通过 / 已停业 → 400，不允许再申请。

    **可选字段只在请求里显式出现时才写入**（`exclude_unset`）：
    商家被拒后往往只改其中一项就重提，若按「整表覆盖」处理，
    没重新填的 contact/address/category 会被静默清空成 NULL。
    需要清空某项时显式传空串即可（空串 → 落库 NULL）。
    """
    provided = req.model_dump(exclude_unset=True)
    name = _clean_text(provided.get("name"), MAX_NAME_LEN, "店铺名", required=True)
    _OPTIONAL_FIELDS = (
        ("category", MAX_CATEGORY_LEN, "店铺类型"),
        ("contact", MAX_CONTACT_LEN, "联系方式"),
        ("address", MAX_ADDRESS_LEN, "地址"),
        ("description", MAX_DESCRIPTION_LEN, "店铺简介"),
    )
    optional = {
        key: _clean_text(provided.get(key), limit, label)
        for key, limit, label in _OPTIONAL_FIELDS
        if key in provided
    }

    with connection() as conn:
        with conn.cursor() as cursor:
            existing = merchant_service.get_merchant_by_user(cursor, user_id)
            resent = False
            if existing:
                status = merchant_service.as_int(existing.get("status"))
                if status == MERCHANT_STATUS_APPROVED:
                    raise HTTPException(400, "您已入驻，无需重复申请")
                if status == MERCHANT_STATUS_CLOSED:
                    raise HTTPException(400, "店铺已停业，暂不支持重新申请")
                merchant_id = merchant_service.as_int(existing.get("id"))
                assignments = ["name=%s", "status=%s", "audit_reason=NULL"]
                params: list = [name, MERCHANT_STATUS_PENDING]
                for key, value in optional.items():
                    assignments.append(f"{key}=%s")
                    params.append(value)
                params.append(merchant_id)
                cursor.execute(
                    f"UPDATE merchant SET {', '.join(assignments)} WHERE id=%s", params
                )
                resent = True
            else:
                cursor.execute(
                    "INSERT INTO merchant "
                    "(user_id, name, category, contact, address, description, status, commission_rate) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (user_id, name, optional.get("category"), optional.get("contact"),
                     optional.get("address"), optional.get("description"),
                     MERCHANT_STATUS_PENDING, f"{float(settings.merchant_commission_rate):.2f}"),
                )
                merchant_id = merchant_service.as_int(cursor.lastrowid)

            cursor.execute(
                "SELECT id, user_id, name, category, contact, address, description, logo_url, "
                "       status, commission_rate, audit_reason, created_at "
                "FROM merchant WHERE id=%s LIMIT 1",
                (merchant_id,),
            )
            row = cursor.fetchone()

    return success(
        merchant_service.to_merchant_info(row or {}),
        "已重新提交入驻申请，请等待审核" if resent else "入驻申请已提交，请等待审核",
    )


@router.put("/info")
def update_merchant_info(
    req: MerchantInfoUpdate, user_id: int = Depends(get_current_user_id)
):
    """修改店铺资料（工作台「店铺设置」页）。

    与 `POST /apply` 同一个 `exclude_unset` 口径：**只覆盖请求里显式出现的字段**。
    商家只改联系方式时，没重新填的分类/地址不会被清空；要清空某项就显式传空串。

    允许在「待审核」阶段修改资料（商家在审核期间自己改地址是合理的），
    但**不允许**在「已拒绝 / 已停业」状态下修改 —— 那两种状态要走重新入驻流程。
    `status` / `commission_rate` 一律不在可改字段内（费率以表行为准，只有管理员能动）。
    """
    provided = req.model_dump(exclude_unset=True)
    if not provided:
        raise HTTPException(400, "没有需要修改的内容")

    fields = (
        ("name", MAX_NAME_LEN, "店铺名", True),
        ("category", MAX_CATEGORY_LEN, "店铺类型", False),
        ("contact", MAX_CONTACT_LEN, "联系方式", False),
        ("address", MAX_ADDRESS_LEN, "地址", False),
        ("description", MAX_DESCRIPTION_LEN, "店铺简介", False),
        ("logo_url", MAX_IMAGE_URL_LEN, "店铺 LOGO", False),
    )
    updates: list[str] = []
    params: list = []
    for key, limit, label, required in fields:
        if key not in provided:
            continue
        updates.append(f"{key}=%s")
        params.append(_clean_text(provided.get(key), limit, label, required=required))

    with connection() as conn:
        with conn.cursor() as cursor:
            merchant = merchant_service.require_merchant(cursor, user_id)
            status = merchant_service.as_int(merchant.get("status"))
            if status == MERCHANT_STATUS_REJECTED:
                raise HTTPException(400, "入驻申请已被拒绝，请重新提交入驻申请")
            if status == MERCHANT_STATUS_CLOSED:
                raise HTTPException(400, "店铺已停业，暂不支持修改资料")
            merchant_id = merchant_service.as_int(merchant.get("id"))
            cursor.execute(
                f"UPDATE merchant SET {', '.join(updates)} WHERE id=%s", params + [merchant_id]
            )
            cursor.execute(
                "SELECT id, user_id, name, category, contact, address, description, logo_url, "
                "       status, commission_rate, audit_reason, created_at "
                "FROM merchant WHERE id=%s LIMIT 1",
                (merchant_id,),
            )
            row = cursor.fetchone()
    return success(merchant_service.to_merchant_info(row or {}), "店铺资料已保存")


@router.get("/info")
def merchant_info(user_id: int = Depends(get_current_user_id)):
    """当前登录账号的商家信息。

    未入驻时返回 `{"merchant": null}` 而不是 404 —— 前端要据此决定
    首屏渲染「入驻申请表单」还是「店铺管理台」，用 404 表达会让正常流程走错误分支。
    """
    with connection() as conn:
        with conn.cursor() as cursor:
            row = merchant_service.get_merchant_by_user(cursor, user_id)
    return success(
        {
            "merchant": merchant_service.to_merchant_info(row) if row else None,
            "enabled": bool(settings.merchant_enabled),
        }
    )


# ============================================================
# 商家端：商品管理
# ============================================================
@router.get("/products")
def list_own_products(user_id: int = Depends(get_current_user_id)):
    """商家查看自己的商品列表（含已下架，按下架状态由前端展示角标）。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            merchant = merchant_service.require_merchant(cursor, user_id)
            merchant_id = merchant_service.as_int(merchant.get("id"))
            cursor.execute(
                "SELECT id, merchant_id, title, description, image_url, points_cost, "
                "       stock, sold_count, status, created_at "
                "FROM merchant_product WHERE merchant_id=%s ORDER BY id DESC",
                (merchant_id,),
            )
            rows = cursor.fetchall()
    return success(
        {
            "merchant_id": merchant_id,
            "merchant_status": merchant_service.as_int(merchant.get("status")),
            "list": [merchant_service.to_product_item(row) for row in rows],
        }
    )


@router.post("/products")
def create_product(
    req: MerchantProductCreate, user_id: int = Depends(get_current_user_id)
):
    """上架新商品。只有**已通过审核**的店铺才能上架。"""
    title = _clean_text(req.title, MAX_TITLE_LEN, "商品名称", required=True)
    description = _clean_text(req.description, MAX_DESCRIPTION_LEN, "商品描述")
    image_url = _clean_text(req.image_url, MAX_IMAGE_URL_LEN, "商品图片")
    points_cost = _clean_int(req.points_cost, 0, MAX_POINTS_COST, "所需积分")
    stock = _clean_int(req.stock, 0, MAX_STOCK, "库存")

    with connection() as conn:
        with conn.cursor() as cursor:
            merchant = merchant_service.require_merchant(cursor, user_id, need_approved=True)
            merchant_id = merchant_service.as_int(merchant.get("id"))
            cursor.execute(
                "INSERT INTO merchant_product "
                "(merchant_id, title, description, image_url, points_cost, stock, sold_count, status) "
                "VALUES (%s,%s,%s,%s,%s,%s,0,%s)",
                (merchant_id, title, description, image_url, points_cost, stock, PRODUCT_STATUS_ONLINE),
            )
            product_id = merchant_service.as_int(cursor.lastrowid)
            cursor.execute(
                "SELECT id, merchant_id, title, description, image_url, points_cost, "
                "       stock, sold_count, status, created_at "
                "FROM merchant_product WHERE id=%s LIMIT 1",
                (product_id,),
            )
            row = cursor.fetchone()
    return success(merchant_service.to_product_item(row or {}), "商品已上架")


@router.put("/products/{product_id}")
def update_product(
    product_id: int,
    req: MerchantProductUpdate,
    user_id: int = Depends(get_current_user_id),
):
    """修改商品：只更新传入的字段（未传 / None 表示不修改）。"""
    fields = req.model_dump(exclude_unset=True)
    updates: list[str] = []
    params: list = []

    if "title" in fields:
        updates.append("title=%s")
        params.append(_clean_text(fields["title"], MAX_TITLE_LEN, "商品名称", required=True))
    if "description" in fields:
        updates.append("description=%s")
        params.append(_clean_text(fields["description"], MAX_DESCRIPTION_LEN, "商品描述"))
    if "image_url" in fields:
        updates.append("image_url=%s")
        params.append(_clean_text(fields["image_url"], MAX_IMAGE_URL_LEN, "商品图片"))
    if "points_cost" in fields:
        updates.append("points_cost=%s")
        params.append(_clean_int(fields["points_cost"], 0, MAX_POINTS_COST, "所需积分"))
    if "stock" in fields:
        updates.append("stock=%s")
        params.append(_clean_int(fields["stock"], 0, MAX_STOCK, "库存"))

    if not updates:
        raise HTTPException(400, "没有需要修改的内容")

    with connection() as conn:
        with conn.cursor() as cursor:
            merchant = merchant_service.require_merchant(cursor, user_id, need_approved=True)
            merchant_id = merchant_service.as_int(merchant.get("id"))
            # 归属校验写进 WHERE：改不到别人的商品，也不需要先查再改
            cursor.execute(
                f"UPDATE merchant_product SET {', '.join(updates)} WHERE id=%s AND merchant_id=%s",
                params + [product_id, merchant_id],
            )
            if cursor.rowcount == 0:
                raise HTTPException(404, "商品不存在或不属于本店")
            cursor.execute(
                "SELECT id, merchant_id, title, description, image_url, points_cost, "
                "       stock, sold_count, status, created_at "
                "FROM merchant_product WHERE id=%s LIMIT 1",
                (product_id,),
            )
            row = cursor.fetchone()
    return success(merchant_service.to_product_item(row or {}), "商品已更新")


@router.put("/products/{product_id}/offline")
def offline_product(product_id: int, user_id: int = Depends(get_current_user_id)):
    """下架商品（软下架：置 status=0，不删行，已有兑换记录不受影响）。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            merchant = merchant_service.require_merchant(cursor, user_id)
            merchant_id = merchant_service.as_int(merchant.get("id"))
            cursor.execute(
                "UPDATE merchant_product SET status=%s WHERE id=%s AND merchant_id=%s",
                (PRODUCT_STATUS_OFFLINE, product_id, merchant_id),
            )
            if cursor.rowcount == 0:
                raise HTTPException(404, "商品不存在或不属于本店")
    return success({"product_id": product_id, "status": PRODUCT_STATUS_OFFLINE}, "商品已下架")


@router.put("/products/{product_id}/online")
def online_product(product_id: int, user_id: int = Depends(get_current_user_id)):
    """重新上架商品（与 `/offline` 完全对称：置 status=1）。

    `/offline` 是软下架，行和数据都在，所以这里只需把状态改回来。
    库存为 0 的商品也允许上架：用户端会显示「已兑完」，
    真正下单时由 `redeem` 的 `stock>0` 条件更新兜底拒单。
    """
    with connection() as conn:
        with conn.cursor() as cursor:
            merchant = merchant_service.require_merchant(cursor, user_id, need_approved=True)
            merchant_id = merchant_service.as_int(merchant.get("id"))
            cursor.execute(
                "UPDATE merchant_product SET status=%s WHERE id=%s AND merchant_id=%s",
                (PRODUCT_STATUS_ONLINE, product_id, merchant_id),
            )
            if cursor.rowcount == 0:
                raise HTTPException(404, "商品不存在或不属于本店")
    return success({"product_id": product_id, "status": PRODUCT_STATUS_ONLINE}, "商品已重新上架")


# ============================================================
# 商家端：核销
# ============================================================
@router.get("/redemptions")
def list_redemptions(
    status: int | None = Query(default=None),
    page: int = Query(default=1),
    size: int = Query(default=LIST_DEFAULT_SIZE),
    user_id: int = Depends(get_current_user_id),
):
    """商家查看本店兑换单，可按状态筛选（1待核销 2已核销 3已过期 4已取消）。"""
    status_value = _normalize_status(status, "兑换单状态")
    page, size = _page_params(page, size)

    with connection() as conn:
        with conn.cursor() as cursor:
            merchant = merchant_service.require_merchant(cursor, user_id)
            merchant_id = merchant_service.as_int(merchant.get("id"))

            where = "o.merchant_id=%s"
            params: list = [merchant_id]
            if status_value is not None:
                where += " AND o.status=%s"
                params.append(status_value)

            cursor.execute(
                f"SELECT COUNT(*) AS total FROM redemption_order o WHERE {where}", params
            )
            total = merchant_service.as_int((cursor.fetchone() or {}).get("total"))

            cursor.execute(
                f"SELECT o.id, o.order_no, o.status, o.code, o.points_cost, o.product_id, "
                f"       o.user_id, o.merchant_id, o.expires_at, o.redeemed_at, o.created_at, "
                f"       p.title AS product_title, u.nickname AS user_nickname "
                f"FROM redemption_order o "
                f"LEFT JOIN merchant_product p ON o.product_id = p.id "
                f"LEFT JOIN user u ON o.user_id = u.id "
                f"WHERE {where} ORDER BY o.id DESC LIMIT %s OFFSET %s",
                params + [size, (page - 1) * size],
            )
            rows = cursor.fetchall()

    return success(
        {
            "total": total,
            "page": page,
            "size": size,
            "list": [merchant_service.to_redemption_item(row) for row in rows],
        }
    )


@router.post("/redemptions/verify")
def verify_redemption(req: VerifyRequest, user_id: int = Depends(get_current_user_id)):
    """商家核销：输入 6 位核销码完成履约确认。

    并发安全依赖服务层的**条件更新**（`status=1 AND expires_at>NOW()` + rowcount），
    商家连点两次也只有第一次生效。核销不退积分、不动库存。
    """
    code = _clean_text(req.code, MAX_CODE_LEN, "核销码", required=True)
    if not code:
        raise HTTPException(400, "核销码不能为空")

    with connection() as conn:
        with conn.cursor() as cursor:
            merchant = merchant_service.require_merchant(cursor, user_id, need_approved=True)
            result = merchant_service.verify_redemption(
                cursor, merchant_service.as_int(merchant.get("id")), code
            )
    return success(result, "核销成功")


# ============================================================
# 商家端：数据看板
# ============================================================
@router.get("/dashboard")
def merchant_dashboard(user_id: int = Depends(get_current_user_id)):
    """商家数据看板：今日核销 / 累计核销 / 去重用户 / 热销商品 / 近 7 日趋势。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            merchant = merchant_service.require_merchant(cursor, user_id)
            data = merchant_service.merchant_dashboard(
                cursor, merchant_service.as_int(merchant.get("id"))
            )
    return success(data)


# ============================================================
# 商家端：结算自查（只读）
# 路径是 `/settlement/summary`（静态两段），与 `/products/{id}`、`/shops/{id}/products`
# 段落数不同、且不与任何通配段重叠，无歧义。
# 真正的出账在管理端 `POST /api/admin/merchant/settle`，这里只给商家看账。
# ============================================================
@router.get("/settlement/summary")
def settlement_summary(user_id: int = Depends(get_current_user_id)):
    """本店结算自查：应得 / 平台佣金 / 实得 / 已结算 / 待结算。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            merchant = merchant_service.require_merchant(cursor, user_id)
            data = merchant_service.merchant_settlement_summary(cursor, merchant)
    return success(data)


# ============================================================
# 用户端：浏览商家与商品
# ============================================================
@router.get("/shops")
def list_shops(
    category: str | None = Query(default=None),
    page: int = Query(default=1),
    size: int = Query(default=LIST_DEFAULT_SIZE),
):
    """用户浏览商家列表（只出已通过审核的商家）。

    公开浏览接口，不要求登录 —— 与物品列表（`get_optional_user_id`）口径一致，
    未登录用户也能看到有哪些店可以兑换。
    """
    category_value = _clean_text(category, MAX_CATEGORY_LEN, "店铺类型")
    page, size = _page_params(page, size)

    where = "m.status=%s"
    params: list = [MERCHANT_STATUS_APPROVED]
    if category_value:
        where += " AND m.category=%s"
        params.append(category_value)

    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM merchant m WHERE {where}", params)
            total = merchant_service.as_int((cursor.fetchone() or {}).get("total"))
            cursor.execute(
                f"SELECT m.id, m.name, m.category, m.address, m.contact, m.description, m.logo_url, "
                f"       (SELECT COUNT(*) FROM merchant_product p "
                f"        WHERE p.merchant_id = m.id AND p.status = {PRODUCT_STATUS_ONLINE}) AS product_count "
                f"FROM merchant m WHERE {where} ORDER BY m.id ASC LIMIT %s OFFSET %s",
                params + [size, (page - 1) * size],
            )
            rows = cursor.fetchall()

    return success(
        {
            "total": total,
            "page": page,
            "size": size,
            "list": [merchant_service.to_merchant_brief(row) for row in rows],
        }
    )


@router.get("/shops/{merchant_id}/products")
def list_shop_products(merchant_id: int):
    """查看某商家所有上架商品（店铺未通过审核 / 不存在时 404）。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, user_id, name, category, contact, address, description, logo_url, "
                "       status, commission_rate, audit_reason, created_at "
                "FROM merchant WHERE id=%s LIMIT 1",
                (merchant_id,),
            )
            merchant = cursor.fetchone()
            if not merchant or merchant_service.as_int(merchant.get("status")) != MERCHANT_STATUS_APPROVED:
                raise HTTPException(404, "商家不存在或暂未开放")

            cursor.execute(
                "SELECT id, merchant_id, title, description, image_url, points_cost, "
                "       stock, sold_count, status, created_at "
                "FROM merchant_product WHERE merchant_id=%s AND status=%s ORDER BY id ASC",
                (merchant_id, PRODUCT_STATUS_ONLINE),
            )
            rows = cursor.fetchall()

    brief = merchant_service.to_merchant_brief(merchant)
    brief["product_count"] = len(rows)
    return success(
        {
            "merchant": brief,
            "list": [merchant_service.to_product_item(row) for row in rows],
        }
    )


# ============================================================
# 用户端：兑换
# ============================================================
@router.post("/redeem")
def redeem(req: RedeemRequest, user_id: int = Depends(get_current_user_id)):
    """用户兑换商家商品/服务，返回核销码与过期时间。

    全部写入（扣库存 + 落兑换单 + 扣积分写流水）在同一事务内，
    任一环节失败整体回滚，不会出现「积分扣了却没有兑换单」。
    """
    product_id = _clean_int(req.product_id, 1, 10 ** 18, "商品ID")
    with connection() as conn:
        with conn.cursor() as cursor:
            result = merchant_service.redeem(cursor, user_id, product_id)
    return success(result, "兑换成功，请凭核销码到店使用")


@router.get("/my-redemptions")
def my_redemptions(
    status: int | None = Query(default=None),
    page: int = Query(default=1),
    size: int = Query(default=LIST_DEFAULT_SIZE),
    user_id: int = Depends(get_current_user_id),
):
    """用户查看自己的兑换记录（可按状态筛选）。

    过期判定只读、不在这里退款：退款由后台 `expire_redemptions` 定时任务
    统一处理（避免 GET 接口产生写副作用，也避免与定时任务重复退款）。
    """
    status_value = _normalize_status(status, "兑换单状态")
    page, size = _page_params(page, size)

    where = "o.user_id=%s"
    params: list = [user_id]
    if status_value is not None:
        where += " AND o.status=%s"
        params.append(status_value)

    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) AS total FROM redemption_order o WHERE {where}", params
            )
            total = merchant_service.as_int((cursor.fetchone() or {}).get("total"))
            cursor.execute(
                f"SELECT o.id, o.order_no, o.status, o.code, o.points_cost, o.product_id, "
                f"       o.user_id, o.merchant_id, o.expires_at, o.redeemed_at, o.created_at, "
                f"       p.title AS product_title, m.name AS merchant_name "
                f"FROM redemption_order o "
                f"LEFT JOIN merchant_product p ON o.product_id = p.id "
                f"LEFT JOIN merchant m ON o.merchant_id = m.id "
                f"WHERE {where} ORDER BY o.id DESC LIMIT %s OFFSET %s",
                params + [size, (page - 1) * size],
            )
            rows = cursor.fetchall()

    return success(
        {
            "total": total,
            "page": page,
            "size": size,
            "list": [merchant_service.to_redemption_item(row) for row in rows],
        }
    )
