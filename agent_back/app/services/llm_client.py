"""大模型统一调用封装（阿里云百炼 DashScope）。

约定：业务代码只允许调用本模块，不直接 import dashscope，也不直接请求大模型 HTTP 接口。
- 文本对话 / JSON 输出 / 多模态理解：openai 库（OpenAI 兼容接口）；
- 图像编辑 / 文生图 / 语音识别：DashScope 原生异步任务 REST（仅依赖 requests）。

所有失败统一抛出 RuntimeError（带可读原因），由上层捕获并转为结构化错误。
"""
import base64
import json
import logging
import time
from pathlib import Path
from typing import Any

import openai
import requests
from openai import OpenAI

from app.core.config import settings
from app.services import dashscope

# 任务轮询间隔与超时（秒）
_POLL_INTERVAL = 2.0
_TASK_TIMEOUT = 120


def available() -> bool:
    """是否已配置大模型密钥（未配置时上层应降级处理）。"""
    return dashscope.has_key()


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.dashscope_api_key}", "Content-Type": "application/json"}


def _require_key() -> None:
    if not available():
        raise RuntimeError("大模型服务未配置密钥（DASHSCOPE_API_KEY）")


def _chat_client() -> OpenAI:
    return OpenAI(api_key=settings.dashscope_api_key, base_url=settings.llm_api_url)


def _modelscope_client() -> OpenAI:
    """魔搭社区 OpenAI 兼容客户端（ASR/TTS/图像编辑 共用）。"""
    return OpenAI(api_key=settings.modelscope_api_key, base_url=settings.modelscope_api_url)


def _has_modelscope() -> bool:
    return bool(settings.modelscope_api_key.strip())


def _require_modelscope_key() -> None:
    if not _has_modelscope():
        raise RuntimeError("魔搭服务未配置密钥（MODELSCOPE_API_KEY）")


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

