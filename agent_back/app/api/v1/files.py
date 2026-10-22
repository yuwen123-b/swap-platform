"""受控文件访问路由：替代 StaticFiles 目录直挂，杜绝图片直链访问。

旧实现用 app.mount(...StaticFiles...) 把整个 uploads/ 目录对外暴露，
任何人拿到 URL 即可无鉴权读取，且响应由 StaticFiles 决定，无法注入
nosniff 等安全响应头，配合可伪造 Content-Type 的上传曾构成存储型 XSS 风险。

现改为本路由统一提供服务：
1. 校验 URL 上的 HMAC 签名与有效期（sign_file_path 生成）；
2. 解析路径后强制校验必须落在 uploads 目录内，防路径穿越；
3. 按扩展名白名单映射 Content-Type，并强制 nosniff，杜绝浏览器内容嗅探。

URL 形态与旧路径保持一致的 /api/v1/static/ 前缀，仅追加 ?exp=&sig= 参数，
因此依赖该前缀解析相对路径的既有模块（panorama / accessibility）不受影响。
"""
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.security import verify_file_signature

router = APIRouter()

# 扩展名 → MIME 白名单：不依据用户输入或存储内容，仅按白名单映射
# .glb/.gltf：3D 模型（Tripo 图生 3D 产物）。此前漏掉会导致详情页模型加载 403
# 「不支持的文件类型」，与图片同样走签名校验 + nosniff。
# .wav/.mp3/.m4a/.ogg：助老模式 TTS 播报音频。此前同样漏掉 —— 助老页拿到的
# response_audio_url 一律 403，前端只能永远走浏览器合成兜底，表现为「有时有声有时没声」。
_EXT_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
}


def _resolve_within_upload_root(relative_path: str) -> Path:
    """把 URL 相对路径解析为绝对路径，并确保其位于 uploads 目录内。"""
    root = Path(settings.upload_dir).resolve()
    target = (root / relative_path).resolve()
    if target != root and root not in target.parents:
        raise HTTPException(403, "非法文件路径")
    return target


@router.get("/{relative_path:path}")
def read_static_file(
    request: Request,
    relative_path: str,
    exp: int = Query(..., description="签名过期时间戳（秒）"),
    sig: str = Query(..., description="HMAC 签名"),
):
    # 1. 签名校验：路径 + 过期时间参与签名，任一被篡改即失败
    if not verify_file_signature(relative_path, exp, sig):
        raise HTTPException(403, "文件链接无效或已过期")

    # 2. 路径穿越防护
    target = _resolve_within_upload_root(relative_path)
    if not target.is_file():
        raise HTTPException(404, "文件不存在")

    # 3. 扩展名白名单：非白名单类型一律拒绝，避免以附件形式外泄其他文件
    content_type = _EXT_CONTENT_TYPES.get(target.suffix.lower())
    if not content_type:
        raise HTTPException(403, "不支持的文件类型")

    # 4. 强制安全响应头：nosniff 阻止浏览器内容嗅探，inline 明确内联展示
    headers = {
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": "inline",
        "Cache-Control": "private, max-age=3600",
    }
    return FileResponse(target, media_type=content_type, headers=headers)
