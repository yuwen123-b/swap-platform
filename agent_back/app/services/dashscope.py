"""阿里云百炼 DashScope（OpenAI 兼容接口）文本对话封装，统一使用 openai 库。"""
import json
from collections.abc import Iterator
from typing import Any

from openai import OpenAI

from app.core.config import settings


def has_key() -> bool:
    return bool(settings.dashscope_api_key.strip())


def _client() -> OpenAI:
    return OpenAI(api_key=settings.dashscope_api_key, base_url=settings.llm_api_url)


def chat_stream(messages: list[dict], model: str | None = None, timeout: int = 120) -> Iterator[str]:
    """流式对话：逐段 yield 增量文本；连接/HTTP 异常向上抛出。"""
    stream = _client().chat.completions.create(
        model=model or settings.llm_api_model,
        messages=messages,
        stream=True,
        timeout=timeout,
    )
    for chunk in stream:
        try:
            delta = chunk.choices[0].delta.content
        except (IndexError, AttributeError, TypeError):
            continue
        if delta:
            yield delta


def chat_json(messages: list[dict], model: str | None = None, timeout: int = 60) -> Any:
    """非流式调用并把回答解析为 JSON（自动截取首个 {...} 片段）。"""
    completion = _client().chat.completions.create(
        model=model or settings.llm_api_model,
        messages=messages,
        timeout=timeout,
    )
    content = (completion.choices[0].message.content or "").strip()
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"LLM 未返回 JSON：{content[:200]}")
    return json.loads(content[start:end + 1])


def chat_with_tools(
    messages: list[dict],
    tools: list[dict],
    model: str | None = None,
    tool_choice: str = "auto",
    timeout: int = 60,
) -> Any:
    """非流式函数调用：返回 ChatCompletionMessage（含 .content 与 .tool_calls）。

    tools 遵循 OpenAI function-calling schema；
    调用方需根据返回值是否含 tool_calls 决定继续解析或走文本分支。
    """
    completion = _client().chat.completions.create(
        model=model or settings.llm_api_model,
        messages=messages,
        tools=tools,
        tool_choice=tool_choice,
        timeout=timeout,
    )
    return completion.choices[0].message
