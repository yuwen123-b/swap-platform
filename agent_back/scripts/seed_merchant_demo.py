"""商家工作台演示数据脚本（幂等、可回滚）。

【为什么需要它】
5 家种子商家的 `user_id` 全是 NULL（`ensure_merchant_seed` 刻意不绑账号），
而且 `redemption_order` / `merchant_settlement` 建表后都是 0 行 ——
于是**没有任何真实账号能登录工作台，看板与核销历史也全是空的**。
本脚本一次性解决这两件事：
  1. 把指定账号绑定成「社区打印店」的店主（`merchant.user_id`）；
  2. 造 10 单兑换记录，覆盖 待核销 / 已核销 / 已过期 三种状态，
     已核销的时间刻意分散在近 7 天，让看板的趋势柱状图有数据。

【用法】（在 agent_back 目录下）
    # 绑定账号 15 为店主 + 造演示数据（默认买家取积分最高的非店主账号）
    .venv/Scripts/python.exe scripts/seed_merchant_demo.py --owner-id 15

    # 指定买家
    .venv/Scripts/python.exe scripts/seed_merchant_demo.py --owner-id 15 --buyer-id 12

    # 清除全部演示数据（含积分 / 库存复原；默认不解绑店主）
    .venv/Scripts/python.exe scripts/seed_merchant_demo.py --clean

    # 清除演示数据并把店主解绑回 NULL
    .venv/Scripts/python.exe scripts/seed_merchant_demo.py --clean --unbind

【幂等与回滚】
- 演示兑换单的 `order_no` 统一以 `DEMORD` 开头、核销码统一以 `90` 开头（其中一单是
  `012345`，专门用来演示「前导 0 核销码」这条最容易踩的坑）；
- 每次运行前先 `_cleanup()` 清掉上一轮演示数据（含对应的 `points_log` 流水、
  `user.points` 与 `merchant_product.stock/sold_count` 复原），因此**反复运行不会累积**；
- 积分一致性：待核销/已核销的单子真实扣分（source=5），已过期的单子扣分后再退还
  （source=5 + source=7，净额为 0），与线上 `expire_redemptions` 定时任务的口径一致。
"""
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.pool import connection  # noqa: E402

DEMO_ORDER_PREFIX = "DEMORD"
DEMO_CODE_PREFIX = "90"
# 演示期间的积分补足走 source=4（管理员调整）+ 固定 related_id，
# 这样清理时能精确定位并还原，不会误删真实流水
DEMO_ADJUST_SOURCE = 4
DEMO_ADJUST_RELATED_ID = 900001

SOURCE_REDEEM = 5
SOURCE_REDEEM_REFUND = 7

DEFAULT_MERCHANT_ID = 1  # 社区打印店

# (状态, 数量, 说明)  —— 状态：1待核销 2已核销 3已过期
PLAN = [
    (2, 4, "已核销：核销时间分散在近 7 天，支撑看板趋势图"),
    (1, 4, "待核销：可用来演示核销页"),
    (3, 2, "已过期：积分已原额退还"),
]

# 已核销单的时间偏移（天）——刻意覆盖今天 / 昨天 / 3 天前，让柱状图有 4 根柱子
REDEEMED_DAY_OFFSETS = [0, 0, 1, 3]


def _scalar(cursor, sql, params=None):
    cursor.execute(sql, params or ())
    row = cursor.fetchone()
    if not row:
        return None
    return list(row.values())[0]


