"""3D 物品模型生成服务（图生 3D → GLB，多服务商分派）。

支持两个服务商，由 `MODEL_3D_PROVIDER` 切换：

- **hunyuan（默认）**：腾讯混元 3D 极速版（hy-3d-express），走 TokenHub 网关
  （`TOKENHUB_API_URL/v1/api/3d/submit|query`，`Authorization: Bearer <API Key>`）。
  **不需要任何腾讯云 SDK，也没有 region 概念**——TokenHub 是 OpenAPI 风格的
  静态 Key 网关，不是 SecretId/SecretKey 的 TC3 签名接口。
- **tripo（回退）**：百炼 Tripo（DashScope 异步任务），代码原样保留，改一行 .env 即可切回。

公共流程（全程在 BackgroundTasks 线程内同步执行，不引入 Celery）：

1. 读物品 `images[0]` → `image_utils.ensure_local_jpeg` 落到
   `uploads/items/{id}/models/source.jpg`（远端图可能是 WEBP，必须归一成 JPEG）；
2. 交给 provider 生成 GLB 并**落盘**到 `uploads/items/{id}/models/model.glb`；
3. 回写 `item.model_url`（不带签名的静态地址）`/ model_status='ready' / model_generated_at`。

两个 provider 的下载链接都是**短期有效**（混元 COS 签名 24h、Tripo 2h），
因此拿到 URL 后必须立即下载落盘，绝不把外链存进 DB。

失败绝不静默降级：`model_status='failed'` 且失败原因落库到 `model_error`，
前端按优先级退回 360° 四视图 / 静态图。
（历史教训：360° 生成失败后偷偷降级为文生图重画，导致"看起来成功但其实全错"。）
"""
import base64
import json
import logging
import time
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

import requests

from app.core.config import settings
from app.core.security import sign_file_path
from app.db.pool import connection
from app.services.image_utils import ImageSourceError, ensure_local_jpeg, to_public_url

logger = logging.getLogger(__name__)

MODEL_STATUS_NONE = "none"
MODEL_STATUS_GENERATING = "generating"
MODEL_STATUS_READY = "ready"
MODEL_STATUS_FAILED = "failed"

# provider 标识
PROVIDER_HUNYUAN = "hunyuan"
PROVIDER_TRIPO = "tripo"

# 落盘文件名：GLB 固定名，前端 URL 不随物品更新而变（配合签名刷新）
MODEL_FILE_NAME = "model.glb"
SOURCE_IMAGE_NAME = "source.jpg"

# 失败原因落库长度上限（与 item.model_error 列宽一致）
MODEL_ERROR_MAX_LEN = 500

# generating 卡死兜底：起始时间距今超过该分钟数即判 failed（与用户约定一致）。
# 触发方式是「读时判定」——后端重启导致后台线程丢失时，前端不会永久转圈。
GENERATING_TIMEOUT_MINUTES = 5

# GLB 魔数：下载产物必须真的是 GLB（混元默认返回 obj，若参数失传会静默拿到 obj 字符串）
_GLB_MAGIC = b"glTF"

# 静态资源前缀（与 files.py 路由一致；读取时据此补签名）
_STATIC_PREFIX = f"{settings.api_prefix}/static/"


# ============================================================
# 开关与 URL 工具
# ============================================================
def current_provider() -> str:
    """当前生效的 3D 服务商（大小写不敏感），非法值在提交前由 _require_ready 拦下。"""
    return (settings.model_3d_provider or PROVIDER_HUNYUAN).strip().lower()


def is_enabled() -> bool:
    """3D 生成总开关（默认关）。后端硬校验：前端即使绕过也拿不到生成能力。"""
    return bool(settings.model_3d_enabled)


def models_dir(item_id: int) -> Path:
    return Path(settings.upload_dir).resolve() / "items" / str(item_id) / "models"


def model_relative_path(item_id: int) -> str:
    """uploads 下的相对路径（用于拼静态 URL 与计算落盘位置）。"""
    return f"items/{item_id}/models/{MODEL_FILE_NAME}"


def model_url(item_id: int) -> str:
    """落库用的静态地址（与 panorama_views 同口径：**不带**签名，读取时现场补）。"""
    return f"{_STATIC_PREFIX}{model_relative_path(item_id)}"


