from fastapi import APIRouter, Depends, Query

from app.db.pool import connection
from app.routers.admin.deps import ok, require_role

router = APIRouter()

monitor_roles = require_role([1, 2])


@router.get("/ai/logs", dependencies=[Depends(monitor_roles)])
def list_ai_logs(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    api_name: str | None = None,
    status: int | None = None,
):
    conditions = ["1=1"]
    params: list = []
    if api_name:
        conditions.append("api_name=%s")
        params.append(api_name)
    if status is not None:
        conditions.append("status=%s")
        params.append(status)
    where = " AND ".join(conditions)
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM ai_log WHERE {where}", params)
            total = cursor.fetchone()["total"]
            cursor.execute(
                f"SELECT * FROM ai_log WHERE {where} ORDER BY id DESC LIMIT %s OFFSET %s",
                params + [size, (page - 1) * size],
            )
            rows = cursor.fetchall()
    return ok({"total": total, "list": rows})


@router.get("/ai/stats", dependencies=[Depends(monitor_roles)])
def ai_stats():
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS total, SUM(status=1) AS success, AVG(duration_ms) AS avg_duration FROM ai_log"
            )
            overall = cursor.fetchone()
            cursor.execute("SELECT COUNT(*) AS c FROM ai_log WHERE DATE(created_at)=CURDATE()")
            today = cursor.fetchone()["c"]
            cursor.execute(
                """SELECT api_name, COUNT(*) AS total, SUM(status=1) AS success, AVG(duration_ms) AS avg_duration
                   FROM ai_log GROUP BY api_name ORDER BY total DESC"""
            )
            by_api = cursor.fetchall()
    total = overall["total"] or 0
    success = int(overall["success"] or 0)
    return ok(
        {
            "total": total,
            "success": success,
            "success_rate": round(success / total, 4) if total else 0,
            "avg_duration_ms": round(float(overall["avg_duration"] or 0), 1),
            "today": today,
            "by_api": by_api,
        }
    )


@router.get("/ai/alerts", dependencies=[Depends(monitor_roles)])
def ai_alerts(limit: int = Query(20, ge=1, le=100)):
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM ai_log WHERE status=0 ORDER BY id DESC LIMIT %s", (limit,))
            rows = cursor.fetchall()
    return ok(rows)
