"""智能体助手：配置 DASHSCOPE_API_KEY 后走真实大模型，否则降级本地演示。"""
import json
import logging
import time
from collections.abc import Iterator

from app.agents.prompts.assistant_prompts import (
    MERCHANT_KEYWORDS,
    MERCHANT_TOOL_DIRECTIVE,
    PLATFORM_OVERVIEW,
    SCOPE_NOTICE,
    build_points_rules_block,
)
from app.agents.tools.merchant_tools import MERCHANT_TOOLS, MERCHANT_TOOL_NAMES, call_merchant_tool
from app.core.config import settings
from app.db.pool import connection
from app.services import dashscope
from app.services import item_query_service
from app.services import mcp_client
from app.services import points_service

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    f"你是「社区旧物互换平台」的智能助手「{settings.agent_name}」。"
    "定位是社区百事通式工具型助手：专业、简洁、可信，不卖萌、不使用'哦~''呀~''呢~'等语气词，"
    "不输出'尽管问我''随时找我'等营销式结尾，直接给结果不绕弯子。"
    "请用简洁的中文回答用户问题，回答控制在 300 字以内。"
    "\n\n输出约束："
    "1. 你的回答必须基于工具返回的真实数据。工具返回什么，你就说什么；工具返回空，就如实告知用户'没有找到'，不要编造数据。"
    "2. 不要主动推荐用户去做别的操作（如'打开平台首页'、'上传闲置物品'、'确认交换完成'、'获得积分奖励'），除非用户明确询问这些。"
    "3. 当用户询问'附近有没有某物'、'有没有人换某物'、'想换某物'时，必须先调用 search_items 或 find_nearby_items 工具查询，拿到结果后再回答，不要在没调用工具的情况下编造回答，也不要说'我无法查看附近物品'。"
    "4. 工具调用失败时，如实说'查询失败，请稍后重试'，不要假装成功或给预设建议。"
    "5. 无关问题礼貌地引导回平台话题。"
    "\n\n禁止输出以下模板话术（会让用户觉得你在敷衍）："
    "- '建议您打开平台首页...' / '可以上传自己的闲置物品...' / '交换成功后记得在平台确认完成...' / '可以获得积分奖励哦~'"
)

# 英文模式追加的语言指令（用户要求：目标语言为 English 时全程英文，禁止中文）
EN_LANGUAGE_DIRECTIVE = (
    "\n\n请务必使用 English 回复用户。目标语言是 English，请全程使用英文回答，禁止出现中文。"
)


def _read_effective_rules() -> dict:
    """读取 sys_config 里的**实时**积分规则；任何失败都回落代码默认值，不阻断对话。

    提示词里出现的分值必须与平台实际规则一致，否则 AI 会与管理端配置矛盾，
    因此不写死数值，改为每次请求读一次（3 个键，1 个小 SELECT）。
    """
    try:
        with connection() as conn:
            with conn.cursor() as cursor:
                return points_service.get_effective_rules(cursor)
    except Exception as exc:  # noqa: BLE001 — 配置读取失败不应让对话失败
        logger.warning("读取积分规则失败，提示词回落代码默认值：%s", exc)
        return {
            "points_publish": points_service.DEFAULT_POINTS_PUBLISH,
            "points_exchange": points_service.DEFAULT_POINTS_EXCHANGE,
            "carbon_per_exchange": points_service.DEFAULT_CARBON_PER_EXCHANGE,
        }


def _base_system_prompt(is_en: bool) -> str:
    """拼装基础系统提示词：角色语气（原文未改） + 平台知识 + 实时积分规则 + 范围协调句。

    平台知识必须对**所有**分支生效。本次修复的根因之一是：
    「用旧书换商家服务怎么兑换」不含任何物品查询关键词，会落到「普通对话」分支，
    而该分支的 system prompt 恰好只有输出约束、零平台功能描述，
    模型唯一能给出的回答就是「我这边没有相关数据」——不是拒答，是提示词真空。

    顺序说明：EN_LANGUAGE_DIRECTIVE 放最后，确保「必须用英文回答」压过
    中文的平台知识片段（该指令仅在 lang='en' 时非空）。
    """
    return (
        SYSTEM_PROMPT
        + PLATFORM_OVERVIEW
        + build_points_rules_block(_read_effective_rules())
        + SCOPE_NOTICE
        + (EN_LANGUAGE_DIRECTIVE if is_en else "")
    )

