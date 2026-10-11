from fastapi import APIRouter, Depends

from app.db.pool import connection
from app.routers.admin.deps import ok, require_role

router = APIRouter()

# 仅超级管理员可访问
super_admin = require_role([1])


@router.get("/system/config", dependencies=[Depends(super_admin)])
def get_config():
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT config_key, config_value, description, updated_at FROM sys_config ORDER BY config_key ASC")
            rows = cursor.fetchall()
    return ok({row["config_key"]: row["config_value"] for row in rows})


@router.put("/system/config", dependencies=[Depends(super_admin)])
def update_config(configs: dict[str, str]):
    with connection() as conn:
        with conn.cursor() as cursor:
            for key, value in configs.items():
                cursor.execute(
                    "INSERT INTO sys_config (config_key, config_value) VALUES (%s,%s) ON DUPLICATE KEY UPDATE config_value=VALUES(config_value)",
                    (key, value),
                )
    return ok(message="配置已更新")