def _cleanup(cursor, merchant_id: int, verbose: bool = True) -> None:
    """清除上一轮演示数据，并把积分 / 库存还原（幂等，可反复调用）。"""
    like_no = f"{DEMO_ORDER_PREFIX}%"
    cursor.execute(
        "SELECT id, user_id, product_id, points_cost, status FROM redemption_order "
        "WHERE order_no LIKE %s",
        (like_no,),
    )
    rows = cursor.fetchall()
    if not rows:
        if verbose:
            print("[clean] 无演示兑换单，跳过")
        return

    # 待核销 + 已核销 的单子是「当前已扣分」的；已过期单子已退还，净额为 0
    spent_by_user: dict[int, int] = {}
    for row in rows:
        if int(row["status"]) in (1, 2):
            spent_by_user[int(row["user_id"])] = spent_by_user.get(int(row["user_id"]), 0) + int(
                row["points_cost"] or 0
            )
        # 库存/销量按「每单各减 1 / 加 1」反向复原
        cursor.execute(
            "UPDATE merchant_product SET stock=stock+1, sold_count=GREATEST(sold_count-1, 0) "
            "WHERE id=%s",
            (row["product_id"],),
        )

    order_ids = [int(row["id"]) for row in rows]
    placeholders = ",".join(["%s"] * len(order_ids))
    cursor.execute(
        f"DELETE FROM points_log WHERE related_id IN ({placeholders}) "
        f"AND source IN (%s, %s)",
        order_ids + [SOURCE_REDEEM, SOURCE_REDEEM_REFUND],
    )
    removed_logs = cursor.rowcount

    # 退还「已扣未退」的积分
    for user_id, points in spent_by_user.items():
        if points > 0:
            cursor.execute("UPDATE user SET points=points+%s WHERE id=%s", (points, user_id))

    # 归还演示期间的积分补足
    cursor.execute(
        "SELECT user_id, points FROM points_log "
        "WHERE source=%s AND related_id=%s",
        (DEMO_ADJUST_SOURCE, DEMO_ADJUST_RELATED_ID),
    )
    for row in cursor.fetchall():
        cursor.execute(
            "UPDATE user SET points=points-%s WHERE id=%s",
            (abs(int(row["points"] or 0)), int(row["user_id"])),
        )
    cursor.execute(
        "DELETE FROM points_log WHERE source=%s AND related_id=%s",
        (DEMO_ADJUST_SOURCE, DEMO_ADJUST_RELATED_ID),
    )

    cursor.execute(f"DELETE FROM redemption_order WHERE order_no LIKE %s", (like_no,))
    print(
        f"[clean] 已删除 {len(rows)} 张演示兑换单 / {removed_logs} 条积分流水，"
        f"并为 {len(spent_by_user)} 个账号还原积分与库存"
    )


def _resolve_owner(cursor, args) -> int | None:
    if args.owner_id:
        return int(args.owner_id)
    if args.owner_phone:
        user_id = _scalar(cursor, "SELECT id FROM user WHERE phone=%s LIMIT 1", (args.owner_phone,))
        if not user_id:
            raise SystemExit(f"[err] 找不到手机号 {args.owner_phone} 对应的账号")
        return int(user_id)
    return None


def _bind_owner(cursor, merchant_id: int, owner_id: int) -> None:
    cursor.execute(
        "UPDATE merchant SET user_id=NULL WHERE user_id=%s AND id<>%s", (owner_id, merchant_id)
    )
    cursor.execute("UPDATE merchant SET user_id=%s WHERE id=%s", (owner_id, merchant_id))
    print(f"[bind] 商家 #{merchant_id} 已绑定到账号 #{owner_id}")


def _pick_buyer(cursor, owner_id: int | None, explicit: int | None) -> dict:
    if explicit:
        cursor.execute("SELECT id, nickname, points FROM user WHERE id=%s LIMIT 1", (explicit,))
        row = cursor.fetchone()
        if not row:
            raise SystemExit(f"[err] 买家账号 #{explicit} 不存在")
        return row
    cursor.execute(
        "SELECT id, nickname, points FROM user WHERE id<>%s ORDER BY points DESC, id ASC LIMIT 1",
        (owner_id or 0,),
    )
    row = cursor.fetchone()
    if not row:
        raise SystemExit("[err] 数据库里只有一个账号，无法演示「他人兑换」")
    return row