# 英文演示回复（LLM 不可用时的降级文案）
EN_MOCK_REPLY = (
    f"Hi, I'm {settings.agent_name}, the assistant of the community swap platform. "
    "Demo mode: DASHSCOPE_API_KEY is not configured, so I can't query real item data yet. "
    "Please set the API key in .env and try again."
)

CATEGORIES = ["数码电子", "家居家电", "图书文具", "服饰鞋包", "母婴用品", "运动户外", "美妆个护", "其他闲置"]

# ========== 图表生成工具（MCP 服务） ==========
# 当用户请求「分析数据并画图」时，Agent 通过 OpenAI function-calling 决策，
# 再调用 MCP 图表服务生成图表 URL，最终以 markdown 图片形式返回前端。

_CHART_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "generate_chart",
        "description": (
            "根据提供的数据生成图表，返回图片 URL。当用户请求分析交易/物品/积分等数据并绘图、"
            "画饼图、柱状图、折线图时调用此工具。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "chart_type": {
                    "type": "string",
                    "enum": ["pie", "bar", "line"],
                    "description": "图表类型：pie=饼图, bar=柱状图, line=折线图",
                },
                "data": {
                    "type": "string",
                    "description": (
                        "图表数据 JSON 字符串：饼图传 {\"类目1\": 数值1, ...}；"
                        "柱状图/折线图传 {\"labels\": [\"a\", \"b\"], \"values\": [1, 2]}"
                    ),
                },
                "title": {
                    "type": "string",
                    "description": "图表标题（可选）",
                },
            },
            "required": ["chart_type", "data"],
        },
    },
}

_CHART_DIRECTIVE = (
    "\n\n当用户要求绘制图表（如饼图/柱状图/折线图）或分析数据并作图时，"
    "请调用 generate_chart 工具：先在 data 字段中序列化合适的 JSON 数据，"
    "再在 chart_type 中选 pie/bar/line；普通问答无需调用工具。"
)

# ========== 高德地图工具（MCP 服务，streamable_http） ==========
# 当用户询问附近物品、距离、路线、天气、地址等地理相关问题时，Agent 通过
# OpenAI function-calling 决策调用高德 MCP 工具，把结果回填给 LLM 生成自然语言回复。

_AMAP_DIRECTIVE = (
    "\n\n当用户询问附近物品、距离、路线、天气、地址、定位等地理相关问题时，"
    "你可以调用高德地图工具来获取准确信息。调用前先确认用户的位置"
    "（从用户档案读取 latitude/longitude），如果用户档案没有位置信息，"
    "先询问用户当前位置（城市名或具体地址均可）。普通问答无需调用工具。"
)

# 触发地图工具的关键词（任一命中即尝试 amap 工具调用）
_AMAP_KEYWORDS = (
    "附近", "周边", "距离", "多远", "路线", "怎么走", "怎么去", "导航",
    "天气", "地址", "定位", "地图", "经纬度", "附近物品", "附近的人",
    "驾车", "步行", "公交", "骑行", "规划路线", "geocode", "regeocode", "amap",
)


def _is_amap_request(question: str) -> bool:
    q = question.lower()
    return any(k in q for k in _AMAP_KEYWORDS)


def _mcp_to_openai_tool(tool: dict) -> dict:
    """把 MCP 工具 schema 转成 OpenAI function-calling tool schema。"""
    schema = tool.get("inputSchema") or {"type": "object", "properties": {}}
    return {
        "type": "function",
        "function": {
            "name": tool.get("name", ""),
            "description": tool.get("description", "") or tool.get("name", ""),
            "parameters": schema,
        },
    }