def sign_model_url(url: str) -> str:
    """给静态相对地址补 HMAC 签名；外链或不认识的形态原样返回（同 panorama 口径）。"""
    if not url or not url.startswith(_STATIC_PREFIX):
        return url
    relative = url[len(_STATIC_PREFIX):].split("?", 1)[0]
    return f"{_STATIC_PREFIX}{relative}?{sign_file_path(relative)}"


# ============================================================
# 状态落库
# ============================================================
def _update_status(
    item_id: int,
    status: str,
    model_url_value: str | None = None,
    error: str | None = None,
) -> None:
    """回写状态。error 仅在 failed 时有意义，其余状态一律清空（避免旧错因误导下一次排查）。"""
    # 失败原因可能很长（HTTP 响应体前后文），列宽 500，超长截断
    reason = (error or "")[:MODEL_ERROR_MAX_LEN] or None
    with connection() as conn:
        with conn.cursor() as cursor:
            if status == MODEL_STATUS_READY:
                cursor.execute(
                    "UPDATE item SET model_status=%s, model_url=%s, model_generated_at=NOW(), "
                    "model_error=NULL WHERE id=%s",
                    (status, model_url_value, item_id),
                )
            elif status == MODEL_STATUS_GENERATING:
                # 置 generating 时记录起始时间：供 get_model 做「卡死超时」兜底判断；
                # 同时清空上一次的失败原因，避免与新任务混淆
                cursor.execute(
                    "UPDATE item SET model_status=%s, model_generated_at=NOW(), "
                    "model_error=NULL WHERE id=%s",
                    (status, item_id),
                )
            elif status == MODEL_STATUS_FAILED:
                cursor.execute(
                    "UPDATE item SET model_status=%s, model_error=%s WHERE id=%s",
                    (status, reason, item_id),
                )
            else:
                cursor.execute(
                    "UPDATE item SET model_status=%s WHERE id=%s", (status, item_id)
                )


def _load_source_url(item_id: int) -> str:
    """取物品第一张图片的 URL 字符串（签名 URL 或公网外链均可）。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT images FROM item WHERE id=%s LIMIT 1", (item_id,))
            row = cursor.fetchone()
    if not row:
        raise RuntimeError("物品不存在")
    raw = row.get("images")
    if not raw:
        raise RuntimeError("该物品没有图片，无法生成 3D 模型")
    try:
        images = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError) as exc:
        raise RuntimeError("物品图片数据格式错误") from exc
    if not isinstance(images, list) or not images or not images[0]:
        raise RuntimeError("该物品没有图片，无法生成 3D 模型")
    return str(images[0])


def _require_ready() -> None:
    """提交前的环境前置校验，失败原因要能直接指导运维（按 provider 分别校验）。"""
    if not is_enabled():
        raise RuntimeError("3D 模型生成未开启（MODEL_3D_ENABLED=false）")

    provider = current_provider()
    if provider == PROVIDER_HUNYUAN:
        if not settings.tokenhub_api_key:
            raise RuntimeError("混元 3D 未配置密钥（TOKENHUB_API_KEY 为空）")
        if not settings.tokenhub_api_url:
            raise RuntimeError("混元 3D 未配置网关地址（TOKENHUB_API_URL 为空）")
        return
    if provider == PROVIDER_TRIPO:
        if not settings.dashscope_api_key:
            raise RuntimeError("Tripo 3D 生成未配置密钥（DASHSCOPE_API_KEY）")
        if not settings.public_base_url:
            raise RuntimeError("Tripo 需要公网可达的图片 URL（PUBLIC_BASE_URL 未配置）")
        return
    raise RuntimeError(
        f"未知的 3D 服务商（MODEL_3D_PROVIDER={settings.model_3d_provider}），"
        f"可选值：{PROVIDER_HUNYUAN} / {PROVIDER_TRIPO}"
    )


# ============================================================
# GLB 下载（两个 provider 共用）
# ============================================================
def _download_model(url: str, dest: Path) -> int:
    """下载 GLB 到 dest（先写 .part 再 replace，避免半截文件被前端当成品加载）。

    下载链接都是短期的（混元 COS 签名 24h、Tripo 2h），因此调用方拿到 URL 必须立即调用本函数。
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with requests.get(
            url, stream=True, timeout=settings.model_3d_download_timeout_seconds
        ) as resp:
            if resp.status_code >= 400:
                raise RuntimeError(f"GLB 下载失败 HTTP {resp.status_code}")
            with open(tmp, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        fh.write(chunk)
    except requests.RequestException as exc:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"GLB 下载失败：{exc}") from exc

    size = tmp.stat().st_size
    if size == 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("GLB 下载结果为空")
    # 魔数校验：混元 result_format 若未生效会返回 obj 文本，早期发现比前端白屏好。
    # 注意必须先关闭句柄再 unlink——Windows 上删除仍被打开的文件会抛 WinError 32。
    with open(tmp, "rb") as fh:
        magic = fh.read(4)
    if magic != _GLB_MAGIC:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("下载到的文件不是合法的 GLB（模型格式可能回退成了 obj）")
    tmp.replace(dest)
    return size


