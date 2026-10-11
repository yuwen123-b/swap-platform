"""用户档案接口：查询/更新助老模式、无障碍模式、行动能力、高对比度、语言等持久化配置。"""
from fastapi import APIRouter, HTTPException

from app.core.response import success
from app.db.pool import connection
from app.schemas.user import ProfileResponse, ProfileUpdate

router = APIRouter()

# 白名单字段 -> 数据库列，避免任意字段更新
_COLUMN_MAP = {
    "elderly_mode": "elderly_mode",
    "accessibility_mode": "accessibility_mode",
    "mobility_level": "mobility_level",
    "high_contrast": "high_contrast",
    "language": "preferred_lang",
}


def _row_to_profile(row: dict) -> ProfileResponse:
    return ProfileResponse(
        user_id=row["id"],
        nickname=row.get("nickname"),
        elderly_mode=int(row.get("elderly_mode") or 0),
        accessibility_mode=row.get("accessibility_mode") or "normal",
        mobility_level=row.get("mobility_level") or "free",
        high_contrast=int(row.get("high_contrast") or 0),
        language=row.get("preferred_lang") or "zh_CN",
    )


@router.get("/profile/{user_id}")
def get_profile(user_id: int):
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, nickname, elderly_mode, accessibility_mode, mobility_level, "
                "high_contrast, preferred_lang FROM user WHERE id=%s LIMIT 1",
                (user_id,),
            )
            row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "用户不存在")
    return success(_row_to_profile(row).model_dump())


@router.put("/profile/{user_id}")
def update_profile(user_id: int, body: ProfileUpdate):
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(400, "没有需要更新的字段")
    sets = []
    params = []
    for field, column in _COLUMN_MAP.items():
        if field in data:
            sets.append(f"{column}=%s")
            params.append(data[field])
    params.append(user_id)
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"UPDATE user SET {', '.join(sets)} WHERE id=%s", params)
            if cursor.rowcount == 0:
                raise HTTPException(404, "用户不存在")
            cursor.execute(
                "SELECT id, nickname, elderly_mode, accessibility_mode, mobility_level, "
                "high_contrast, preferred_lang FROM user WHERE id=%s LIMIT 1",
                (user_id,),
            )
            row = cursor.fetchone()
    return success(_row_to_profile(row).model_dump())