def _stream_amap_response(question: str, is_en: bool) -> Iterator[str]:
    """高德 MCP 两轮调用：LLM 决策 → 调 MCP → 结果回填 → 流式生成自然语言回复。

    MCP 连接失败（无工具）抛异常由上层降级到普通流式对话；
    MCP 调用阶段失败则 yield 友好提示后 return，不中断对话。
    """
    amap_tools = mcp_client.list_amap_tools()
    if not amap_tools:
        raise RuntimeError("高德 MCP 工具不可用")

    openai_tools = [_mcp_to_openai_tool(t) for t in amap_tools]
    messages: list[dict] = [
        {"role": "system", "content": _base_system_prompt(is_en) + _AMAP_DIRECTIVE},
        {"role": "user", "content": question},
    ]

    # 第一轮：LLM 决策是否调工具
    message = dashscope.chat_with_tools(messages, openai_tools)

    # 未触发工具：走普通文本返回（按字符流式产出）
    if not getattr(message, "tool_calls", None):
        content = (message.content or "").strip()
        if not content:
            raise RuntimeError("LLM 未返回内容")
        for ch in content:
            yield ch
            time.sleep(0.01)
        return

    intro = "正在查询地图信息…\n\n"
    for ch in intro:
        yield ch
        time.sleep(0.02)

    # 把 assistant 的 tool_call 消息追加到历史，便于第二轮 LLM 上下文
    messages.append(message)

    # 执行 LLM 决策的所有 tool_calls（amap 可能并行调多个工具）
    for tool_call in message.tool_calls:
        tool_name = tool_call.function.name
        try:
            args = json.loads(tool_call.function.arguments or "{}")
        except Exception:  # noqa: BLE001
            args = {}
        try:
            logger.info("[TOOL_CALL] %s(%s)", tool_name, json.dumps(args, ensure_ascii=False))
            result = mcp_client.call_amap_tool(tool_name, args)
        except Exception as exc:  # noqa: BLE001
            # MCP 调用失败（含超时）：友好提示后结束，不抛异常
            logger.warning("高德 MCP 调用 %s 失败：%s", tool_name, exc)
            yield "地图服务暂时不可用，请稍后重试"
            return
        # 把工具结果以 tool 角色回填，供第二轮 LLM 组织回复
        if isinstance(result, str):
            result_text = result
        else:
            result_text = json.dumps(result, ensure_ascii=False)
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": result_text,
        })

    # 第二轮：基于工具结果流式生成自然语言回复
    try:
        for token in dashscope.chat_stream(messages):
            yield token
    except Exception:  # noqa: BLE001
        yield "\n\n（回复生成中断，请重试）"

# 触发图表工具的关键词（任一命中即尝试 MCP 工具调用）
_CHART_KEYWORDS = (
    "图表", "饼图", "柱状图", "折线图", "条形图", "散点图", "数据可视化",
    "画图", "绘图", "画出", "生成图", "分析数据", "数据并画", "统计图",
    "chart", "pie", "bar", "line chart", "graph",
)


def _is_chart_request(question: str) -> bool:
    q = question.lower()
    return any(k in q for k in _CHART_KEYWORDS)


# ========== 平台物品查询工具（内部数据库，最高优先级） ==========
# 当用户询问「附近有没有某物」「想换某物」时，必须调用 search_items /
# find_nearby_items 查询平台物品数据库，不得用纯文本敷衍用户。

_ITEM_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_items",
        "description": (
            "在平台物品数据库中按关键词和分类搜索可交换的闲置物品。"
            "当用户询问'有没有某物'、'想换某物'、'找某物'、'有人出让某物'时调用，"
            "返回真实物品列表（含 item_id、title、category、condition_level、distance_km）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "搜索关键词，匹配物品标题或描述，如'数学教材'、'微波炉'、'自行车'",
                },
                "category": {
                    "type": "string",
                    "description": (
                        "物品分类名（可选）：数码电子/家居家电/图书文具/服饰鞋包/"
                        "母婴用品/运动户外/美妆个护/其他闲置"
                    ),
                },
            },
            "required": ["keyword"],
        },
    },
}

_ITEM_NEARBY_TOOL = {
    "type": "function",
    "function": {
        "name": "find_nearby_items",
        "description": (
            "查询指定坐标 radius_km 半径内的可交换物品，按距离升序排序。"
            "当用户询问'附近有什么物品'且上下文提供了用户位置（纬度/经度）时调用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "latitude": {"type": "number", "description": "用户纬度（从用户上下文读取）"},
                "longitude": {"type": "number", "description": "用户经度（从用户上下文读取）"},
                "radius_km": {"type": "number", "description": "搜索半径（公里），默认 5"},
                "keyword": {"type": "string", "description": "进一步过滤的关键词（可选）"},
            },
            "required": ["latitude", "longitude"],
        },
    },
}

