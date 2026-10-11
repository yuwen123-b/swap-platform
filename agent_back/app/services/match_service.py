"""匹配服务：交接方式可行性评估。

行动能力受限（limited/assisted）的用户排除「自取」，
优先推荐「上门送达」或「志愿者代取」。
"""
from app.services import accessibility_service

# 交接方式枚举
SELF_PICKUP = "self_pickup"
DOOR_DELIVERY = "door_delivery"
VOLUNTEER_PICKUP = "volunteer_pickup"
ALL_METHODS = (SELF_PICKUP, DOOR_DELIVERY, VOLUNTEER_PICKUP)


def evaluate_handover(user_id: int) -> dict:
    """根据用户行动能力评估可选交接方式与推荐项。"""
    try:
        level = accessibility_service.get_profile(user_id)["mobility_level"]
    except ValueError:
        level = accessibility_service.MOBILITY_FREE

    if level in (accessibility_service.MOBILITY_LIMITED, accessibility_service.MOBILITY_ASSISTED):
        methods = [DOOR_DELIVERY, VOLUNTEER_PICKUP]
        recommended = DOOR_DELIVERY
    else:
        methods = list(ALL_METHODS)
        recommended = SELF_PICKUP
    return {"mobility_level": level, "methods": methods, "recommended": recommended}