def seed(args) -> None:
    merchant_id = int(args.merchant_id)
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, name, status FROM merchant WHERE id=%s LIMIT 1", (merchant_id,)
            )
            merchant = cursor.fetchone()
            if not merchant:
                raise SystemExit(f"[err] 商家 #{merchant_id} 不存在")
            if int(merchant["status"]) != 1:
                raise SystemExit(
                    f"[err] 商家 #{merchant_id} 当前状态为 {merchant['status']}（需为 1 已通过）"
                )

            # 先清上一轮（含积分/库存还原），保证反复运行不累积
            _cleanup(cursor, merchant_id)

            owner_id = _resolve_owner(cursor, args)
            if owner_id:
                _bind_owner(cursor, merchant_id, owner_id)

            cursor.execute(
                "SELECT id, title, points_cost FROM merchant_product "
                "WHERE merchant_id=%s ORDER BY id ASC LIMIT 2",
                (merchant_id,),
            )
            products = cursor.fetchall()
            if not products:
                raise SystemExit(f"[err] 商家 #{merchant_id} 还没有商品，无法造兑换单")

            buyer = _pick_buyer(cursor, owner_id, args.buyer_id)
            buyer_id = int(buyer["id"])
        print(f"[seed] 商家：#{merchant_id} {merchant['name']}")
        print(f"[seed] 买家：#{buyer_id} {buyer.get('nickname') or ''}（当前 {buyer['points']} 积分）")
        print(f"[seed] 商品：{[(int(p['id']), p['title'], int(p['points_cost'])) for p in products]}")

        with conn.cursor() as cursor:
            # 计算「当前需扣除」的积分（待核销 + 已核销），不足则补足
            needs = 0
            plan_rows = []
            index = 0
            for status, count, _desc in PLAN:
                for _ in range(count):
                    product = products[index % len(products)]
                    index += 1
                    points_cost = int(product["points_cost"] or 0)
                    if status in (1, 2):
                        needs += points_cost
                    plan_rows.append((status, product, points_cost))

            balance = int(buyer["points"] or 0)
            if balance < needs:
                topup = needs - balance + 100  # 多补 100，让买家余额看起来是正常状态
                cursor.execute("UPDATE user SET points=points+%s WHERE id=%s", (topup, buyer_id))
                cursor.execute(
                    "INSERT INTO points_log (user_id, points, balance, source, related_id, description) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    (buyer_id, topup, balance + topup, DEMO_ADJUST_SOURCE,
                     DEMO_ADJUST_RELATED_ID, "演示数据积分补足"),
                )
                print(f"[seed] 买家积分不足，已补足 {topup} 分（可在 --clean 时还原）")

            now = datetime.now()
            running = int(
                _scalar(cursor, "SELECT points FROM user WHERE id=%s", (buyer_id,)) or 0
            )
            created = []
            redeemed_index = 0

            for seq, (status, product, points_cost) in enumerate(plan_rows, start=1):
                product_id = int(product["id"])
                # 演示核销码：整批固定 6 位；第 3 单刻意用 012345 演示「前导 0」
                code = "012345" if seq == 3 else f"{DEMO_CODE_PREFIX}{seq:04d}"
                order_no = f"{DEMO_ORDER_PREFIX}{seq:06d}"

                if status == 2:
                    days = REDEEMED_DAY_OFFSETS[redeemed_index % len(REDEEMED_DAY_OFFSETS)]
                    redeemed_index += 1
                    redeemed_at = now - timedelta(days=days, hours=seq)
                    expires_at = now + timedelta(days=max(30 - days, 1))
                elif status == 3:
                    redeemed_at = None
                    expires_at = now - timedelta(days=2)
                else:
                    redeemed_at = None
                    expires_at = now + timedelta(days=30)

                # 扣库存（与线上 redeem 一致：stock-1, sold_count+1）
                cursor.execute(
                    "UPDATE merchant_product SET stock=stock-1, sold_count=sold_count+1 WHERE id=%s",
                    (product_id,),
                )

                cursor.execute(
                    "INSERT INTO redemption_order "
                    "(order_no, user_id, merchant_id, product_id, points_cost, status, code, "
                    " redeemed_at, expires_at, created_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (order_no, buyer_id, merchant_id, product_id, points_cost, status, code,
                     redeemed_at, expires_at, (redeemed_at or now - timedelta(hours=seq))),
                )
                order_id = int(cursor.lastrowid)
                created.append((order_id, status, code))

                if points_cost > 0:
                    # 扣分（source=5）；已过期的再退分（source=7），净额 0
                    running -= points_cost
                    cursor.execute(
                        "INSERT INTO points_log (user_id, points, balance, source, related_id, description) "
                        "VALUES (%s,%s,%s,%s,%s,%s)",
                        (buyer_id, -points_cost, running, SOURCE_REDEEM, order_id,
                         f"演示兑换 {product['title']}"),
                    )
                    if status == 3:
                        running += points_cost
                        cursor.execute(
                            "INSERT INTO points_log (user_id, points, balance, source, related_id, description) "
                            "VALUES (%s,%s,%s,%s,%s,%s)",
                            (buyer_id, points_cost, running, SOURCE_REDEEM_REFUND, order_id,
                             "兑换过期退还"),
                        )
            buyer_id_for_update = buyer_id

        with conn.cursor() as cursor:
            cursor.execute("UPDATE user SET points=%s WHERE id=%s", (running, buyer_id_for_update))

    print()
    print(f"[done] 已生成 {len(created)} 张演示兑换单：")
    for order_id, status, code in created:
        label = {1: "待核销", 2: "已核销", 3: "已过期"}.get(status, str(status))
        print(f"        #{order_id:<6} {label}  核销码 {code}")
    print()
    print("[done] 下一步：")
    print("        1) 用店主账号登录 → 访问 /merchant/dashboard 看看板（4 张卡 + Top5 + 7 天趋势）")
    print("        2) 访问 /merchant/verify 输入上面的核销码（试 012345 验证前导 0）")
    print("        3) 访问 /merchant/settings 看「佣金与结算」自查")
    print("        4) 演示完执行 --clean 清除演示数据")