_ITEM_QUERY_DIRECTIVE = (
    "\n\n当用户询问'附近有没有某物'、'有没有人换某物'、'我想换某物'、"
    "'想找某物'、'我在某地附近有什么'等意图时，必须调用 search_items 或 find_nearby_items "
    "工具去数据库查询，不要把问题推回给用户、不要说'我无法查看附近物品'。"
    "\n串联调用规则：若用户提到地名（如'吕梁'、'北京海淀'）但未直接给经纬度，"
    "且用户档案无位置，先调用 maps_geo 把地名转成经纬度，再用该坐标调 find_nearby_items；"
    "若用户上下文已含位置且用户问'附近'，直接调 find_nearby_items。"
    "\n若用户位置缺失且未提到地名，先用 search_items 按关键词查询，并提示用户去个人中心设置位置。"
    "查询结果为空时如实告知用户，并建议用户发布自己的需求让别人联系。"
    "回复时只基于工具返回的真实数据，不要编造物品名、价格或距离。"
)

# 触发物品查询的关键词（任一命中即尝试内部工具调用）；优先级高于 amap/chart
_ITEM_QUERY_KEYWORDS = (
    "想换", "想找", "求换", "求购", "有没有", "有吗", "哪里有", "有人有",
    "有人换", "谁能换", "换一本", "换个", "换点", "找一本", "找个", "找点", "找找", "寻找",
    "附近有", "附近有没有", "附近能", "附近谁", "闲置", "二手",
)
# 商家 / 积分关键词（智能体知识修复新增，见 assistant_prompts.MERCHANT_KEYWORDS）
# 与物品关键词**合并在同一分支**，而不是新开一个商家分支：
# 该分支的工具集同时包含物品工具与商家工具，由 LLM 依据工具描述自选，
# 从根上避免「新开分支要决定插在物品分支前还是后」的两难
# （『附近有没有打印店』含物品关键词、『兑换一本教材』含商家关键词，两个方向都会抢单）。
# 即便判断偏差，也不会答错——最多多调一次工具。
_ITEM_QUERY_KEYWORDS = _ITEM_QUERY_KEYWORDS + MERCHANT_KEYWORDS


def _is_item_query_request(question: str) -> bool:
    q = question.lower()
    return any(k in q for k in _ITEM_QUERY_KEYWORDS)


def _build_user_context_block(user_id: int | None) -> str:
    """从 user_id 查用户位置，生成注入 system prompt 的上下文片段。"""
    if not user_id:
        return "\n\n当前用户位置：未知（未登录或未携带 user_id）。若用户问附近物品，先询问其所在城市或地址。"
    profile = item_query_service.get_user_profile(user_id)
    lat = profile.get("latitude")
    lng = profile.get("longitude")
    community = profile.get("community")
    nickname = profile.get("nickname") or ""
    if lat is not None and lng is not None:
        loc = f"纬度 {lat}，经度 {lng}"
        if community:
            loc += f"，小区 {community}"
        return f"\n\n当前用户信息：昵称 {nickname}，位置 {loc}。调用 find_nearby_items 时直接使用该坐标。"
    return (
        f"\n\n当前用户信息：昵称 {nickname}，位置未设置（用户尚未在个人中心填写位置）。"
        "若用户询问附近物品，先提示其去个人中心设置位置，或询问当前城市/地址后再调 search_items。"
    )


def _call_item_tool(name: str, args: dict, viewer_user_id: int | None = None) -> str:
    """执行物品/地理/商家工具，返回 JSON 字符串结果供 LLM 回填。

    分发内部物品查询（search_items/find_nearby_items）、amap 地理编码（maps_geo）
    与商家/积分查询（get_merchant_list / get_merchant_products / get_points_balance），
    让 LLM 能在同一次 function-calling 内串联：maps_geo(地名)→find_nearby_items(坐标)。

    viewer_user_id 为当前提问用户，用于附近查询的隐私过滤
    （自己的物品不受自身 location_public 影响），以及 get_points_balance
    ——查积分永远查当前提问用户，绝不让 LLM 自己传 user_id。
    """
    logger.info("[TOOL_CALL] %s(%s)", name, json.dumps(args, ensure_ascii=False))
    if name == "search_items":
        result = item_query_service.search_items(
            keyword=str(args.get("keyword") or ""),
            category=args.get("category"),
        )
        return json.dumps(result, ensure_ascii=False)
    if name == "find_nearby_items":
        result = item_query_service.find_nearby_items(
            latitude=args.get("latitude"),
            longitude=args.get("longitude"),
            radius_km=args.get("radius_km") or 5.0,
            keyword=str(args.get("keyword") or ""),
            viewer_user_id=viewer_user_id,
        )
        return json.dumps(result, ensure_ascii=False)
    if name == "maps_geo":
        # 地理编码走高德 MCP（streamable_http），把地名转成经纬度
        if not mcp_client.is_amap_configured():
            return json.dumps({"error": "地图服务未配置"}, ensure_ascii=False)
        try:
            result = mcp_client.call_amap_tool("maps_geo", args)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[TOOL_FAIL] maps_geo: %s", exc)
            return json.dumps({"error": "地理编码失败", "detail": str(exc)}, ensure_ascii=False)
        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
    if name in MERCHANT_TOOL_NAMES:
        # 商家/积分工具自己吞异常并返回 {"error": ...}，此处无需再兜
        return call_merchant_tool(name, args, viewer_user_id=viewer_user_id)
    return json.dumps({"error": f"未知工具 {name}"}, ensure_ascii=False)


