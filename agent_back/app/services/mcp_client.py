"""MCP（Model Context Protocol）客户端：连接两类 MCP 服务。

- mcp-server-chart：SSE 传输，生成图表 URL
- amap-maps（高德地图）：streamable_http 传输，提供周边搜索/距离/路径/天气/地理编码等工具

约束：调用方位于 FastAPI 既有事件循环内的同步上下文，因此所有异步操作
必须在独立线程 + 独立事件循环中执行，避免 asyncio.run() 与主循环冲突。
连接失败时统一返回空工具列表 + 记录日志，不抛异常，保证 Agent 主流程不中断。
"""
import asyncio
import logging
import threading
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client

from app.core.config import settings

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    """是否配置了 MCP 图表服务的 SSE URL。"""
    return bool(settings.mcp_chart_sse_url.strip())


def is_amap_configured() -> bool:
    """是否配置了高德地图 MCP 的 streamable_http URL。"""
    return bool(settings.mcp_amap_url.strip())


def _run_async(coro):
    """在独立线程中运行协程，避免与 FastAPI 运行中的事件循环冲突。"""
    box: dict[str, Any] = {}

    def _worker() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            box["value"] = loop.run_until_complete(coro)
        except BaseException as exc:  # noqa: BLE001
            box["error"] = exc
        finally:
            try:
                loop.close()
            except Exception:  # noqa: BLE001
                pass

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join()
    if "error" in box:
        raise box["error"]
    return box.get("value")


async def _list_tools_async(url: str) -> list[dict]:
    """连接 MCP SSE 服务并返回工具清单。"""
    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return [
                {
                    "name": tool.name,
                    "description": getattr(tool, "description", "") or "",
                    "inputSchema": getattr(tool, "inputSchema", {}) or {},
                }
                for tool in result.tools
            ]


async def _call_tool_async(url: str, name: str, arguments: dict) -> Any:
    """调用 MCP 工具并返回结果内容。"""
    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
            # result.content 是 list[TextContent | ImageContent | ...]
            texts: list[str] = []
            for item in result.content or []:
                text = getattr(item, "text", None)
                if text:
                    texts.append(text)
            if not texts:
                return None
            joined = "\n".join(texts)
            # 尝试解析 JSON（部分 MCP 工具返回结构化结果）
            try:
                import json
                return json.loads(joined)
            except Exception:  # noqa: BLE001
                return joined


def list_tools() -> list[dict]:
    """同步获取 MCP 服务的工具清单；未配置或失败时返回空列表。"""
    if not is_configured():
        return []
    try:
        return _run_async(_list_tools_async(settings.mcp_chart_sse_url))
    except Exception as exc:  # noqa: BLE001
        logger.warning("MCP list_tools 失败：%s", exc)
        return []


def call_tool(name: str, arguments: dict) -> Any:
    """同步调用 MCP 工具；未配置或失败时抛出异常。"""
    if not is_configured():
        raise RuntimeError("未配置 MCP_CHART_SSE_URL")
    return _run_async(_call_tool_async(settings.mcp_chart_sse_url, name, arguments))


def call_chart_tool(chart_type: str, data: Any, title: str = "") -> str:
    """高层封装：调用图表生成工具，返回图表 URL 或文本结果。

    自动发现工具名（包含 chart/pie/bar/line/plot 关键字的第一个），
    依次尝试常见参数名组合，命中后返回字符串形式的结果。
    """
    if not is_configured():
        raise RuntimeError("未配置 MCP_CHART_SSE_URL")

    tools = list_tools()
    if not tools:
        raise RuntimeError("MCP 服务未返回任何工具")

    # 候选工具名：优先精确匹配 chart_type，再按关键字降级
    keywords = [chart_type.lower(), "chart", "pie", "bar", "line", "plot"]
    target = None
    for kw in keywords:
        for t in tools:
            if kw and kw in t["name"].lower():
                target = t
                break
        if target:
            break
    if not target:
        # 没匹配上就用第一个工具
        target = tools[0]

    # 常见参数名组合，按 schema 字段名命中
    schema_props = (target.get("inputSchema") or {}).get("properties", {}) or {}
    arg_keys = set(schema_props.keys()) | {"type", "data", "title", "chart_type", "chartType", "values", "labels"}

    def _pick(primary: str, *alternatives: str) -> str | None:
        for k in (primary, *alternatives):
            if k in arg_keys:
                return k
        return None

    type_key = _pick("type", "chart_type", "chartType", "chart")
    data_key = _pick("data", "values", "dataset", "series")
    title_key = _pick("title", "name", "label")

    arguments: dict[str, Any] = {}
    if type_key:
        arguments[type_key] = chart_type
    if data_key:
        arguments[data_key] = data
    if title_key and title:
        arguments[title_key] = title
    # 兜底：若 schema 无可识别字段，直接按最常见命名传入
    if not arguments:
        arguments = {"type": chart_type, "data": data, "title": title}

    logger.info("MCP 调用工具 %s 参数 %s", target["name"], arguments)
    result = call_tool(target["name"], arguments)

    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        # 常见字段：url / image_url / chart_url / data.url
        for key in ("url", "image_url", "chart_url", "image", "output"):
            value = result.get(key)
            if isinstance(value, str) and value:
                return value
        # 嵌套 data.url
        nested = result.get("data")
        if isinstance(nested, dict):
            for key in ("url", "image_url", "chart_url"):
                value = nested.get(key)
                if isinstance(value, str) and value:
                    return value
        # 返回原始 JSON 字符串
        import json
        return json.dumps(result, ensure_ascii=False)
    return str(result)