# ============================================================
# Provider：腾讯混元 3D（TokenHub 网关，同步 REST + 轮询）
# ============================================================
def _hunyuan_url(action: str) -> str:
    return f"{settings.tokenhub_api_url.rstrip('/')}/v1/api/3d/{action}"


def _hunyuan_headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.tokenhub_api_key}",
        "Content-Type": "application/json",
    }


def _hunyuan_error(body: dict) -> str:
    """把网关错误信封（error.message / error.code）拍平成一行可读文本。"""
    err = body.get("error") or {}
    if not isinstance(err, dict):
        return str(err)
    message = str(err.get("message") or "").strip()
    code = str(err.get("code") or "").strip()
    return " ".join(part for part in (code, message) if part).strip()


def _hunyuan_friendly(code: str, message: str) -> str:
    """把已知的失败原因翻译成能直接指导用户的中文（原文一并保留便于排查）。"""
    text = f"{code} {message}".lower()
    raw = f"{code} {message}".strip()

    # 命中判断集中在这里，避免在 if 里混用 and/or 造成优先级误读
    def hit(*keywords: str) -> bool:
        return any(keyword.lower() in text for keyword in keywords)

    if hit("concurrency", "并发", "too many request"):
        return f"混元 3D 同时只能处理 1 个任务（当前仍有任务在跑），请稍后重试。原始信息：{raw}"
    if hit("arrear", "欠费", "insufficient balance", "balance not enough"):
        return f"TokenHub 账户欠费或余额不足，请充值或领取免费体验包。原始信息：{raw}"
    if hit("quota", "额度不足", "积分不足", "exceeded"):
        return f"TokenHub 免费额度已用尽，请充值或开通后付费。原始信息：{raw}"
    if hit("unauthorized", "authentication", "invalid api", "auth failed", "密钥"):
        return f"TokenHub API Key 无效或已失效，请检查 TOKENHUB_API_KEY。原始信息：{raw}"
    if hit("risk", "风控", "content policy", "moderation"):
        return f"输入图片未通过内容风控，请更换图片后重试。原始信息：{raw}"
    if hit("job not found", "任务不存在"):
        return f"混元 3D 任务不存在或已过期（任务 id 有效期 24 小时）。原始信息：{raw}"
    return f"混元 3D 生成失败：{raw}"


def _encode_image_base64(image_path: Path) -> str:
    """本地 JPEG → base64 字符串；超过官方 6MB 上限时降质/缩边重编码。

    混元只支持 image_base64 / image_url / prompt 三选一，这里固定走 base64，
    因此不再依赖 PUBLIC_BASE_URL 公网可达（少一个易挂的环节）。
    """
    limit = settings.hunyuan_3d_max_image_bytes
    data = image_path.read_bytes()
    if len(data) > limit:
        data = _shrink_jpeg(image_path, limit)
    return base64.b64encode(data).decode("ascii")


def _shrink_jpeg(image_path: Path, limit: int) -> bytes:
    """降质 → 再缩边，直到编码后不超过 limit 字节。失败抛 RuntimeError。"""
    from PIL import Image

    try:
        with Image.open(image_path) as img:
            rgb = img.convert("RGB")
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"物品图片无法读取，不能编码为 base64：{exc}") from exc

    for quality in (85, 75, 65, 55, 45):
        buf = BytesIO()
        rgb.save(buf, "JPEG", quality=quality, optimize=True)
        if buf.tell() <= limit:
            logger.info("3D 源图超过 %s 字节，已按 quality=%s 重编码", limit, quality)
            return buf.getvalue()

    width, height = rgb.size
    for _ in range(3):
        width, height = int(width * 0.8), int(height * 0.8)
        if width < 128 or height < 128:
            break
        buf = BytesIO()
        rgb.resize((width, height)).save(buf, "JPEG", quality=70, optimize=True)
        if buf.tell() <= limit:
            logger.info("3D 源图超过 %s 字节，已缩边至 %sx%s 重编码", limit, width, height)
            return buf.getvalue()

    raise RuntimeError(f"物品图片过大，压缩后仍超过 {limit} 字节，无法用于 3D 生成")


