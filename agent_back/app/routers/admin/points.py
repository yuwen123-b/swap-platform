from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.pool import connection
from app.routers.admin.deps import ok, require_role
from app.services.points_service import SOURCE_ADMIN, award_points

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
            # 改用 points_service.award_points：统一在 UPDATE user.points 之后回读余额，
            # 让 points_log.balance 与 user.points 保持一致。
            # （原实现直接 INSERT，漏写 balance，落库恒为 0，与其它来源的流水不一致）
            #
            # related_id 必须为 None：points_log 的唯一索引
            # uk_points_log_source(source, related_id, user_id) 是「同一笔业务不重复发放」的
            # 数据库级闸门，而管理员调整每次都是**独立事件**，不存在「同一笔业务」的语义。
            # MySQL 唯一索引不约束 NULL，写 NULL 才能让同一管理员对同一用户反复加分/扣分；
            # 若沿用 admin_id，第二次调整就会撞唯一键被拒（409）。
            award_points(
                cursor,
                req.user_id,
                req.points,
                source=SOURCE_ADMIN,
                related_id=None,
                description=f"[管理员调整] {req.reason}",
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
