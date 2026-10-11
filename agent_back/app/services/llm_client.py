"""大模型统一调用封装（阿里云百炼 DashScope）。

约定：业务代码只允许调用本模块，不直接 import dashscope，也不直接请求大模型 HTTP 接口。
- 文本对话 / JSON 输出 / 多模态理解：openai 库（OpenAI 兼容接口）；
- 图像编辑 / 文生图 / 语音识别：DashScope 原生异步任务 REST（仅依赖 requests）。

所有失败统一抛出 RuntimeError（带可读原因），由上层捕获并转为结构化错误。
"""
import base64
import json
import time
from pathlib import Path
from typing import Any

import openai
import requests
from openai import OpenAI

from app.core.config import settings
from app.services import dashscope

# DashScope 原生 REST 基地址（异步任务类接口不在 OpenAI 兼容路径下）
NATIVE_BASE = "https://dashscope.aliyuncs.com/api/v1"
# 任务轮询间隔与超时（秒）
_POLL_INTERVAL = 2.0
_TASK_TIMEOUT = 120


def available() -> bool:
    """是否已配置大模型密钥（未配置时上层应降级处理）。"""
    return dashscope.has_key()


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.llm_api_key}", "Content-Type": "application/json"}


def _require_key() -> None:
    if not available():
        raise RuntimeError("大模型服务未配置密钥（LLM_API_KEY）")


def _chat_client() -> OpenAI:
    return OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_api_url)


def chat_text(messages: list[dict], model: str | None = None, timeout: int = 60) -> str:
    """非流式文本对话，返回完整回复文本。"""
    _require_key()
    try:
        completion = _chat_client().chat.completions.create(
            model=model or settings.llm_api_model, messages=messages, timeout=timeout
        )
    except openai.APIError as exc:
        raise RuntimeError(f"大模型请求失败：{exc}") from exc
    return (completion.choices[0].message.content or "").strip()


def chat_json(messages: list[dict], model: str | None = None, timeout: int = 60) -> Any:
    """非流式对话并解析 JSON 回答（委托给既有 dashscope 封装）。"""
    _require_key()
    try:
        return dashscope.chat_json(messages, model=model, timeout=timeout)
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"大模型未返回合法 JSON：{exc}") from exc
    except openai.APIError as exc:
        raise RuntimeError(f"大模型请求失败：{exc}") from exc


def understand_intent(text: str, prompt_template: str, **fmt) -> dict:
    """意图理解：按提示词模板要求模型输出 JSON 并解析。fmt 提供模板额外占位符（如 language）。"""
    messages = [
        {"role": "user", "content": prompt_template.format(text=text, **fmt)},
    ]
    result = chat_json(messages)
    if not isinstance(result, dict) or "intent" not in result:
        raise RuntimeError("意图理解结果缺少 intent 字段")
    return result


def translate_text(text: str, prompt: str) -> dict:
    """翻译：prompt 中已包含双语要求与专有名词保护，期望返回 {"translation":..., "confidence":...}。"""
    result = chat_json([{"role": "user", "content": prompt}])
    if not isinstance(result, dict) or "translation" not in result:
        raise RuntimeError("翻译结果缺少 translation 字段")
    confidence = result.get("confidence", 0.8)
    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence = 0.8
    return {"translation": str(result["translation"]), "confidence": confidence}


def describe_image(image_ref: str, prompt: str, timeout: int = 60) -> str:
    """多模态理解：image_ref 支持 http(s) URL 或本地文件路径（自动转 base64）。"""
    _require_key()
    if image_ref.startswith(("http://", "https://")):
        image_url = image_ref
    else:
        data = Path(image_ref).read_bytes()
        image_url = "data:image/jpeg;base64," + base64.b64encode(data).decode()
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_url}},
                {"type": "text", "text": prompt},
            ],
        }
    ]
    try:
        completion = _chat_client().chat.completions.create(
            model=settings.llm_vl_model, messages=messages, timeout=timeout
        )
    except openai.APIError as exc:
        raise RuntimeError(f"多模态理解失败：{exc}") from exc
    return (completion.choices[0].message.content or "").strip()


