"""管理端演示数据种子脚本（幂等，可重复运行）。

用法（在 agent_back 目录下）：
    .venv/Scripts/python.exe scripts/seed_admin_demo.py
"""
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.security import hash_password, new_salt  # noqa: E402
from app.db.pool import connection  # noqa: E402
from app.routers.admin.deps import hash_admin_password  # noqa: E402

random.seed(42)


def ensure_reject_reason_column(cursor) -> None:
    cursor.execute(
        "SELECT COUNT(*) AS c FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='item' AND COLUMN_NAME='reject_reason'"
    )
    if cursor.fetchone()["c"] == 0:
        cursor.execute("ALTER TABLE item ADD COLUMN reject_reason VARCHAR(255) NULL COMMENT '审核拒绝理由'")
        print("[seed] item.reject_reason 列已补齐")


def seed_admins(cursor) -> None:
    admins = [
        ("admin", "admin123", "超级管理员", 1),
        ("operator", "123456", "运营专员", 2),
        ("auditor", "123456", "审核员", 3),
    ]
    for username, pwd, real_name, role in admins:
        cursor.execute(
            "INSERT IGNORE INTO admin (username, password_hash, real_name, role, status) VALUES (%s,%s,%s,%s,1)",
            (username, hash_admin_password(pwd), real_name, role),
        )
    print(f"[seed] admin 行数影响: {cursor.rowcount}")


def seed_sys_config(cursor) -> None:
    configs = [
        ("platform_name", "社区旧物互换平台", "平台名称"),
        ("announcement", "欢迎来到社区旧物互换平台，闲置流转，邻里互助。", "平台公告"),
        ("contact", "400-800-1234", "客服联系方式"),
        ("audit_enabled", "1", "物品发布是否需要审核：1开启 0关闭"),
        ("points_publish", "10", "发布物品奖励积分"),
        ("points_exchange", "20", "完成一次交换奖励积分"),
        ("points_report_deduct", "50", "举报成立扣除积分"),
    ]
    for key, value, desc in configs:
        cursor.execute(
            "INSERT IGNORE INTO sys_config (config_key, config_value, description) VALUES (%s,%s,%s)",
            (key, value, desc),
        )
    print("[seed] sys_config 默认配置完成")


def seed_categories(cursor) -> list[int]:
    names = ["数码电子", "家居家电", "图书文具", "服饰鞋包", "母婴用品", "运动户外", "美妆个护", "其他闲置"]
    ids = []
    for name in names:
        cursor.execute("SELECT id FROM category WHERE name=%s LIMIT 1", (name,))
        row = cursor.fetchone()
        if row:
            ids.append(row["id"])
        else:
            cursor.execute("INSERT INTO category (name, parent_id, carbon_factor) VALUES (%s,0,%s)", (name, round(random.uniform(0.5, 5), 4)))
            ids.append(cursor.lastrowid)
    print(f"[seed] category 共 {len(ids)} 个")
    return ids


def seed_users(cursor) -> list[int]:
    demos = [
        ("13800000001", "陈晓明"), ("13800000002", "林芳"), ("13800000003", "王强"),
        ("13800000004", "赵敏"), ("13800000005", "刘洋"), ("13800000006", "孙丽"),
        ("13800000007", "周杰"), ("13800000008", "吴倩"), ("13800000009", "郑浩"),
        ("13800000010", "冯雪"),
    ]
    ids = []
    for i, (phone, nickname) in enumerate(demos):
        cursor.execute("SELECT id FROM user WHERE phone=%s LIMIT 1", (phone,))
        row = cursor.fetchone()
        if row:
            ids.append(row["id"])
            continue
        salt = new_salt()
        days_ago = random.randint(0, 30)
        created = datetime.now() - timedelta(days=days_ago)
        cursor.execute(
            "INSERT INTO user (phone, password_md5, salt, nickname, gender, points, credit_score, status, is_verified, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,100,1,1,%s)",
            (phone, hash_password("123456", salt), salt, nickname, random.randint(0, 2), random.randint(50, 500), created),
        )
        ids.append(cursor.lastrowid)
    print(f"[seed] user 共 {len(ids)} 个")
    return ids


