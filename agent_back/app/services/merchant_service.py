"""商家端闭环的核心业务逻辑。

闭环：用户赚积分 → 兑换商家服务 → 商家核销 → 平台结算 → 商家获得客流。

【事务约定 — 与 points_service / order_service 完全一致】
除 `expire_redemptions()`（后台定时任务，自行开事务）以外，
本模块所有函数都接收调用方传入的 `cursor`，**绝不自己开事务 / 不自己取连接**。
调用方负责把「业务写入 + 积分扣减」放进同一个 `with connection() as conn` 里，
任一环节抛错整体回滚，不会出现「库存扣了、分没扣」或「分扣了、订单没落库」。

【三条并发铁律】
1. **防超卖**：扣库存一律用条件更新 `WHERE id=%s AND status=1 AND stock>0`，
   靠 `rowcount` 判断是否抢到，数据库层杜绝负库存。
2. **防超扣**：`award_points` 只做 `UPDATE user SET points=points+%s`，**不做余额校验**。
   扣分前必须 `SELECT points FROM user WHERE id=%s FOR UPDATE` 拿行锁自己校验，
   否则并发下同一账号会被扣成负数。
   加锁顺序固定为「先锁 user 行、再改 product 行」，避免交叉死锁。
3. **防重复核销**：核销一律用条件更新
   `WHERE id=%s AND merchant_id=%s AND status=1 AND expires_at>NOW()` + `rowcount` 判定。
   绝不能「先 SELECT 再 UPDATE」——商家连点两次或与用户同时操作会造成双重核销。
"""
import logging
import re
import secrets
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.core.config import settings
from app.core.constants import (
    MERCHANT_PRODUCT_STATUS_LABEL,
    MERCHANT_STATUS_LABEL,
    REDEMPTION_STATUS_LABEL,
    SETTLEMENT_STATUS_LABEL,
)
from app.db.pool import connection
from app.services.points_service import (
    SOURCE_REDEEM,
    SOURCE_REDEEM_REFUND,
    PointsAwardError,
    award_points,
)

logger = logging.getLogger(__name__)

# ========== merchant.status ==========
MERCHANT_STATUS_PENDING = 0
MERCHANT_STATUS_APPROVED = 1
MERCHANT_STATUS_REJECTED = 2
MERCHANT_STATUS_CLOSED = 3

# ========== merchant_product.status ==========
PRODUCT_STATUS_OFFLINE = 0
PRODUCT_STATUS_ONLINE = 1

# ========== redemption_order.status ==========
REDEMPTION_STATUS_PENDING = 1
REDEMPTION_STATUS_REDEEMED = 2
REDEMPTION_STATUS_EXPIRED = 3
REDEMPTION_STATUS_CANCELLED = 4

# ========== merchant_settlement.status ==========
SETTLEMENT_STATUS_PENDING = 0
SETTLEMENT_STATUS_SETTLED = 1

# 兑换单号：RD + yyyyMMddHHmmss + 4 位随机数字 = 20 字符
# 前缀刻意与旧物交换单的 SW（order_service.ORDER_NO_PREFIX）区分，避免对账时混淆
REDEMPTION_NO_PREFIX = "RD"
REDEMPTION_NO_RANDOM_DIGITS = 4

# 核销码：6 位纯数字（商家要手动输入，纯数字最好输）
VERIFY_CODE_DIGITS = 6
VERIFY_CODE_MAX_RETRY = 5

# 结算周期格式 YYYY-MM
PERIOD_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

# 过期扫描：每批最多取 200 单，单次任务最多扫 20 批（4000 单），避免一次任务过久
EXPIRE_BATCH_SIZE = 200
EXPIRE_MAX_BATCHES = 20

_MONEY_QUANT = Decimal("0.01")

# 商品标题 / 商家名的兜底展示文案
_FALLBACK_PRODUCT_TITLE = "商家商品"
_FALLBACK_NICKNAME = "社区邻居"


class MerchantError(RuntimeError):
    """商家端可预期的业务错误（由 main.py 的异常处理器转成对应 HTTP 状态码）。

    与「数据库不可用」等基础设施错误区分：后者原样抛出（500），
    不伪装成业务错误，避免掩盖真实的表结构/连接问题。
    """

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


# ============================================================
# 标签与 URL 工具
# ============================================================
def merchant_status_label(status) -> str:
    try:
        return MERCHANT_STATUS_LABEL.get(int(status), "未知状态")
    except (TypeError, ValueError):
        return "未知状态"


def product_status_label(status) -> str:
    try:
        return MERCHANT_PRODUCT_STATUS_LABEL.get(int(status), "未知状态")
    except (TypeError, ValueError):
        return "未知状态"


def redemption_status_label(status) -> str:
    try:
        return REDEMPTION_STATUS_LABEL.get(int(status), "未知状态")
    except (TypeError, ValueError):
        return "未知状态"