def _stream_item_query_response(question: str, is_en: bool, user_id: int | None) -> Iterator[str]:
    """平台数据查询两轮调用：LLM 决策 → 调内部工具 → 结果回填 → 流式生成自然语言回复。

    工具集 = 物品查询 + 高德地理编码 + 商家/积分查询。
    商家工具并入本分支（而非新开分支）的理由见 _ITEM_QUERY_KEYWORDS 的注释。

    LLM 未触发工具时走普通文本；工具调用失败（异常）由上层降级。
    """
    # 内部物品工具 + 商家/积分工具 + 高德地理编码（让 LLM 能串联 maps_geo(地名)→find_nearby_items(坐标)）
    tools = [_ITEM_SEARCH_TOOL, _ITEM_NEARBY_TOOL, *MERCHANT_TOOLS]
    if mcp_client.is_amap_configured():
        for t in mcp_client.list_amap_tools():
            if t.get("name") == "maps_geo":
                tools.append(_mcp_to_openai_tool(t))
                break
    messages: list[dict] = [
        {"role": "system", "content": _base_system_prompt(is_en) + _ITEM_QUERY_DIRECTIVE + MERCHANT_TOOL_DIRECTIVE + _build_user_context_block(user_id)},
        {"role": "user", "content": question},
    ]

    # 第一轮：LLM 决策是否调工具
    message = dashscope.chat_with_tools(messages, tools)

    if not getattr(message, "tool_calls", None):
        content = (message.content or "").strip()
        if not content:
            raise RuntimeError("LLM 未返回内容")
        for ch in content:
            yield ch
            time.sleep(0.01)
        return

    intro = "正在为你查询平台数据…\n\n"
    for ch in intro:
        yield ch
        time.sleep(0.02)

    messages.append(message)
    for tool_call in message.tool_calls:
        tool_name = tool_call.function.name
        try:
            args = json.loads(tool_call.function.arguments or "{}")
        except Exception:  # noqa: BLE001
            args = {}
        try:
            result_text = _call_item_tool(tool_name, args, viewer_user_id=user_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("物品查询工具 %s 失败：%s", tool_name, exc)
            result_text = json.dumps({"error": "查询失败", "detail": str(exc)}, ensure_ascii=False)
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": result_text,
        })

    # 第二轮：基于工具结果流式生成自然语言回复
    reply_buf: list[str] = []
    try:
        for token in dashscope.chat_stream(messages):
            reply_buf.append(token)
            yield token
    except Exception:  # noqa: BLE001
        yield "\n\n（回复生成中断，请重试）"
    if reply_buf:
        logger.info("[LLM_REPLY] %s", "".join(reply_buf)[:100])


def _stream_chart_response(question: str, is_en: bool) -> Iterator[str]:
    """非流式决策 + MCP 工具调用 + markdown 图片返回；失败抛异常由上层降级。"""
    messages = [
        {"role": "system", "content": _base_system_prompt(is_en) + _CHART_DIRECTIVE},
        {"role": "user", "content": question},
    ]
    message = dashscope.chat_with_tools(messages, [_CHART_TOOL_DEFINITION])

    # 未触发工具调用：走普通文本返回（按字符流式产出，保持前端打字机效果）
    if not getattr(message, "tool_calls", None):
        content = (message.content or "").strip()
        if not content:
            raise RuntimeError("LLM 未返回内容")
        for ch in content:
            yield ch
            time.sleep(0.01)
        return

    tool_call = message.tool_calls[0]
    args = json.loads(tool_call.function.arguments or "{}")
    chart_type = str(args.get("chart_type") or "bar").lower()
    if chart_type not in ("pie", "bar", "line"):
        chart_type = "bar"
    data = args.get("data") or args.get("values") or ""
    title = str(args.get("title") or "图表")

    intro = "正在为你生成图表…\n\n"
    for ch in intro:
        yield ch
        time.sleep(0.02)

    url = mcp_client.call_chart_tool(chart_type, data, title)
    yield f"![{title}]({url})"


