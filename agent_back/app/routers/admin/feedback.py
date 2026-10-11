from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query

from app.db.pool import connection
from app.routers.admin.deps import ok, require_role

router = APIRouter()

_roles = require_role([1, 2])


@router.get("/feedback/list", dependencies=[Depends(_roles)])
def list_feedback(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    sentiment: str | None = None,
):
    conditions = ["1=1"]
    params: list = []
    if sentiment in ("positive", "neutral", "negative"):
        conditions.append("sentiment=%s")
        params.append(sentiment)
    where = " AND ".join(conditions)
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM platform_feedback WHERE {where}", params)
            total = cursor.fetchone()["total"]
            cursor.execute(
                f"""SELECT f.*, u.nickname AS user_nickname
                    FROM platform_feedback f LEFT JOIN user u ON f.user_id = u.id
                    WHERE {where} ORDER BY f.id DESC LIMIT %s OFFSET %s""",
                params + [size, (page - 1) * size],
            )
            rows = cursor.fetchall()
    return ok({"total": total, "list": rows})


@router.get("/feedback/stats", dependencies=[Depends(_roles)])
def feedback_stats():
    """情感分布统计 + 近 7 日趋势。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS total, SUM(sentiment='positive') AS positive, "
                "SUM(sentiment='neutral') AS neutral, SUM(sentiment='negative') AS negative, "
                "COALESCE(AVG(rating),0) AS avg_rating FROM platform_feedback"
            )
            row = cursor.fetchone()
            cursor.execute(
                """SELECT DATE(created_at) AS day, COUNT(*) AS c,
                          SUM(sentiment='positive') AS positive,
                          SUM(sentiment='neutral') AS neutral,
                          SUM(sentiment='negative') AS negative
                   FROM platform_feedback
                   WHERE created_at >= CURDATE() - INTERVAL 6 DAY
                   GROUP BY DATE(created_at)"""
            )
            by_day = {str(r["day"]): r for r in cursor.fetchall()}

    trend = []
    for offset in range(6, -1, -1):
        day = (date.today() - timedelta(days=offset)).isoformat()
        r = by_day.get(day)
        trend.append(
            {
                "day": day[5:],
                "total": int(r["c"]) if r else 0,
                "positive": int(r["positive"]) if r else 0,
                "neutral": int(r["neutral"]) if r else 0,
                "negative": int(r["negative"]) if r else 0,
            }
        )
    return ok(
        {
            "total": int(row["total"] or 0),
            "positive": int(row["positive"] or 0),
            "neutral": int(row["neutral"] or 0),
            "negative": int(row["negative"] or 0),
            "avg_rating": round(float(row["avg_rating"] or 0), 1),
            "trend": trend,
        }
    )