def settlement_status_label(status) -> str:
    try:
        return SETTLEMENT_STATUS_LABEL.get(int(status), "未知状态")
    except (TypeError, ValueError):
        return "未知状态"


def sign_relative(relative_path) -> str | None:
    """把 uploads 下的相对路径转成带 HMAC 签名的受控 URL。

    与 item / user 的头像口径完全一致：**DB 只存相对路径，签名在读取时现场补**
    （签名带 1 小时有效期，落库会立刻过期）。
    外链（http/https 开头）原样返回，方便演示数据直接写 CDN 地址。

    实现统一收敛到 `image_utils.to_signed_url`（2026-10 起 item.images 也走同一份），
    避免两份「签名口径」各自漂移；本函数保留原名是历史调用方兼容。
    """
    from app.services.image_utils import to_signed_url

    return to_signed_url(relative_path)


def as_float(value) -> float:
    """DB Decimal / None → float（JSON 响应友好），非法值归 0。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def as_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def as_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    return None


# ============================================================
# 单号 / 核销码
# ============================================================
def generate_redemption_no(now: datetime | None = None) -> str:
    """生成兑换单号：RD + yyyyMMddHHmmss + 4 位随机数字。

    随机位用 `secrets` 而非 `random`：`uk_redemption_order_no` 唯一索引是硬约束，
    secrets 取值不可预测、分布均匀，配合撞键重试即可杜绝重复。
    """
    stamp = (now or datetime.now()).strftime("%Y%m%d%H%M%S")
    suffix = secrets.randbelow(10 ** REDEMPTION_NO_RANDOM_DIGITS)
    return f"{REDEMPTION_NO_PREFIX}{stamp}{suffix:0{REDEMPTION_NO_RANDOM_DIGITS}d}"


def generate_verify_code(cursor) -> str:
    """生成 6 位数字核销码，并尽量避开已存在的码。

    这里的「先查后插」只是为了降低撞键概率，**真正的唯一性由
    `uk_redemption_code` 唯一索引保证**（查与插之间存在极小竞态窗口，
    但六位码空间 100 万，实际冲突概率极低；真撞上会由唯一索引兜底报错）。
    """
    for _ in range(VERIFY_CODE_MAX_RETRY):
        code = f"{secrets.randbelow(10 ** VERIFY_CODE_DIGITS):0{VERIFY_CODE_DIGITS}d}"
        cursor.execute("SELECT id FROM redemption_order WHERE code=%s LIMIT 1", (code,))
        if not cursor.fetchone():
            return code
    raise MerchantError(500, "核销码生成失败，请稍后重试")


# ============================================================
# 行 → 响应模型
# ============================================================
def to_merchant_info(row: dict) -> dict:
    status = as_int(row.get("status"))
    return {
        "id": as_int(row.get("id")),
        "user_id": as_int(row.get("user_id")) if row.get("user_id") is not None else None,
        "name": row.get("name") or "",
        "category": row.get("category"),
        "contact": row.get("contact"),
        "address": row.get("address"),
        "description": row.get("description"),
        "logo_url": sign_relative(row.get("logo_url")),
        "status": status,
        "status_label": merchant_status_label(status),
        "commission_rate": as_float(row.get("commission_rate")),
        "audit_reason": row.get("audit_reason"),
        "created_at": as_datetime(row.get("created_at")),
    }


def to_merchant_brief(row: dict) -> dict:
    return {
        "id": as_int(row.get("id")),
        "name": row.get("name") or "",
        "category": row.get("category"),
        "address": row.get("address"),
        "contact": row.get("contact"),
        "description": row.get("description"),
        "logo_url": sign_relative(row.get("logo_url")),
        "product_count": as_int(row.get("product_count")),
    }


def to_product_item(row: dict) -> dict:
    status = as_int(row.get("status") if row.get("status") is not None else PRODUCT_STATUS_ONLINE)
    return {
        "id": as_int(row.get("id")),
        "merchant_id": as_int(row.get("merchant_id")),
        "title": row.get("title") or "",
        "description": row.get("description"),
        "image_url": sign_relative(row.get("image_url")),
        "points_cost": as_int(row.get("points_cost")),
        "stock": as_int(row.get("stock")),
        "sold_count": as_int(row.get("sold_count")),
        "status": status,
        "status_label": product_status_label(status),
        "created_at": as_datetime(row.get("created_at")),
    }


def to_redemption_item(row: dict) -> dict:
    status = as_int(row.get("status"))
    return {
        "id": as_int(row.get("id")),
        "order_no": row.get("order_no") or "",
        "status": status,
        "status_label": redemption_status_label(status),
        "code": row.get("code") or "",
        "points_cost": as_int(row.get("points_cost")),
        "product_id": as_int(row.get("product_id")),
        "product_title": row.get("product_title") or "",
        "merchant_id": as_int(row.get("merchant_id")),
        "merchant_name": row.get("merchant_name") or "",
        "user_id": as_int(row.get("user_id")),
        "user_nickname": row.get("user_nickname") or _FALLBACK_NICKNAME,
        "expires_at": as_datetime(row.get("expires_at")),
        "redeemed_at": as_datetime(row.get("redeemed_at")),
        "created_at": as_datetime(row.get("created_at")),
    }


# ============================================================
# 商家查询
# ============================================================
def get_merchant_by_user(cursor, user_id: int) -> dict | None:
    """按登录账号反查商家（user 表没有 role 字段，身份全靠 merchant.user_id 关联）。"""
    cursor.execute(
        "SELECT id, user_id, name, category, contact, address, description, logo_url, "
        "       status, commission_rate, audit_reason, created_at "
        "FROM merchant WHERE user_id=%s LIMIT 1",
        (user_id,),
    )
    return cursor.fetchone()


def require_merchant(cursor, user_id: int, need_approved: bool = False) -> dict:
    """取当前登录账号的商家；不存在（或未通过审核）时抛出可读错误。"""
    merchant = get_merchant_by_user(cursor, user_id)
    if not merchant:
        raise MerchantError(404, "您还不是商家，请先提交入驻申请")
    if need_approved and as_int(merchant.get("status")) != MERCHANT_STATUS_APPROVED:
        raise MerchantError(403, "店铺尚未通过审核，暂不能进行该操作")
    return merchant


# ============================================================
# 兑换
# ============================================================
def redeem(cursor, user_id: int, product_id: int) -> dict:
    """用户用积分兑换商家商品/服务。

    写入顺序（**必须按此顺序**）：
    1. 读商品 + 商家（校验存在 / 商家已通过审核 / 商品上架 / 不是自己的店）
    2. `SELECT points ... FOR UPDATE` 校验余额（失败即 400，此时**尚无任何写入**）
    3. 条件扣库存（`stock>0` 才生效，杜绝超卖）
    4. INSERT 兑换单 → 拿 `lastrowid`
    5. `award_points(-points_cost, source=5, related_id=订单id)` 扣分并写流水

    第 5 步的 `related_id` 用订单 id：`points_log` 的唯一索引
    `uk_points_log_source(source, related_id, user_id)` 因此天然保证
    「一笔兑换只扣一次分」，重复调用会撞唯一键而非重复扣分。
    """
    now = datetime.now()
    cursor.execute(
        "SELECT p.id, p.merchant_id, p.title, p.points_cost, p.status, "
        "       m.name AS merchant_name, m.user_id AS merchant_user_id, m.status AS merchant_status "
        "FROM merchant_product p JOIN merchant m ON p.merchant_id = m.id "
        "WHERE p.id=%s LIMIT 1",
        (product_id,),
    )
    product = cursor.fetchone()
    if not product:
        raise MerchantError(404, "兑换商品不存在")

    if as_int(product.get("merchant_status")) != MERCHANT_STATUS_APPROVED:
        raise MerchantError(400, "该店铺暂未开放兑换")
    if as_int(product.get("status")) != PRODUCT_STATUS_ONLINE:
        raise MerchantError(400, "该商品已下架")

    merchant_user_id = product.get("merchant_user_id")
    if merchant_user_id is not None and as_int(merchant_user_id) == as_int(user_id):
        raise MerchantError(400, "不能兑换自己店铺的商品")

    points_cost = max(as_int(product.get("points_cost")), 0)
    product_title = product.get("title") or _FALLBACK_PRODUCT_TITLE

    # 余额校验（行锁）：points_cost=0 的免费商品跳过
    if points_cost > 0:
        cursor.execute("SELECT points FROM user WHERE id=%s FOR UPDATE", (user_id,))
        user_row = cursor.fetchone()
        if not user_row:
            raise MerchantError(404, "用户不存在")
        balance = as_int(user_row.get("points"))
        if balance < points_cost:
            raise MerchantError(
                400, f"积分不足：本次兑换需要 {points_cost} 积分，你当前有 {balance} 积分"
            )

    # 扣库存（条件更新，防超卖）
    cursor.execute(
        "UPDATE merchant_product SET stock=stock-1, sold_count=sold_count+1 "
        "WHERE id=%s AND status=%s AND stock>0",
        (product_id, PRODUCT_STATUS_ONLINE),
    )
    if cursor.rowcount == 0:
        raise MerchantError(400, "库存不足，该商品刚刚被兑完")

    order_no = generate_redemption_no(now)
    code = generate_verify_code(cursor)
    expires_at = now + timedelta(days=max(as_int(settings.redemption_code_expire_days), 1))
    cursor.execute(
        "INSERT INTO redemption_order "
        "(order_no, user_id, merchant_id, product_id, points_cost, status, code, expires_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (order_no, user_id, as_int(product.get("merchant_id")), product_id, points_cost,
         REDEMPTION_STATUS_PENDING, code, expires_at),
    )
    order_id = as_int(cursor.lastrowid)

    balance_after: int | None = None
    if points_cost > 0:
        balance_after = award_points(
            cursor,
            user_id,
            -points_cost,
            source=SOURCE_REDEEM,
            related_id=order_id,
            description=f"兑换「{product_title}」",
        )

    return {
        "order_id": order_id,
        "order_no": order_no,
        "code": code,
        "points_cost": points_cost,
        "product_title": product_title,
        "merchant_name": product.get("merchant_name") or "",
        "expires_at": expires_at,
        "points_balance": balance_after,
    }


# ============================================================
# 核销
# ============================================================
def verify_redemption(cursor, merchant_id: int, code: str) -> dict:
    """商家核销：把待核销的兑换单置为已核销。

    核销**不退积分、不动库存**——积分在兑换时已经扣掉，核销只是履约确认。
    """
    cursor.execute(
        "SELECT id FROM redemption_order WHERE code=%s AND merchant_id=%s LIMIT 1",
        (code, merchant_id),
    )
    row = cursor.fetchone()
    if not row:
        # 区分「码不存在」与「码是别家的」：前者 404，后者 403
        cursor.execute("SELECT merchant_id FROM redemption_order WHERE code=%s LIMIT 1", (code,))
        other = cursor.fetchone()
        if other:
            raise MerchantError(403, "该核销码不属于本店")
        raise MerchantError(404, "核销码不存在，请核对后重新输入")

    order_id = as_int(row.get("id"))
    # 条件更新：并发/连点时只有一个请求能拿到 rowcount=1
    cursor.execute(
        "UPDATE redemption_order SET status=%s, redeemed_at=NOW() "
        "WHERE id=%s AND merchant_id=%s AND status=%s AND expires_at>NOW()",
        (REDEMPTION_STATUS_REDEEMED, order_id, merchant_id, REDEMPTION_STATUS_PENDING),
    )
    if cursor.rowcount == 0:
        cursor.execute(
            "SELECT status FROM redemption_order WHERE id=%s LIMIT 1", (order_id,)
        )
        current = cursor.fetchone() or {}
        status = as_int(current.get("status"))
        if status == REDEMPTION_STATUS_REDEEMED:
            raise MerchantError(400, "该核销码已使用，请勿重复核销")
        if status == REDEMPTION_STATUS_EXPIRED:
            raise MerchantError(400, "该核销码已过期")
        if status == REDEMPTION_STATUS_CANCELLED:
            raise MerchantError(400, "该兑换单已取消")
        # status 仍是「待核销」→ 条件里唯一没过的就是 expires_at>NOW()
        # （后台过期任务每小时才扫一次，这一行可能还没被置为 3）
        raise MerchantError(400, "该核销码已过期")

    cursor.execute(
        "SELECT o.order_no, o.points_cost, o.redeemed_at, p.title, u.nickname "
        "FROM redemption_order o "
        "LEFT JOIN merchant_product p ON o.product_id = p.id "
        "LEFT JOIN user u ON o.user_id = u.id "
        "WHERE o.id=%s LIMIT 1",
        (order_id,),
    )
    detail = cursor.fetchone() or {}
    return {
        "success": True,
        "order_id": order_id,
        "order_no": detail.get("order_no") or "",
        "product_title": detail.get("title") or _FALLBACK_PRODUCT_TITLE,
        "points_cost": as_int(detail.get("points_cost")),
        "user_nickname": detail.get("nickname") or _FALLBACK_NICKNAME,
        "redeemed_at": as_datetime(detail.get("redeemed_at")),
    }


# ============================================================
# 过期处理（后台定时任务，自行开事务）
# ============================================================
def _find_expired_ids(limit: int) -> list[int]:
    now = datetime.now()
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM redemption_order "
                "WHERE status=%s AND expires_at<=%s ORDER BY id LIMIT %s",
                (REDEMPTION_STATUS_PENDING, now, limit),
            )
            return [as_int(row.get("id")) for row in cursor.fetchall()]


def _expire_one(order_id: int) -> bool:
    """处理单笔过期兑换单（**独立事务**）：置为已过期 + 原额退还积分。

    为什么每单一个独立事务而不是整批一个：
    退还积分走 `award_points`，若命中 `PointsAwardError`（同一单已退过），
    整批事务会被回滚——那一批里其它**本该成功**的退还就一起丢了。
    单笔独立事务让失败只影响自己，且失败后状态不会半途落库。

    退还用 `source=7`（兑换过期退还），与消耗用的 `source=5` 不同，
    因此同一笔兑换单可以同时存在「消耗」和「退还」两条流水，
    不会撞 `uk_points_log_source` 唯一索引。
    """
    now = datetime.now()
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT user_id, points_cost FROM redemption_order WHERE id=%s LIMIT 1",
                (order_id,),
            )
            row = cursor.fetchone()
            if not row:
                return False

            cursor.execute(
                "UPDATE redemption_order SET status=%s "
                "WHERE id=%s AND status=%s AND expires_at<=%s",
                (REDEMPTION_STATUS_EXPIRED, order_id, REDEMPTION_STATUS_PENDING, now),
            )
            if cursor.rowcount == 0:
                # 已被核销 / 已被其它进程置为过期 → 不重复处理
                return False

            cost = max(as_int(row.get("points_cost")), 0)
            if cost > 0:
                award_points(
                    cursor,
                    as_int(row.get("user_id")),
                    cost,
                    source=SOURCE_REDEEM_REFUND,
                    related_id=order_id,
                    description="兑换过期退还",
                )
            return True


def expire_redemptions() -> int:
    """扫描并处理所有已过期但状态仍为「待核销」的兑换单，返回处理单数。

    幂等性由三道闸共同保证：
    1. 条件更新 `status=1 AND expires_at<=now` —— 处理过的单不会再被选中；
    2. `points_log` 唯一索引（source=7 + related_id=订单id + user_id）——
       即使重复走到退还也会被数据库拦下；
    3. 单笔独立事务 —— 任一单失败不影响其它单。
    """
    total = 0
    for _ in range(EXPIRE_MAX_BATCHES):
        ids = _find_expired_ids(EXPIRE_BATCH_SIZE)
        if not ids:
            break
        progressed = 0
        for order_id in ids:
            try:
                if _expire_one(order_id):
                    progressed += 1
                    total += 1
            except PointsAwardError:
                logger.warning(
                    "兑换单 %s 的过期退还流水已存在，本次跳过（不影响其它单）", order_id, exc_info=True
                )
            except Exception:  # noqa: BLE001 — 单笔失败不拖垮整批
                logger.error("兑换单 %s 过期处理失败", order_id, exc_info=True)
        if progressed == 0:
            # 本批一单都没处理成功，再查还是同一批 → 直接退出，避免死循环
            break
    if total:
        logger.info("过期兑换单处理完成：%s 单已置为过期并退还积分", total)
    return total


async def expire_redemptions_loop() -> None:
    """后台过期扫描循环（每小时一次）。

    `expire_redemptions` 是同步阻塞的 pymysql 调用，因此用 `asyncio.to_thread`
    丢到线程池执行 —— 直接在事件循环里 await 会阻塞**所有** HTTP 请求。
    任务自身抛错只记日志、不中断循环，保证扫描长期存活。
    """
    import asyncio

    interval = max(int(settings.redemption_expire_interval_seconds), 60)
    while True:
        try:
            await asyncio.to_thread(expire_redemptions)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — 单轮失败不应终止循环
            logger.error("过期兑换单扫描失败: %s", exc, exc_info=True)
        await asyncio.sleep(interval)


# ============================================================
# 结算
# ============================================================
def calculate_commission(points_total: int, commission_rate) -> Decimal:
    """佣金 = 积分总额 × 积分汇率(元/积分) × 佣金比例%。

    例：1000 积分 × 0.01 元/积分 × 5% = 0.50 元。
    全程用 Decimal，避免浮点尾数写进 DECIMAL(10,2) 列。
    """
    rate = Decimal(str(commission_rate if commission_rate is not None else 0))
    yuan_per_point = Decimal(str(settings.merchant_points_to_yuan))
    amount = Decimal(max(as_int(points_total), 0)) * yuan_per_point * rate / Decimal(100)
    return amount.quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)


def parse_period(period: str | None) -> tuple[str, datetime, datetime]:
    """把 `YYYY-MM` 解析为 (周期字符串, 起, 止)，止为下月 1 日 0 点（左闭右开）。

    用「时间区间」而不是 `DATE_FORMAT(redeemed_at,'%Y-%m')` 比较：
    前者能吃到 `idx_merchant_status` / 时间索引，且避开 pymysql 里 `%` 转义坑。
    """
    raw = (period or datetime.now().strftime("%Y-%m")).strip()
    if not PERIOD_PATTERN.match(raw):
        raise MerchantError(400, "结算周期格式不正确，应为 YYYY-MM（如 2026-10）")
    year, month = int(raw[:4]), int(raw[5:7])
    start = datetime(year, month, 1)
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    return raw, start, end


def settle_merchant(cursor, merchant_id: int, period: str | None = None) -> dict:
    """结算某商家某周期的核销单，返回结算结果。

    统计口径：该周期内 `status=2（已核销）` 且 `redeemed_at` 落在区间内的兑换单。
    幂等：已结算（status=1）的同一 (merchant_id, period) 直接返回原记录，
    不重算、不重复写行（结算表没有唯一键，幂等靠这一层判断 + 单事务串行保证）。
    """
    period_str, start, end = parse_period(period)

    cursor.execute(
        "SELECT id, name, commission_rate FROM merchant WHERE id=%s LIMIT 1", (merchant_id,)
    )
    merchant = cursor.fetchone()
    if not merchant:
        raise MerchantError(404, "商家不存在")

    cursor.execute(
        "SELECT id, redemption_count, points_total, commission_amount, status, settled_at "
        "FROM merchant_settlement WHERE merchant_id=%s AND period=%s LIMIT 1",
        (merchant_id, period_str),
    )
    existing = cursor.fetchone()
    if existing and as_int(existing.get("status")) == SETTLEMENT_STATUS_SETTLED:
        return {
            "merchant_id": merchant_id,
            "merchant_name": merchant.get("name") or "",
            "period": period_str,
            "redemption_count": as_int(existing.get("redemption_count")),
            "points_total": as_int(existing.get("points_total")),
            "commission_amount": as_float(existing.get("commission_amount")),
            "status": SETTLEMENT_STATUS_SETTLED,
            "status_label": settlement_status_label(SETTLEMENT_STATUS_SETTLED),
            "settled_at": as_datetime(existing.get("settled_at")),
            "already_settled": True,
        }

    cursor.execute(
        "SELECT COUNT(*) AS c, COALESCE(SUM(points_cost), 0) AS p FROM redemption_order "
        "WHERE merchant_id=%s AND status=%s AND redeemed_at >= %s AND redeemed_at < %s",
        (merchant_id, REDEMPTION_STATUS_REDEEMED, start, end),
    )
    stat = cursor.fetchone() or {}
    count = as_int(stat.get("c"))
    points_total = as_int(stat.get("p"))
    commission = calculate_commission(points_total, merchant.get("commission_rate"))
    now = datetime.now()

    if existing:
        cursor.execute(
            "UPDATE merchant_settlement SET redemption_count=%s, points_total=%s, "
            "commission_amount=%s, status=%s, settled_at=%s WHERE id=%s",
            (count, points_total, str(commission), SETTLEMENT_STATUS_SETTLED, now,
             as_int(existing.get("id"))),
        )
    else:
        cursor.execute(
            "INSERT INTO merchant_settlement "
            "(merchant_id, period, redemption_count, points_total, commission_amount, status, settled_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (merchant_id, period_str, count, points_total, str(commission),
             SETTLEMENT_STATUS_SETTLED, now),
        )

    return {
        "merchant_id": merchant_id,
        "merchant_name": merchant.get("name") or "",
        "period": period_str,
        "redemption_count": count,
        "points_total": points_total,
        "commission_amount": float(commission),
        "status": SETTLEMENT_STATUS_SETTLED,
        "status_label": settlement_status_label(SETTLEMENT_STATUS_SETTLED),
        "settled_at": now,
        "already_settled": False,
    }


def to_money(value) -> Decimal:
    """任意数值 → 两位小数的 Decimal（写 DECIMAL(10,2) 列 / 出 JSON 前统一口径）。"""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        amount = Decimal("0")
    return amount.quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)


def merchant_settlement_summary(cursor, merchant: dict) -> dict:
    """商家结算自查（只读）：应得 / 佣金 / 实得 / 已结算 / 待结算一次算清。

    只读接口，**不改任何状态**（真正的出账仍由管理端 `POST /admin/merchant/settle` 触发）。

    口径说明（唯一一处容易算错的地方）：
    - `gross_amount`（应得）= 累计已核销积分 × 积分汇率，**未扣佣金**；
    - `commission_amount`（平台佣金）= gross × `merchant.commission_rate`%，
      与 `merchant_settlement.commission_amount` 完全同源（都走 `calculate_commission`）；
    - `settled_amount`（已结算）= 已结算批次的 `merchant_settlement.points_total` × 汇率，
      **同样用应得口径**，因此 `gross - settled` 就是待结算金额，商家一眼能对上；
    - 若管理员调过费率，已结算批次仍按当年落库的 `commission_amount` 展示，不重算。
    """
    merchant_id = as_int(merchant.get("id"))
    commission_rate = merchant.get("commission_rate")

    # 累计已核销（口径与 dashboard 的 total_redemptions 完全一致）
    cursor.execute(
        "SELECT COUNT(*) AS c, COALESCE(SUM(points_cost), 0) AS p FROM redemption_order "
        "WHERE merchant_id=%s AND status=%s",
        (merchant_id, REDEMPTION_STATUS_REDEEMED),
    )
    agg = cursor.fetchone() or {}
    redemption_count = as_int(agg.get("c"))
    points_total = as_int(agg.get("p"))

    # 已结算批次合计
    cursor.execute(
        "SELECT COUNT(*) AS c, COALESCE(SUM(points_total), 0) AS p, "
        "       COALESCE(SUM(commission_amount), 0) AS m, MAX(settled_at) AS t "
        "FROM merchant_settlement WHERE merchant_id=%s AND status=%s",
        (merchant_id, SETTLEMENT_STATUS_SETTLED),
    )
    settled_row = cursor.fetchone() or {}
    settled_count = as_int(settled_row.get("c"))
    settled_points = as_int(settled_row.get("p"))
    settled_commission = to_money(settled_row.get("m"))

    yuan_per_point = Decimal(str(settings.merchant_points_to_yuan))
    gross = to_money(Decimal(points_total) * yuan_per_point)
    commission = calculate_commission(points_total, commission_rate)
    settled_amount = to_money(Decimal(settled_points) * yuan_per_point)
    # 待结算不允许为负：费率/汇率被下调过时，已结算金额理论上可能超过按新汇率算的应得
    pending = gross - settled_amount
    if pending < 0:
        pending = Decimal("0.00")

    return {
        "merchant_id": merchant_id,
        "merchant_name": merchant.get("name") or "",
        "commission_rate": as_float(commission_rate),
        "points_to_yuan": as_float(settings.merchant_points_to_yuan),
        "redemption_count": redemption_count,
        "points_total": points_total,
        "gross_amount": float(gross),
        "commission_amount": float(commission),
        "net_amount": float(to_money(gross - commission)),
        "settled_points": settled_points,
        "settled_amount": float(settled_amount),
        "settled_commission": float(settled_commission),
        "pending_amount": float(pending),
        "settled_count": settled_count,
        "last_settled_at": as_datetime(settled_row.get("t")),
        "period": datetime.now().strftime("%Y-%m"),
    }


# ============================================================
# 数据看板
# ============================================================
def redemption_trend(cursor, days: int = 7, merchant_id: int | None = None) -> list[dict]:
    """近 N 日核销趋势（商家端看板与平台总览共用）。

    补齐没有核销的日期：前端画折线图需要连续的点，缺日期会让曲线断掉。
    `merchant_id=None` 表示平台全部商家。
    """
    today = date.today()
    day_start = datetime(today.year, today.month, today.day)
    trend_start = day_start - timedelta(days=max(days, 1) - 1)

    where = "status=%s AND redeemed_at >= %s"
    params: list = [REDEMPTION_STATUS_REDEEMED, trend_start]
    if merchant_id is not None:
        where += " AND merchant_id=%s"
        params.append(merchant_id)

    cursor.execute(
        f"SELECT DATE(redeemed_at) AS d, COUNT(*) AS c FROM redemption_order "
        f"WHERE {where} GROUP BY DATE(redeemed_at)",
        params,
    )
    counts: dict[str, int] = {}
    for row in cursor.fetchall():
        raw_day = row.get("d")
        key = raw_day.strftime("%Y-%m-%d") if hasattr(raw_day, "strftime") else str(raw_day)[:10]
        counts[key] = as_int(row.get("c"))

    trend = []
    for offset in range(max(days, 1)):
        day = trend_start + timedelta(days=offset)
        key = day.strftime("%Y-%m-%d")
        trend.append({"date": key, "count": counts.get(key, 0)})
    return trend


def merchant_dashboard(cursor, merchant_id: int) -> dict:
    """商家数据看板：今日/累计核销、去重用户、热销商品、近 7 日趋势。

    直接实时聚合 `redemption_order`，不读 `merchant_stats` 缓存表
    （该表按决策「建表但本期不写不读」，等前端埋点上线后再启用）。
    """
    today = date.today()
    day_start = datetime(today.year, today.month, today.day)
    day_end = day_start + timedelta(days=1)

    cursor.execute(
        "SELECT COUNT(*) AS c FROM redemption_order "
        "WHERE merchant_id=%s AND status=%s AND redeemed_at >= %s AND redeemed_at < %s",
        (merchant_id, REDEMPTION_STATUS_REDEEMED, day_start, day_end),
    )
    today_redemptions = as_int((cursor.fetchone() or {}).get("c"))

    cursor.execute(
        "SELECT COUNT(*) AS c, COUNT(DISTINCT user_id) AS u FROM redemption_order "
        "WHERE merchant_id=%s AND status=%s",
        (merchant_id, REDEMPTION_STATUS_REDEEMED),
    )
    agg = cursor.fetchone() or {}
    total_redemptions = as_int(agg.get("c"))
    unique_users = as_int(agg.get("u"))

    cursor.execute(
        "SELECT title, sold_count FROM merchant_product WHERE merchant_id=%s "
        "ORDER BY sold_count DESC, id ASC LIMIT 5",
        (merchant_id,),
    )
    popular_products = [
        {"title": row.get("title") or "", "sold_count": as_int(row.get("sold_count"))}
        for row in cursor.fetchall()
    ]

    return {
        "today_redemptions": today_redemptions,
        "total_redemptions": total_redemptions,
        "unique_users": unique_users,
        "popular_products": popular_products,
        "trend": redemption_trend(cursor, days=7, merchant_id=merchant_id),
    }


# ============================================================
# 只读查询（供智能体助手的 function-calling 调用）
# ============================================================
# 说明：下面两个函数是「智能体商家工具」的只读数据源，口径与
# `api/v1/merchant.py` 的 `list_shops` / `list_shop_products` 一致，
# 但**刻意不共用代码**：那两个接口是阶段一二已验证通过的实现，
# 把 SQL 抽出来改它们属于「不必要的重构」，有回归风险。
# 代价是与接口层约 8 行 SQL 重复，收益是接口层零改动。
#
# 与接口层的差异（有意为之）：
# - 只返回 LLM 需要的最小字段，**不含 logo_url**（带 exp/sig 的签名 URL 是噪音）
# - 查询失败不抛业务异常，交由工具层转成 {"error": ...} 给模型措辞

# 单次工具调用最多返回的条数（防止把整张表塞进模型上下文）
AGENT_SHOP_LIMIT = 20
AGENT_PRODUCT_LIMIT = 50


def list_approved_shops(cursor, category: str | None = None, limit: int = AGENT_SHOP_LIMIT) -> list[dict]:
    """列出已通过审核的商家（供智能体工具 get_merchant_list）。

    只返回已上线（status=已通过）的商家，与用户浏览积分商城的口径一致。
    """
    limit = max(1, min(AGENT_SHOP_LIMIT, as_int(limit) or AGENT_SHOP_LIMIT))
    category = (category or "").strip()

    where = "m.status=%s"
    params: list = [MERCHANT_STATUS_APPROVED]
    if category:
        where += " AND m.category=%s"
        params.append(category)

    cursor.execute(
        f"SELECT m.id, m.name, m.category, m.address, m.contact, m.description, "
        f"       (SELECT COUNT(*) FROM merchant_product p "
        f"        WHERE p.merchant_id = m.id AND p.status = {PRODUCT_STATUS_ONLINE}) AS product_count "
        f"FROM merchant m WHERE {where} ORDER BY m.id ASC LIMIT %s",
        params + [limit],
    )
    return [
        {
            "merchant_id": as_int(row.get("id")),
            "name": row.get("name") or "",
            "category": row.get("category") or "",
            "address": row.get("address") or "",
            "contact": row.get("contact") or "",
            "description": row.get("description") or "",
            "product_count": as_int(row.get("product_count")),
        }
        for row in cursor.fetchall()
    ]


def list_shop_products_by_id(
    cursor, merchant_id: int, keyword: str = "", limit: int = AGENT_PRODUCT_LIMIT
) -> dict | None:
    """取某商家的在售商品（供智能体工具 get_merchant_products）。

    商家不存在或未通过审核时返回 None，由工具层转成友好错误文案。
    """
    cursor.execute(
        "SELECT id, name, category, address, contact, status FROM merchant WHERE id=%s LIMIT 1",
        (as_int(merchant_id),),
    )
    merchant = cursor.fetchone()
    if not merchant or as_int(merchant.get("status")) != MERCHANT_STATUS_APPROVED:
        return None

    limit = max(1, min(AGENT_PRODUCT_LIMIT, as_int(limit) or AGENT_PRODUCT_LIMIT))
    keyword = (keyword or "").strip()

    conditions = ["merchant_id=%s", "status=%s"]
    params: list = [as_int(merchant.get("id")), PRODUCT_STATUS_ONLINE]
    if keyword:
        conditions.append("(title LIKE %s OR description LIKE %s)")
        kw = f"%{keyword}%"
        params.extend([kw, kw])

    cursor.execute(
        f"SELECT id, title, points_cost, stock, sold_count FROM merchant_product "
        f"WHERE {' AND '.join(conditions)} ORDER BY id ASC LIMIT %s",
        params + [limit],
    )
    products = []
    for row in cursor.fetchall():
        points_cost = as_int(row.get("points_cost"))
        products.append(
            {
                "product_id": as_int(row.get("id")),
                "title": row.get("title") or "",
                "points_cost": points_cost,
                # 0 积分显式标注为免费：与商家端/用户端「免费券」文案口径一致
                "is_free": points_cost == 0,
                "stock": as_int(row.get("stock")),
                "sold_count": as_int(row.get("sold_count")),
            }
        )

    return {
        "merchant": {
            "merchant_id": as_int(merchant.get("id")),
            "name": merchant.get("name") or "",
            "category": merchant.get("category") or "",
            "address": merchant.get("address") or "",
        },
        "products": products,
    }