# 状态枚举：1=在售 2=已换出 3=下架(含审核拒绝) 4=待审核
ITEM_TITLES = [
    ("九成新 iPad Air 4 64G", 1, "自用平板，无磕碰，配件齐全。", 1),
    ("宜家实木书架", 2, "搬家转让，八成新，需自提。", 1),
    ("《人类简史》等图书 5 本", 3, "正版图书，品相好，打包换。", 4),
    ("耐克跑鞋 42 码", 4, "只穿过两次，尺码不合转让。", 1),
    ("婴儿推车（可折叠）", 5, "孩子大了用不上，功能完好。", 4),
    ("捷安特山地车", 6, "骑行一年，保养良好。", 1),
    ("全新未拆封护肤品套装", 7, "朋友送的，肤质不合转让。", 2),
    ("小米电饭煲 4L", 2, "换新闲置，功能正常。", 1),
    ("Kindle Paperwhite", 1, "屏幕无划痕，续航正常。", 4),
    ("儿童乐高积木套装", 5, "已拼完，零件齐全带图纸。", 3),
    ("尤克里里（23 寸）", 8, "入门琴，送琴包和调音器。", 1),
    ("美的电风扇", 2, "夏天必备，三档风速。", 1),
]


def seed_items(cursor, user_ids: list[int], category_ids: list[int]) -> list[int]:
    cursor.execute("SELECT COUNT(*) AS c FROM item")
    if cursor.fetchone()["c"] > 0:
        cursor.execute("SELECT id FROM item")
        print("[seed] item 已存在，跳过")
        return [r["id"] for r in cursor.fetchall()]
    ids = []
    for i, (title, cat_idx, desc, status) in enumerate(ITEM_TITLES):
        created = datetime.now() - timedelta(days=random.randint(0, 6), hours=random.randint(0, 23))
        reject_reason = "图片不清晰，请重新上传实物照片" if status == 2 else None
        cursor.execute(
            "INSERT INTO item (user_id, category_id, title, description, brand, condition_level, original_price, "
            "exchange_mode, price, status, view_count, reject_reason, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,1,%s,%s,%s,%s,%s)",
            (
                random.choice(user_ids), category_ids[cat_idx - 1] if cat_idx <= len(category_ids) else category_ids[-1],
                title, desc, "", random.randint(1, 5), round(random.uniform(50, 3000), 2),
                round(random.uniform(10, 800), 2), status, random.randint(5, 300), reject_reason, created,
            ),
        )
        ids.append(cursor.lastrowid)
    print(f"[seed] item 新增 {len(ids)} 件")
    return ids


def seed_posts_comments(cursor, user_ids: list[int]) -> list[int]:
    cursor.execute("SELECT COUNT(*) AS c FROM post")
    if cursor.fetchone()["c"] > 0:
        cursor.execute("SELECT id FROM post")
        print("[seed] post 已存在，跳过")
        return [r["id"] for r in cursor.fetchall()]
    posts = [
        ("交换心得：旧书换到了心仪的台灯", "在平台挂了半个月的旧书，昨天终于换出去了，邻里面对面交易很放心。"),
        ("小区里有没有人想换婴儿用品？", "家里婴儿床、推车都闲置了，想换一些大孩子的玩具或者绘本。"),
        ("建议增加周末线下交换市集", "感觉线上聊完线下交易很方便，如果社区能定期办市集就更好了。"),
        ("第一次用 AI 估价，挺准的", "发布闲置时试了下 AI 估价，给的价格区间和心里预期差不多。"),
        ("求购一台二手打印机", "孩子上小学了，经常要打印资料，有闲置打印机的邻居请联系我。"),
    ]
    post_ids = []
    for title, content in posts:
        created = datetime.now() - timedelta(days=random.randint(0, 6), hours=random.randint(0, 23))
        cursor.execute(
            "INSERT INTO post (user_id, title, content, type, like_count, comment_count, status, created_at) "
            "VALUES (%s,%s,%s,1,%s,0,1,%s)",
            (random.choice(user_ids), title, content, random.randint(0, 20), created),
        )
        post_ids.append(cursor.lastrowid)
    comments = ["支持！闲置流转起来挺好", "我家正好有，私聊", "同感，平台越来越方便了", "顶一个，希望采纳", "请问还在吗？"]
    for pid in post_ids:
        for _ in range(random.randint(1, 3)):
            cursor.execute(
                "INSERT INTO comment (post_id, user_id, content) VALUES (%s,%s,%s)",
                (pid, random.choice(user_ids), random.choice(comments)),
            )
        cursor.execute("UPDATE post SET comment_count=(SELECT COUNT(*) FROM comment WHERE post_id=%s) WHERE id=%s", (pid, pid))
    print(f"[seed] post 新增 {len(post_ids)} 条及评论")
    return post_ids