def _submit_task(url: str, payload: dict) -> str:
    """提交异步任务到指定 URL，返回 task_id。"""
    _require_key()
    resp = requests.post(
        url,
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
        resp = requests.get(settings.task_api_url.format(task_id=task_id), headers=_headers(), timeout=15)
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


def image_edit(image_path: Path | None = None, image_url: str = "", prompt: str = "") -> bytes:
    """图像编辑（多视角外推/局部编辑），返回结果图二进制。

    供应商切换：
    - IMAGE_PROVIDER=modelscope（默认）：魔搭 Qwen-Image-Edit，OpenAI 兼容接口，传本地文件；
    - IMAGE_PROVIDER=dashscope：百炼 wanx2.1-imageedit，异步任务 REST，传公网 URL；
    - 魔搭失败时自动降级百炼（需配置 DASHSCOPE_API_KEY 和 PUBLIC_BASE_URL）。
    """
    # 优先魔搭
    if settings.image_provider == "modelscope" and _has_modelscope() and image_path:
        try:
            return _image_edit_modelscope(image_path, prompt)
        except RuntimeError as exc:
            import logging
            logging.getLogger(__name__).warning("魔搭图像编辑失败，降级百炼：%s", exc)
    # 降级百炼
    return _image_edit_dashscope(image_url, prompt)


def _image_edit_modelscope(image_path: Path, prompt: str) -> bytes:
    """魔搭图像编辑：OpenAI 兼容 images.edit 接口。"""
    _require_modelscope_key()
    try:
        with open(image_path, "rb") as f:
            resp = _modelscope_client().images.edit(
                model=settings.image_model,
                image=f,
                prompt=prompt,
            )
    except openai.APIError as exc:
        raise RuntimeError(f"魔搭图像编辑失败：{exc}") from exc
    if not resp.data:
        raise RuntimeError("魔搭图像编辑返回空结果")
    item = resp.data[0]
    # 优先 base64，其次下载 URL
    if getattr(item, "b64_json", None):
        return base64.b64decode(item.b64_json)
    url = getattr(item, "url", None)
    if not url:
        raise RuntimeError("魔搭图像编辑结果缺少 url 和 b64_json")
    r = requests.get(url, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"魔搭图像编辑结果下载失败 HTTP {r.status_code}")
    return r.content


def _image_edit_dashscope(image_url: str, prompt: str) -> bytes:
    """百炼图像编辑（异步任务 REST），image_url 需公网可达，返回结果图二进制。"""
    _require_key()
    if not image_url:
        raise RuntimeError("百炼图像编辑需要公网可达的图片 URL（PUBLIC_BASE_URL 未配置）")
    payload = {
        "model": settings.llm_image_edit_model,
        "input": {"function": "description_edit", "prompt": prompt, "base_image_url": image_url},
        "parameters": {"n": 1},
    }
    result_url = _extract_result_url(_wait_task(_submit_task(settings.image_edit_api_url, payload)))
    r = requests.get(result_url, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"百炼图像编辑结果下载失败 HTTP {r.status_code}")
    return r.content


def text_to_image(prompt: str, size: str = "1024*1024") -> str:
    """文生图（wanx2.1-t2i-turbo），返回结果图 URL。"""
    payload = {
        "model": settings.llm_image_gen_model,
        "input": {"prompt": prompt},
        "parameters": {"size": size, "n": 1},
    }
    output = _wait_task(_submit_task(settings.image_gen_api_url, payload))
    return _extract_result_url(output)


def synthesize_speech(text: str) -> bytes:
    """语音合成，返回音频二进制。

    供应商切换：
    - TTS_PROVIDER=modelscope（默认）：魔搭 CosyVoice2-0.5B，OpenAI 兼容 audio.speech 接口；
    - TTS_PROVIDER=dashscope：百炼 qwen3-tts-flash，同步 HTTP REST；
    - 魔搭失败时自动降级百炼。
    """
    if not (text or "").strip():
        raise RuntimeError("语音合成文本为空")
    # 优先魔搭
    if settings.tts_provider == "modelscope" and _has_modelscope():
        try:
            return _synthesize_modelscope(text)
        except RuntimeError as exc:
            import logging
            logging.getLogger(__name__).warning("魔搭语音合成失败，降级百炼：%s", exc)
    # 降级百炼
    return _synthesize_dashscope(text)


def _synthesize_modelscope(text: str) -> bytes:
    """魔搭语音合成：OpenAI 兼容 audio.speech 接口。"""
    _require_modelscope_key()
    try:
        resp = _modelscope_client().audio.speech.create(
            model=settings.tts_model,
            input=text,
            voice="default",
        )
    except openai.APIError as exc:
        raise RuntimeError(f"魔搭语音合成失败：{exc}") from exc
    if not resp.content:
        raise RuntimeError("魔搭语音合成返回空音频")
    return resp.content


def _synthesize_dashscope(text: str) -> bytes:
    """百炼语音合成（qwen3-tts-flash 同步 HTTP），返回音频二进制。"""
    _require_key()
    payload = {
        "model": settings.llm_tts_model,
        "input": {"text": text, "voice": settings.llm_tts_voice},
    }
    try:
        # 超时 12s：实测正常 1.1~1.6s；曾遇到一次 >60s 无响应，会把整轮助老交互卡死。
        # 失败前端会降级 Web Speech API 播报，所以宁可早放弃（12s 已是正常的 8 倍余量）。
        resp = requests.post(settings.tts_api_url,
                             headers=_headers(), json=payload, timeout=12)
    except requests.RequestException as exc:
        raise RuntimeError(f"语音合成请求失败：{exc}") from exc
    if resp.status_code >= 400:
        raise RuntimeError(f"语音合成失败 HTTP {resp.status_code}: {resp.text[:300]}")
    audio_url = (resp.json().get("output", {}).get("audio", {}) or {}).get("url")
    if not audio_url:
        raise RuntimeError(f"语音合成响应缺少音频 URL：{resp.text[:300]}")
    audio_resp = requests.get(audio_url, timeout=30)
    if audio_resp.status_code >= 400:
        raise RuntimeError(f"合成音频下载失败 HTTP {audio_resp.status_code}")
    if not audio_resp.content:
        raise RuntimeError("语音合成返回空音频")
    return audio_resp.content


def transcribe_audio(file_path: Path, file_url: str = "") -> str:
    """语音识别，返回识别文本。

    三级链路（前一环失败才走下一环，最终全部失败才抛 RuntimeError）：
    1. 魔搭 Fun-ASR（仅当 ASR_PROVIDER=modelscope 且配了 Key）；
       ⚠️ 实测魔搭推理网关目前没有任何音频端点（/v1/audio/* 全 404），保留仅为将来可用；
    2. **qwen3-asr-flash（默认主链路）**：多模态接口 + base64 直传，
       不依赖 PUBLIC_BASE_URL / ngrok，是当前唯一实测可用的路径；
    3. paraformer 录音文件转写（异步任务，需要公网可达 URL；ngrok 掉线即不可用）。
    """
    if settings.asr_provider == "modelscope" and _has_modelscope():
        try:
            return _transcribe_modelscope(file_path)
        except RuntimeError as exc:
            logging.getLogger(__name__).warning("魔搭语音识别失败，降级百炼：%s", exc)

    errors: list[str] = []
    # 主链路：qwen3-asr-flash（本地文件直传，无需公网地址）
    try:
        return _transcribe_qwen_asr(file_path)
    except RuntimeError as exc:
        errors.append(f"qwen3-asr-flash：{exc}")
        logging.getLogger(__name__).warning("qwen3-asr-flash 识别失败，降级 paraformer：%s", exc)
    # 兜底：paraformer 异步任务（需公网 URL）
    if not file_url:
        errors.append("paraformer 兜底不可用：未配置 PUBLIC_BASE_URL（无法提供公网音频地址）")
    else:
        try:
            return _transcribe_dashscope(file_url)
        except RuntimeError as exc:
            errors.append(f"paraformer：{exc}")
    # 把三层原因一并抛出，避免"任务失败"这种无法定位的信息
    raise RuntimeError("语音识别失败 → " + "；".join(errors))


# 音频容器魔数 → DashScope 认识的格式名。
# 必须按**真实字节**判断：Chrome 新版 MediaRecorder 产出的是 MP4/AAC，
# 但前端文件名固定叫 recording.webm（历史遗留），按扩展名判会喂错格式。
_AUDIO_MAGIC = (
    (b"RIFF", "wav"),      # 需配合偏移 8 的 WAVE 校验
    (b"OggS", "ogg"),
    (b"ID3", "mp3"),
    (b"\xff\xfb", "mp3"),
    (b"\xff\xf3", "mp3"),
    (b"\xff\xf2", "mp3"),
    (b"\x1a\x45\xdf\xa3", "webm"),  # EBML
    (b"fLaC", "flac"),
    (b"#!AMR", "amr"),
)


def audio_format(path: Path) -> str:
    """按文件头魔数推断音频格式（默认 wav，宁可失败也不要静默喂错容器）。"""
    try:
        with open(path, "rb") as fh:
            head = fh.read(16)
    except OSError:
        return "wav"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    for magic, fmt in _AUDIO_MAGIC:
        if head.startswith(magic):
            return fmt
    # MP4 家族：偏移 4 起是 'ftyp'（m4a 常见 brand 为 M4A ）
    if head[4:8] == b"ftyp":
        return "m4a" if head[8:11] == b"M4A" else "mp4"
    return "wav"


def _transcribe_qwen_asr(file_path: Path) -> str:
    """qwen3-asr-flash：多模态接口 + data URL 直传（无需公网 URL、无需 OSS 上传）。"""
    _require_key()
    fmt = audio_format(file_path)
    try:
        raw = Path(file_path).read_bytes()
    except OSError as exc:
        raise RuntimeError(f"读取音频失败：{exc}") from exc
    if not raw:
        raise RuntimeError("音频内容为空")
    payload = {
        "model": settings.llm_asr_model,
        "input": {
            "messages": [
                {"role": "user", "content": [
                    {"audio": f"data:audio/{fmt};base64,{base64.b64encode(raw).decode()}"},
                ]},
            ]
        },
        # enable_lid：自动识别语种（老人可能说方言/中英混说）；enable_itn：数字与单位规整
        "parameters": {"asr_options": {"enable_lid": True, "enable_itn": True}},
    }
    try:
        resp = requests.post(settings.asr_multimodal_api_url, headers=_headers(),
                             json=payload, timeout=120)
    except requests.RequestException as exc:
        raise RuntimeError(f"请求失败：{exc}") from exc
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        choices = resp.json().get("output", {}).get("choices") or []
    except ValueError as exc:
        raise RuntimeError(f"响应不是合法 JSON：{resp.text[:200]}") from exc
    text = ""
    for choice in choices:
        for part in (choice.get("message", {}) or {}).get("content") or []:
            if isinstance(part, dict):
                text += part.get("text") or ""
    text = text.strip()
    if not text:
        raise RuntimeError("识别结果为空")
    return text


def _transcribe_modelscope(file_path: Path) -> str:
    """魔搭语音识别：OpenAI 兼容 audio.transcriptions 接口。"""
    _require_modelscope_key()
    try:
        with open(file_path, "rb") as f:
            resp = _modelscope_client().audio.transcriptions.create(
                model=settings.asr_model,
                file=f,
            )
    except openai.APIError as exc:
        raise RuntimeError(f"魔搭语音识别失败：{exc}") from exc
    text = (resp.text or "").strip()
    if not text:
        raise RuntimeError("魔搭语音识别结果为空")
    return text


def _transcribe_dashscope(file_url: str) -> str:
    """百炼语音识别（paraformer 异步任务 REST），file_url 需公网可达。"""
    _require_key()
    if not file_url:
        raise RuntimeError("百炼语音识别需要公网可达的音频 URL（PUBLIC_BASE_URL 未配置）")
    payload = {
        "model": settings.llm_asr_model_para,
        "input": {"file_urls": [file_url]},
    }
    output = _wait_task(_submit_task(settings.asr_api_url, payload))
    results = output.get("results")
    if not isinstance(results, list) or not results:
        raise RuntimeError("语音识别任务输出缺少 results")
    transcription_url = results[0].get("transcription_url")
    if not transcription_url:
        raise RuntimeError("语音识别任务输出缺少 transcription_url")
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
