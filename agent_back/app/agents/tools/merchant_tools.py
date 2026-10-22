"""商家 / 积分类工具：供智能体助手通过 function-calling 调用。

契约与 `agent.py` 内联的 `_ITEM_SEARCH_TOOL` 完全同构（OpenAI function-calling schema）。

【三条设计约定】
1. **只读**：三个工具只查不写，不产生任何副作用。
2. **不抛异常**：查询失败一律返回 `{"error": "..."}` 字符串，把措辞交给 LLM，
   避免一个工具抖动就让整轮对话降级。
3. **不接受 user_id 参数**：`get_points_balance` 查的永远是**当前提问用户**，
   由服务端通过 `viewer_user_id` 注入。若让 LLM 传 user_id，模型可能编造 id 去查他人积分。

返回值统一为 **JSON 字符串**（与 `agent._call_item_tool` 的契约一致），
由 agent.py 直接塞进 `role="tool"` 消息回填给模型。
"""
import json
import logging

from app.db.pool import connection
from app.services import merchant_service, points_service

logger = logging.getLogger(__name__)

GET_MERCHANT_LIST = "get_merchant_list"
GET_MERCHANT_PRODUCTS = "get_merchant_products"
GET_POINTS_BALANCE = "get_points_balance"

# 单次工具调用最多返回的条数（防止把整张表塞进模型上下文）
MAX_MERCHANT_ROWS = 20
MAX_PRODUCT_ROWS = 50

_GET_MERCHANT_LIST_TOOL = {
    "type": "function",
    "function": {
        "name": GET_MERCHANT_LIST,
        "description": (
            "列出平台上已通过审核的社区商家（积分商城的店铺）。"
            "当用户询问'有哪些商家'、'哪里有打印店/便利店/理发店'、"
            "'能兑换什么服务'时调用。返回 merchant_id、名称、类型、地址、联系方式与在售商品数。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": (
                        "店铺类型（可选，精确匹配）：打印 / 便利店 / 理发 / 回收 / 家政。"
                        "用户没有明确指定类型时不要传。"
                    ),
                },
            },
            "required": [],
        },
    },
}

_GET_MERCHANT_PRODUCTS_TOOL = {
    "type": "function",
    "function": {
        "name": GET_MERCHANT_PRODUCTS,
        "description": (
            "查询某个商家在售的商品（含所需积分、库存）。"
            "当用户问'某家店有什么'、'XX 多少钱积分'、'我能换什么'时调用。"
            "merchant_id 必须先通过 get_merchant_list 拿到，不要猜测。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "merchant_id": {
                    "type": "integer",
                    "description": "商家 ID（来自 get_merchant_list 返回的 merchant_id）",
                },
                "keyword": {
                    "type": "string",
                    "description": "商品关键词（可选），如'打印'、'纸巾'、'理发'",
                },
            },
            "required": ["merchant_id"],
        },
    },
}

_GET_POINTS_BALANCE_TOOL = {
    "type": "function",
    "function": {
        "name": GET_POINTS_BALANCE,
        "description": (
            "查询**当前提问用户**的积分余额、等级、碳减排量与完成交换次数。"
            "当用户问'我有多少积分'、'我还差多少分能换 XX'、'我是什么等级'时调用。"
            "无需任何参数（用户身份由服务端识别，不会也无需由你提供）。"
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

# 供 agent.py 并入「物品/商家查询」分支的工具列表
MERCHANT_TOOLS = [_GET_MERCHANT_LIST_TOOL, _GET_MERCHANT_PRODUCTS_TOOL, _GET_POINTS_BALANCE_TOOL]

# 供 agent.py 的 _call_item_tool 判定是否转发到本模块
MERCHANT_TOOL_NAMES = frozenset({GET_MERCHANT_LIST, GET_MERCHANT_PRODUCTS, GET_POINTS_BALANCE})


def _dump(payload) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _error(message: str) -> str:
    return _dump({"error": message})


def _merchant_list(args: dict) -> str:
    category = args.get("category")
    category = category.strip() if isinstance(category, str) else None
    with connection() as conn:
        with conn.cursor() as cursor:
            shops = merchant_service.list_approved_shops(cursor, category=category)
    if not shops:
        # 有分类时给出更具体的提示，避免模型误答「平台没有商家」
        if category:
            return _dump({"merchants": [], "message": f"没有找到类型为「{category}」的商家"})
        return _dump({"merchants": [], "message": "暂无已上线的社区商家"})
    return _dump({"merchants": shops, "total": len(shops)})


def _merchant_products(args: dict) -> str:
    raw_id = args.get("merchant_id")
    try:
        merchant_id = int(raw_id)
    except (TypeError, ValueError):
        return _error("merchant_id 必须是整数，请先用 get_merchant_list 查询商家 ID")
    keyword = args.get("keyword")
    keyword = keyword.strip() if isinstance(keyword, str) else ""

    with connection() as conn:
        with conn.cursor() as cursor:
            result = merchant_service.list_shop_products_by_id(
                cursor, merchant_id=merchant_id, keyword=keyword
            )
    if not result:
        return _error("商家不存在或暂未开放")
    return _dump(result)


def _points_balance(viewer_user_id: int | None) -> str:
    if not viewer_user_id:
        return _error("用户未登录，无法查询积分")
    with connection() as conn:
        with conn.cursor() as cursor:
            snapshot = points_service.get_points_snapshot(cursor, viewer_user_id)
    if not snapshot:
        return _error("用户不存在")
    return _dump(snapshot)


def call_merchant_tool(name: str, args: dict | None = None, viewer_user_id: int | None = None) -> str:
    """执行商家/积分工具，返回 JSON 字符串供回填给 LLM。

    Args:
        name: 工具名（三个常量之一）
        args: LLM 给出的参数 dict（可为 None）
        viewer_user_id: **当前提问用户**，由服务端注入（绝不来自 LLM）

    任何异常都被吞掉并转成 `{"error": ...}`，保证对话不中断。
    """
    args = args if isinstance(args, dict) else {}
    # 只记 debug：走 agent._call_item_tool 时它已统一打 INFO 级 [TOOL_CALL]，
    # 这里再打一遍会让日志出现两行重复，干扰「工具是否真被调用」的排查。
    logger.debug("[TOOL_CALL] %s(%s)", name, json.dumps(args, ensure_ascii=False))
    handlers = {
        GET_MERCHANT_LIST: lambda: _merchant_list(args),
        GET_MERCHANT_PRODUCTS: lambda: _merchant_products(args),
        GET_POINTS_BALANCE: lambda: _points_balance(viewer_user_id),
    }
    handler = handlers.get(name)
    if handler is None:
        return _error(f"未知工具 {name}")
    try:
        return handler()
    except Exception as exc:  # noqa: BLE001 — 工具失败不应中断对话
        logger.warning("商家工具 %s 执行失败：%s", name, exc)
        return _error("查询失败，请稍后重试")