def seed_orders(cursor, user_ids: list[int], item_ids: list[int]) -> None:
    cursor.execute("SELECT COUNT(*) AS c FROM `order`")
    if cursor.fetchone()["c"] > 0:
        print("[seed] order 已存在，跳过")
        return
    n = 0
    for i, item_id in enumerate(item_ids[:8]):
        buyer, seller = random.sample(user_ids, 2)
        status = (i % 5) + 1  # 1-5
        created = datetime.now() - timedelta(days=random.randint(0, 6), hours=random.randint(0, 23))
        completed = created + timedelta(days=1) if status == 5 else None
        cursor.execute(
            "INSERT INTO `order` (order_no, item_id, buyer_id, seller_id, exchange_type, price, status, meet_location, completed_at, created_at) "
            "VALUES (%s,%s,%s,%s,1,%s,%s,%s,%s,%s)",
            (
                f"SW{created.strftime('%Y%m%d')}{1000 + i}", item_id, buyer, seller,
                round(random.uniform(10, 500), 2), status, "社区中心广场", completed, created,
            ),
        )
        n += 1
    print(f"[seed] order 新增 {n} 条")


def seed_points_logs(cursor, user_ids: list[int]) -> None:
    cursor.execute("SELECT COUNT(*) AS c FROM points_log")
    if cursor.fetchone()["c"] > 0:
        print("[seed] points_log 已存在，跳过")
        return
    sources = [(1, 10, "发布物品奖励"), (2, 20, "完成交换奖励"), (3, 5, "每日签到"), (4, 50, "人工调整")]
    n = 0
    for uid in user_ids:
        for _ in range(random.randint(1, 3)):
            source, pts, desc = random.choice(sources)
            created = datetime.now() - timedelta(days=random.randint(0, 6))
            cursor.execute(
                "INSERT INTO points_log (user_id, points, source, description, created_at) VALUES (%s,%s,%s,%s,%s)",
                (uid, pts, source, desc, created),
            )
            n += 1
    print(f"[seed] points_log 新增 {n} 条")


def seed_reports(cursor, user_ids: list[int], item_ids: list[int], post_ids: list[int]) -> None:
    cursor.execute("SELECT COUNT(*) AS c FROM report")
    if cursor.fetchone()["c"] > 0:
        print("[seed] report 已存在，跳过")
        return
    rows = [
        (user_ids[0], 1, item_ids[0], "疑似虚假商品，图片与描述不符", 0, None, None),
        (user_ids[1], 2, post_ids[2], "帖子包含广告信息", 0, None, None),
        (user_ids[2], 3, user_ids[5], "该用户交易中存在欺诈行为", 1, 1, "已核实，扣除对方信用分并警告"),
        (user_ids[3], 1, item_ids[6], "商品为违禁品", 2, 1, "经核实为正常护肤品，举报不成立"),
    ]
    for reporter_id, ttype, tid, reason, status, handler_id, result in rows:
        created = datetime.now() - timedelta(days=random.randint(0, 5))
        handle_time = created + timedelta(hours=5) if status != 0 else None
        cursor.execute(
            "INSERT INTO report (reporter_id, target_type, target_id, reason, status, handler_id, handle_time, result, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (reporter_id, ttype, tid, reason, status, handler_id, handle_time, result, created),
        )
    print(f"[seed] report 新增 {len(rows)} 条")


def seed_ai_logs(cursor) -> None:
    cursor.execute("SELECT COUNT(*) AS c FROM ai_log")
    if cursor.fetchone()["c"] > 0:
        print("[seed] ai_log 已存在，跳过")
        return
    apis = ["pricing", "match", "negotiation"]
    n = 0
    for _ in range(20):
        status = 1 if random.random() > 0.15 else 0
        created = datetime.now() - timedelta(days=random.randint(0, 6), hours=random.randint(0, 23))
        cursor.execute(
            "INSERT INTO ai_log (api_name, request_body, response_body, status, duration_ms, error_msg, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (
                random.choice(apis), '{"demo": true}',
                '{"price_range": [100, 200]}' if status == 1 else None,
                status, random.randint(200, 3000),
                None if status == 1 else "模型响应超时", created,
            ),
        )
        n += 1
    print(f"[seed] ai_log 新增 {n} 条")


def main() -> None:
    with connection() as conn:
        with conn.cursor() as cursor:
            ensure_reject_reason_column(cursor)
            seed_admins(cursor)
            seed_sys_config(cursor)
            category_ids = seed_categories(cursor)
            user_ids = seed_users(cursor)
            item_ids = seed_items(cursor, user_ids, category_ids)
            post_ids = seed_posts_comments(cursor, user_ids)
            seed_orders(cursor, user_ids, item_ids)
            seed_points_logs(cursor, user_ids)
            seed_reports(cursor, user_ids, item_ids, post_ids)
            seed_ai_logs(cursor)
    print("[seed] 全部完成")


if __name__ == "__main__":
    main()