# ---------------------------------------------------------------------------
# DashScope 原生异步任务（图像编辑 / 文生图 / 语音识别）
# ---------------------------------------------------------------------------

def _submit_task(path: str, payload: dict) -> str:
    """提交异步任务，返回 task_id。"""
    _require_key()
    resp = requests.post(
        f"{NATIVE_BASE}{path}",
        headers={**_headers(), "X-DashScope-Async": "enable"},
        json=payload,
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"任务提交失败 HTTP {resp.status_code}: {resp.text[:300]}")
    task_id = resp.json().get("output", {}).get("task_id")
    if not task_id:
        raise RuntimeError(f"任务提交响应缺少 task_id：{resp.text[:200]}")
    return task_id


def _wait_task(task_id: str, timeout: int = _TASK_TIMEOUT) -> dict:
    """轮询任务直至完成，返回 output 对象。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = requests.get(f"{NATIVE_BASE}/tasks/{task_id}", headers=_headers(), timeout=15)
        if resp.status_code >= 400:
            raise RuntimeError(f"任务查询失败 HTTP {resp.status_code}: {resp.text[:300]}")
        output = resp.json().get("output", {})
        status = output.get("task_status")
        if status == "SUCCEEDED":
            return output
        if status in ("FAILED", "CANCELED"):
            raise RuntimeError(f"任务执行失败：{json.dumps(output, ensure_ascii=False)[:300]}")
        time.sleep(_POLL_INTERVAL)
    raise RuntimeError("任务执行超时")


def _extract_result_url(output: dict) -> str:
    """从任务输出中提取结果文件 URL（兼容 results 列表与 result_url 两种结构）。"""
    results = output.get("results")
    if isinstance(results, list) and results and results[0].get("url"):
        return results[0]["url"]
    if output.get("result_url"):
        return output["result_url"]
    raise RuntimeError("任务输出中未找到结果 URL")


def image_edit(image_url: str, prompt: str) -> str:
    """图像编辑（wanx2.1-imageedit 外推/局部编辑），image_url 需公网可达，返回结果图 URL。"""
    payload = {
        "model": settings.llm_image_edit_model,
        "input": {"function": "description_edit", "prompt": prompt, "base_image_url": image_url},
        "parameters": {"n": 1},
    }
    output = _wait_task(_submit_task("/services/aigc/image2image/image-synthesis", payload))
    return _extract_result_url(output)


def text_to_image(prompt: str, size: str = "1024*1024") -> str:
    """文生图（wanx2.1-t2i-turbo），返回结果图 URL。"""
    payload = {
        "model": settings.llm_image_gen_model,
        "input": {"prompt": prompt},
        "parameters": {"size": size, "n": 1},
    }
    output = _wait_task(_submit_task("/services/aigc/text2image/image-synthesis", payload))
    return _extract_result_url(output)


def transcribe_audio(file_url: str) -> str:
    """语音识别（paraformer 文件转写），file_url 需公网可达，返回识别文本。"""
    payload = {
        "model": settings.llm_asr_model,
        "input": {"file_urls": [file_url]},
    }
    output = _wait_task(_submit_task("/services/audio/asr/transcription", payload))
    results = output.get("results")
    if not isinstance(results, list) or not results:
        raise RuntimeError("语音识别任务输出缺少 results")
    transcription_url = results[0].get("transcription_url")
    if not transcription_url:
        raise RuntimeError("语音识别任务输出缺少 transcription_url")
    # 转写结果为一份 JSON 文件，需二次下载解析
    resp = requests.get(transcription_url, timeout=15)
    if resp.status_code >= 400:
        raise RuntimeError(f"转写结果下载失败 HTTP {resp.status_code}")
    data = resp.json()
    sentences = data.get("transcripts", [{}])[0].get("sentences", [])
    text = "".join(s.get("text", "") for s in sentences).strip()
    if not text:
        raise RuntimeError("语音识别结果为空")
    return text


def download_file(url: str, dest: Path) -> int:
    """下载结果文件到本地，返回字节数。"""
    resp = requests.get(url, timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(f"结果文件下载失败 HTTP {resp.status_code}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return len(resp.content)