def clean(args) -> None:
    merchant_id = int(args.merchant_id)
    with connection() as conn:
        with conn.cursor() as cursor:
            _cleanup(cursor, merchant_id)
            if args.unbind:
                cursor.execute("UPDATE merchant SET user_id=NULL WHERE id=%s", (merchant_id,))
                print(f"[clean] 商家 #{merchant_id} 已解绑店主（user_id = NULL）")
    print("[clean] 完成")


def main() -> None:
    parser = argparse.ArgumentParser(description="商家工作台演示数据（幂等，可 --clean 回滚）")
    parser.add_argument("--merchant-id", default=DEFAULT_MERCHANT_ID,
                        help=f"演示商家 ID（默认 {DEFAULT_MERCHANT_ID} 社区打印店）")
    parser.add_argument("--owner-id", help="要绑定为店主的用户 ID（与 --owner-phone 二选一）")
    parser.add_argument("--owner-phone", help="要绑定为店主账号的手机号")
    parser.add_argument("--buyer-id", help="兑换演示数据的买家账号（默认取积分最高的非店主账号）")
    parser.add_argument("--clean", action="store_true", help="只清除演示数据（含积分/库存还原）")
    parser.add_argument("--unbind", action="store_true", help="配合 --clean：把店主解绑回 NULL")
    args = parser.parse_args()

    if args.clean:
        clean(args)
        return

    if not args.owner_id and not args.owner_phone:
        print("[warn] 未指定 --owner-id / --owner-phone：本次不绑定店主。")
        print("       如需绑定，执行：UPDATE merchant SET user_id = <账号ID> WHERE id = 1;")
    seed(args)


if __name__ == "__main__":
    main()