# ========== 高德地图 MCP（streamable_http 传输） ==========

# 模块级工具缓存：避免每次请求都重连 MCP（24 小时有效期内的 URL 工具集稳定）
_amap_tools_cache: list[dict] | None = None


def _parse_tool_list(result: Any) -> list[dict]:
    """把 MCP list_tools 结果转成统一字典结构。"""
    return [
        {
            "name": tool.name,
            "description": getattr(tool, "description", "") or "",
            "inputSchema": getattr(tool, "inputSchema", {}) or {},
        }
        for tool in result.tools
    ]


def _extract_tool_text(result: Any) -> Any:
    """从 call_tool 结果中抽取文本，优先解析 JSON。"""
    texts: list[str] = []
    for item in result.content or []:
        text = getattr(item, "text", None)
        if text:
            texts.append(text)
    if not texts:
        return None
    joined = "\n".join(texts)
    try:
        import json
        return json.loads(joined)
    except Exception:  # noqa: BLE001
        return joined


async def _list_amap_tools_async(url: str, init_timeout: float = 15.0, list_timeout: float = 15.0) -> list[dict]:
    """连接高德 MCP（streamable_http）并返回工具清单。"""
    # streamable_http_client 返回 (read, write, ...) 元组，不同版本元素数不同，取前两项
    async with streamable_http_client(url) as ctx:
        read, write = ctx[0], ctx[1]
        async with ClientSession(read, write) as session:
            await asyncio.wait_for(session.initialize(), timeout=init_timeout)
            result = await asyncio.wait_for(session.list_tools(), timeout=list_timeout)
            return _parse_tool_list(result)


async def _call_amap_tool_async(
    url: str,
    name: str,
    arguments: dict,
    init_timeout: float = 15.0,
    call_timeout: float = 30.0,
) -> Any:
    """调用高德 MCP 工具并返回结果内容。"""
    async with streamable_http_client(url) as ctx:
        read, write = ctx[0], ctx[1]
        async with ClientSession(read, write) as session:
            await asyncio.wait_for(session.initialize(), timeout=init_timeout)
            result = await asyncio.wait_for(session.call_tool(name, arguments), timeout=call_timeout)
            return _extract_tool_text(result)


def list_amap_tools(use_cache: bool = True) -> list[dict]:
    """同步获取高德 MCP 工具清单；未配置或失败时返回空列表（不抛异常）。

    首次成功加载后缓存到模块级变量，后续请求直接命中缓存，避免重复建连。
    """
    global _amap_tools_cache
    if use_cache and _amap_tools_cache is not None:
        return _amap_tools_cache
    if not is_amap_configured():
        return []
    try:
        tools = _run_async(_list_amap_tools_async(settings.mcp_amap_url))
        _amap_tools_cache = tools
        logger.info("高德 MCP 工具加载成功：%s", [t["name"] for t in tools])
        return tools
    except Exception as exc:  # noqa: BLE001
        logger.warning("高德 MCP list_tools 失败：%s", exc)
        return []


def call_amap_tool(name: str, arguments: dict) -> Any:
    """同步调用高德 MCP 工具；未配置或调用失败时抛异常（由上层兜底）。"""
    if not is_amap_configured():
        raise RuntimeError("未配置 MCP_AMAP_URL")
    return _run_async(_call_amap_tool_async(settings.mcp_amap_url, name, arguments))


def clear_amap_cache() -> None:
    """清空 amap 工具缓存（MCP URL 更换或调试时使用）。"""
    global _amap_tools_cache
    _amap_tools_cache = None
