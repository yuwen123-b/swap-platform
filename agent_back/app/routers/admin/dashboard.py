from datetime import date, timedelta

from fastapi import APIRouter, Depends

from app.db.pool import connection
from app.routers.admin.deps import ok, require_role

router = APIRouter()

read_roles = require_role([1, 2, 3])


@router.get("/dashboard/overview", dependencies=[Depends(read_roles)])
def overview():
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS c FROM user")
            user_total = cursor.fetchone()["c"]
            cursor.execute("SELECT COUNT(*) AS c FROM item")
            item_total = cursor.fetchone()["c"]
            cursor.execute("SELECT COUNT(*) AS c FROM `order`")
            order_total = cursor.fetchone()["c"]
            cursor.execute("SELECT COUNT(*) AS c FROM post")
            post_total = cursor.fetchone()["c"]
            cursor.execute("SELECT COUNT(*) AS c FROM user WHERE DATE(created_at)=CURDATE()")
            today_users = cursor.fetchone()["c"]
            cursor.execute("SELECT COUNT(*) AS c FROM item WHERE DATE(created_at)=CURDATE()")
            today_items = cursor.fetchone()["c"]
            cursor.execute("SELECT COUNT(*) AS c FROM `order` WHERE DATE(created_at)=CURDATE()")
            today_orders = cursor.fetchone()["c"]
            cursor.execute("SELECT COUNT(*) AS c FROM item WHERE status=4")
            pending_items = cursor.fetchone()["c"]
            cursor.execute("SELECT COUNT(*) AS c FROM report WHERE status=0")
            pending_reports = cursor.fetchone()["c"]
    return ok(
        {
            "user_total": user_total,
            "item_total": item_total,
            "order_total": order_total,
            "post_total": post_total,
            "today_users": today_users,
            "today_items": today_items,
            "today_orders": today_orders,
            "pending_items": pending_items,
            "pending_reports": pending_reports,
        }
    )


@router.get("/dashboard/trends", dependencies=[Depends(read_roles)])
def trends():
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT DATE(created_at) AS day, COUNT(*) AS c FROM item
                   WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 6 DAY)
                   GROUP BY DATE(created_at)"""
            )
            item_rows = {str(r["day"]): r["c"] for r in cursor.fetchall()}
            cursor.execute(
                """SELECT DATE(created_at) AS day, COUNT(*) AS c FROM `order`
                   WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 6 DAY)
                   GROUP BY DATE(created_at)"""
            )
            order_rows = {str(r["day"]): r["c"] for r in cursor.fetchall()}
            cursor.execute(
                """SELECT c.name, COUNT(i.id) AS c FROM category c
                   LEFT JOIN item i ON i.category_id=c.id
                   GROUP BY c.id, c.name ORDER BY c DESC LIMIT 6"""
            )
            hot_categories = cursor.fetchall()
            cursor.execute(
                """SELECT id, nickname, exchange_count, points FROM user
                   ORDER BY exchange_count DESC, points DESC LIMIT 5"""
            )
            active_users = cursor.fetchall()
    start = date.today() - timedelta(days=6)
    days = [str(start + timedelta(days=i)) for i in range(7)]
    return ok(
        {
            "days": days,
            "item_trend": [item_rows.get(d, 0) for d in days],
            "order_trend": [order_rows.get(d, 0) for d in days],
            "hot_categories": hot_categories,
            "active_users": active_users,
        }
    )