def _hunyuan_submit(image_path: Path) -> str:
    """提交图生 3D 任务，返回任务 id（有效期 24 小时）。"""
    payload = {
        "model": settings.hunyuan_3d_model,
        # 与 prompt 互斥：文档明确「prompt 和 image_base64/image_url 不能同时存在」
        "image_base64": _encode_image_base64(image_path),
        # 默认返回 obj 格式组，前端 ModelViewer 只吃 GLB → 必须显式指定。
        # ⚠️ 官方文档写的小写 "glb"，但真机实测只认**大写**，传 "glb" 会被判
        #    InvalidParameterValue.InvalidResultFormat（合法值：OBJ/GLB/MP4/STL/FBX/USDZ）。
        "result_format": "GLB",
        "enable_pbr": bool(settings.hunyuan_3d_pbr),
    }
    resp = requests.post(
        _hunyuan_url("submit"), headers=_hunyuan_headers(), json=payload, timeout=60
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"混元 3D 任务提交失败 HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        body = resp.json()
    except ValueError as exc:
        raise RuntimeError(f"混元 3D 任务提交返回非 JSON：{resp.text[:200]}") from exc

    if body.get("error"):
        code = str((body.get("error") or {}).get("code") or "")
        message = str((body.get("error") or {}).get("message") or "")
        raise RuntimeError(_hunyuan_friendly(code, message))

    job_id = body.get("id")
    if not job_id:
        raise RuntimeError(f"混元 3D 任务提交响应缺少 id：{resp.text[:200]}")
    status = body.get("status")
    if status == "failed":
        raise RuntimeError(f"混元 3D 任务提交后立即失败：{resp.text[:200]}")
    return str(job_id)


def _hunyuan_wait(job_id: str) -> list:
    """轮询直至 completed，返回 data 数组；失败 / 超时抛 RuntimeError。"""
    deadline = time.time() + settings.hunyuan_3d_timeout_seconds
    payload = {"model": settings.hunyuan_3d_model, "id": job_id}
    last_status = "queued"
    while time.time() < deadline:
        resp = requests.post(
            _hunyuan_url("query"), headers=_hunyuan_headers(), json=payload, timeout=20
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"混元 3D 任务查询失败 HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            body = resp.json()
        except ValueError as exc:
            raise RuntimeError(f"混元 3D 任务查询返回非 JSON：{resp.text[:200]}") from exc

        if body.get("error"):
            code = str((body.get("error") or {}).get("code") or "")
            message = str((body.get("error") or {}).get("message") or "")
            raise RuntimeError(_hunyuan_friendly(code, message))

        last_status = str(body.get("status") or "")
        if last_status == "completed":
            data = body.get("data")
            if not isinstance(data, list) or not data:
                raise RuntimeError("混元 3D 生成完成但未返回模型文件")
            return data
        if last_status == "failed":
            # 失败时部分实现会把原因放在 error 里（已在上面拦截），这里兜底
            raise RuntimeError("混元 3D 任务执行失败（未提供详细原因）")
        time.sleep(settings.hunyuan_3d_poll_interval_seconds)
    raise RuntimeError(
        f"混元 3D 生成超时（超过 {settings.hunyuan_3d_timeout_seconds} 秒未完成，"
        f"最后状态：{last_status or 'unknown'}）"
    )


def _hunyuan_extract_glb_url(data: list) -> str:
    """从 data 数组里取 type=glb 的下载地址（COS 签名 URL，24 小时有效）。"""
    for row in data:
        if not isinstance(row, dict):
            continue
        if str(row.get("type") or "").lower() == "glb" and row.get("url"):
            return str(row["url"])
    # result_format=glb 生效时 data 里通常只有一项；兜底取第一个带 url 的条目
    for row in data:
        if isinstance(row, dict) and row.get("url"):
            return str(row["url"])
    raise RuntimeError("混元 3D 生成结果缺少 GLB 下载地址")


def _generate_hunyuan(item_id: int, jpeg_path: Path) -> dict:
    """混元分支：提交 → 轮询 → 下载落盘，返回结果摘要。"""
    job_id = _hunyuan_submit(jpeg_path)
    logger.info(
        "物品 %s 混元 3D 任务已提交：job_id=%s model=%s pbr=%s",
        item_id, job_id, settings.hunyuan_3d_model, settings.hunyuan_3d_pbr,
    )
    data = _hunyuan_wait(job_id)
    glb_url = _hunyuan_extract_glb_url(data)
    # COS 签名 URL 24 小时失效 → 立即下载（与 Tripo 同策略）
    size = _download_model(glb_url, models_dir(item_id) / MODEL_FILE_NAME)
    _update_status(item_id, MODEL_STATUS_READY, model_url(item_id))
    return {
        "item_id": item_id,
        "status": MODEL_STATUS_READY,
        "model_url": model_url(item_id),
        "bytes": size,
        "task_id": job_id,
        "provider": PROVIDER_HUNYUAN,
    }


# ============================================================
# Provider：百炼 Tripo（回退分支，逻辑与切换前完全一致）
# ============================================================
def _tripo_submit_task(image_url: str) -> str:
    """提交 Tripo 异步任务，返回 task_id。"""
    payload = {
        "model": settings.model_3d_model,
        "input": {"image": image_url},
        # 只传 texture_quality：geometry_quality 仅 Tripo-H3.1 支持，
        # 对 P1.0 传它会被判 InvalidParameter（见官方 API 文档）。
        "parameters": {"texture_quality": settings.model_3d_texture_quality},
    }
    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }
    resp = requests.post(settings.model_3d_api_url, headers=headers, json=payload, timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(f"3D 任务提交失败 HTTP {resp.status_code}: {resp.text[:300]}")
    body = resp.json()
    task_id = (body.get("output") or {}).get("task_id")
    if not task_id:
        raise RuntimeError(f"3D 任务提交响应缺少 task_id：{resp.text[:200]}")
    return str(task_id)


def _tripo_wait_task(task_id: str) -> dict:
    """轮询直至 SUCCEEDED，返回 output；失败 / 超时抛 RuntimeError。"""
    deadline = time.time() + settings.model_3d_timeout_seconds
    headers = {"Authorization": f"Bearer {settings.dashscope_api_key}"}
    url = settings.task_api_url.format(task_id=task_id)
    while time.time() < deadline:
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code >= 400:
            raise RuntimeError(f"3D 任务查询失败 HTTP {resp.status_code}: {resp.text[:300]}")
        output = resp.json().get("output") or {}
        status = output.get("task_status")
        if status == "SUCCEEDED":
            return output
        if status in ("FAILED", "CANCELED", "UNKNOWN"):
            reason = " ".join(
                str(output.get(key) or "") for key in ("code", "message")
            ).strip()
            raise RuntimeError(f"3D 生成失败（{status}）：{reason or '无错误详情'}")
        time.sleep(settings.model_3d_poll_interval_seconds)
    raise RuntimeError(f"3D 生成超时（超过 {settings.model_3d_timeout_seconds} 秒未完成）")


def _tripo_extract_model_url(output: dict) -> str:
    """从 results 里取 GLB 下载地址（默认 pbr=true 返回 pbr_model_url）。"""
    results = output.get("results")
    if isinstance(results, list):
        for row in results:
            if isinstance(row, dict):
                url = row.get("pbr_model_url") or row.get("base_model_url")
                if url:
                    return str(url)
    raise RuntimeError("3D 生成结果缺少模型下载地址")


def _generate_tripo(item_id: int, jpeg_path: Path) -> dict:
    """Tripo 分支：本地 JPEG → 签名公网 URL → 提交 → 轮询 → 下载落盘。"""
    upload_root = Path(settings.upload_dir).resolve()
    try:
        relative = jpeg_path.resolve().relative_to(upload_root).as_posix()
    except ValueError as exc:
        raise RuntimeError("物品原图不在 uploads 目录内，无法生成公网访问地址") from exc
    public_url = to_public_url(relative)

    task_id = _tripo_submit_task(public_url)
    logger.info(
        "物品 %s 3D 任务已提交：task_id=%s model=%s", item_id, task_id, settings.model_3d_model
    )
    output = _tripo_wait_task(task_id)

    # 链接 2 小时失效 → 立即下载
    glb_url = _tripo_extract_model_url(output)
    size = _download_model(glb_url, models_dir(item_id) / MODEL_FILE_NAME)

    _update_status(item_id, MODEL_STATUS_READY, model_url(item_id))
    return {
        "item_id": item_id,
        "status": MODEL_STATUS_READY,
        "model_url": model_url(item_id),
        "bytes": size,
        "task_id": task_id,
        "provider": PROVIDER_TRIPO,
    }


# ============================================================
# 对外入口
# ============================================================
def generate_3d_model(item_id: int) -> dict:
    """同步生成 3D 模型并落库；任何环节失败抛出 RuntimeError。

    按 `MODEL_3D_PROVIDER` 分派到具体 provider，前置的「取图 → 归一成 JPEG」两步共用。
    """
    _require_ready()

    # 1) 原图 → 本地 JPEG（两个 provider 都只吃标准格式；且上传原图可能是 WEBP）
    source_url = _load_source_url(item_id)
    try:
        jpeg_path = ensure_local_jpeg(source_url, dest=models_dir(item_id) / SOURCE_IMAGE_NAME)
    except ImageSourceError as exc:
        raise RuntimeError(f"物品原图无法用于 3D 生成：{exc}") from exc

    # 2) 分派
    provider = current_provider()
    if provider == PROVIDER_HUNYUAN:
        return _generate_hunyuan(item_id, jpeg_path)
    if provider == PROVIDER_TRIPO:
        return _generate_tripo(item_id, jpeg_path)
    raise RuntimeError(f"未知的 3D 服务商：{provider}")


def run_generate(item_id: int) -> None:
    """BackgroundTasks 入口：先置 generating，失败置 failed，绝不抛出阻断调用方。"""
    try:
        _update_status(item_id, MODEL_STATUS_GENERATING)
    except Exception:  # noqa: BLE001 状态置位失败即无后续意义，直接记录退出
        logger.exception("物品 %s model_status=generating 写入失败", item_id)
        return
    try:
        generate_3d_model(item_id)
    except Exception as exc:  # noqa: BLE001 失败一律显式标记，绝不静默降级
        logger.warning("物品 %s 3D 模型生成失败：%s", item_id, exc)
        try:
            # 原因一并落库：前端轮询即可拿到，用户不必再靠终端/重放脚本定位
            _update_status(item_id, MODEL_STATUS_FAILED, error=str(exc))
        except Exception:  # noqa: BLE001 状态回写失败仅记录日志
            logger.exception("物品 %s model_status 回写失败", item_id)


def get_model(item_id: int) -> dict:
    """查询 3D 模型状态，供前端轮询；model_url 仅 ready 时给出（读取时补签名）。

    failed 时额外返回 model_error（失败原因原文），供前端向用户解释「为什么没生成出来」。
    """
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT model_status, model_url, model_generated_at, model_error "
                "FROM item WHERE id=%s LIMIT 1",
                (item_id,),
            )
            row = cursor.fetchone()
    if not row:
        raise ValueError("物品不存在")

    status = row.get("model_status") or MODEL_STATUS_NONE
    raw_generated = row.get("model_generated_at")
    error = row.get("model_error")

    # generating 卡死兜底：起始时间距今超过阈值即判失败（如后台线程随重启丢失）
    if status == MODEL_STATUS_GENERATING and isinstance(raw_generated, datetime):
        if datetime.now() - raw_generated > timedelta(minutes=GENERATING_TIMEOUT_MINUTES):
            reason = (
                f"生成超过 {GENERATING_TIMEOUT_MINUTES} 分钟未完成"
                "（后台任务可能随服务重启中断），已标记为失败，可重新生成"
            )
            logger.warning(
                "物品 %s 3D 生成超过 %s 分钟未完成，标记为 failed",
                item_id, GENERATING_TIMEOUT_MINUTES,
            )
            try:
                _update_status(item_id, MODEL_STATUS_FAILED, error=reason)
                error = reason
            except Exception:  # noqa: BLE001 状态回写失败仅记录日志
                logger.exception("物品 %s model_status 超时回写失败", item_id)
            status = MODEL_STATUS_FAILED

    url = None
    if status == MODEL_STATUS_READY and row.get("model_url"):
        url = sign_model_url(str(row["model_url"]))
    return {
        "item_id": item_id,
        "model_status": status,
        "model_url": url,
        # 仅 failed 时透出原因；其余状态即使列里残留旧值也不外泄
        "model_error": error if status == MODEL_STATUS_FAILED else None,
    }
