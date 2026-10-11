from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.pool import connection
from app.routers.admin.deps import ok, require_role

router = APIRouter()

read_roles = require_role([1, 2, 3])
write_roles = require_role([1, 2])
super_admin = require_role([1])

RULE_KEYS = ("points_publish", "points_exchange", "points_report_deduct")


class PointsAdjust(BaseModel):
    user_id: int
    points: int = Field(description="正数加分，负数扣分")
    reason: str = Field(min_length=1, max_length=100)


@router.get("/points/logs", dependencies=[Depends(read_roles)])
def list_points_logs(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    keyword: str | None = None,
):
    conditions = ["1=1"]
    params: list = []
    if keyword:
        conditions.append("(u.nickname LIKE %s OR l.description LIKE %s)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    where = " AND ".join(conditions)
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) AS total FROM points_log l LEFT JOIN user u ON l.user_id=u.id WHERE {where}", params
            )
            total = cursor.fetchone()["total"]
            cursor.execute(
                f"""SELECT l.*, u.nickname
                    FROM points_log l LEFT JOIN user u ON l.user_id=u.id
                    WHERE {where} ORDER BY l.id DESC LIMIT %s OFFSET %s""",
                params + [size, (page - 1) * size],
            )
            rows = cursor.fetchall()
    return ok({"total": total, "list": rows})


@router.post("/points/adjust", dependencies=[Depends(write_roles)])
def adjust_points(req: PointsAdjust, admin: dict = Depends(write_roles)):
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, points FROM user WHERE id=%s LIMIT 1", (req.user_id,))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(404, "用户不存在")
            cursor.execute("UPDATE user SET points=points+%s WHERE id=%s", (req.points, req.user_id))
            cursor.execute(
                "INSERT INTO points_log (user_id, points, source, related_id, description) VALUES (%s,%s,4,%s,%s)",
                (req.user_id, req.points, admin["admin_id"], f"[管理员调整] {req.reason}"),
            )
    return ok(message="积分调整成功")


@router.get("/points/rules", dependencies=[Depends(read_roles)])
def get_rules():
    with connection() as conn:
        with conn.cursor() as cursor:
            placeholders = ",".join(["%s"] * len(RULE_KEYS))
            cursor.execute(
                f"SELECT config_key, config_value, description FROM sys_config WHERE config_key IN ({placeholders})",
                list(RULE_KEYS),
            )
            rows = cursor.fetchall()
    return ok({row["config_key"]: row["config_value"] for row in rows})


@router.put("/points/rules", dependencies=[Depends(super_admin)])
def update_rules(rules: dict[str, str]):
    with connection() as conn:
        with conn.cursor() as cursor:
            for key, value in rules.items():
                if key not in RULE_KEYS:
                    continue
                cursor.execute(
                    "INSERT INTO sys_config (config_key, config_value) VALUES (%s,%s) ON DUPLICATE KEY UPDATE config_value=VALUES(config_value)",
                    (key, value),
                )
    return ok(message="积分规则已更新")