def mock_reply(question: str) -> str:
    """无 API Key 时的本地演示回复：明确告知演示模式，不输出预设指导话术。"""
    return (
        f"我是{settings.agent_name}，当前为演示模式（后端未配置 DASHSCOPE_API_KEY），"
        "暂时无法查询真实物品数据。请在 .env 配置 API Key 后再试。"
    )


def stream_tokens(question: str, lang: str = "zh", user_id: int | None = None) -> Iterator[str]:
    """流式产出回答；LLM 未配置或首包前失败时回退演示回复。lang 支持 'zh'/'en'。

    优先级：平台数据查询（物品 + 商家/积分，走内部数据库）> 高德地图 MCP > 图表 MCP > 普通流式对话。
    各分支失败时自动降级到普通流式对话，保证对话不中断。
    user_id 用于从用户档案读取位置注入 system prompt（附近物品查询依赖），
    以及 get_points_balance 工具（积分只查当前提问用户）。
    """
    is_en = lang == "en"
    if dashscope.has_key():
        # 物品查询意图（最高优先级）→ 调内部 search_items / find_nearby_items
        if _is_item_query_request(question):
            try:
                emitted_item = False
                for token in _stream_item_query_response(question, is_en, user_id):
                    emitted_item = True
                    yield token
                return
            except Exception:
                if emitted_item:
                    yield "\n\n（查询中断，请重试）"
                    return
                # 失败降级到普通流式对话
        # 地图意图 + 高德 MCP 已配置 → 尝试 amap 工具调用路径
        if mcp_client.is_amap_configured() and _is_amap_request(question):
            try:
                emitted_amap = False
                for token in _stream_amap_response(question, is_en):
                    emitted_amap = True
                    yield token
                return
            except Exception:
                if emitted_amap:
                    yield "\n\n（地图服务中断，请重试）"
                    return
                # 失败降级到普通流式对话
        # 图表意图 + 图表 MCP 已配置 → 尝试图表工具调用路径
        if mcp_client.is_configured() and _is_chart_request(question):
            try:
                emitted_chart = False
                for token in _stream_chart_response(question, is_en):
                    emitted_chart = True
                    yield token
                return
            except Exception:
                if emitted_chart:
                    yield "\n\n（图表生成中断，请重试）"
                    return
                # 失败降级到普通流式对话
        emitted = False
        try:
            messages = [
                {"role": "system", "content": _base_system_prompt(is_en)},
                {"role": "user", "content": question},
            ]
            for token in dashscope.chat_stream(messages):
                emitted = True
                yield token
            return
        except Exception:
            if emitted:
                yield "\n\n（回答生成中断，请重试）" if not is_en else "\n\n(Answer interrupted, please retry.)"
                return
    text = EN_MOCK_REPLY if is_en else mock_reply(question)
    for ch in text:
        yield ch
        time.sleep(0.02)


def _valid_recognition(data: dict) -> dict | None:
    name = str(data.get("name") or "").strip()
    if not name:
        return None
    category = str(data.get("category") or "").strip()
    if category not in CATEGORIES:
        category = "其他闲置"
    try:
        condition = int(data.get("condition_level") or 3)
    except (TypeError, ValueError):
        condition = 3
    condition = max(1, min(5, condition))
    tags = data.get("tags") if isinstance(data.get("tags"), list) else []
    return {
        "name": name[:64],
        "category": category,
        "condition_level": condition,
        "description": str(data.get("description") or "").strip()[:200],
        "tags": [str(t)[:16] for t in tags][:6],
    }


def mock_recognition() -> dict:
    return {
        "name": "演示识别结果",
        "category": "其他闲置",
        "condition_level": 4,
        "description": "当前为演示模式：在 .env 配置 LLM_VL_MODEL 多模态模型后即可真实识别图片中的物品。",
        "tags": ["演示", "旧物", "环保"],
    }
