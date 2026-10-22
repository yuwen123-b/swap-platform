"""3D 物品模型接口：触发生成、查询生成结果。

POST /generate  接受 JSON { item_id }，用物品已有图片触发后台 3D 生成
GET  /{id}     查询生成状态与 GLB 地址

与 panorama 接口的分工：本模块是**新增的第三条降级链顶端**——
`model ready → panorama ready → 静态图`。`PanoramaViewer` 与 360° 全部逻辑不受影响。
"""
import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.core.response import success
from app.core.security import get_current_user_id
from app.db.pool import connection
from app.schemas.model import ModelGenerateRequest
from app.services import three_d_service

router = APIRouter()


@router.post("/generate")
def generate_model(
    req: ModelGenerateRequest,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id),
):
    """触发 3D 模型生成；立即返回 generating，前端轮询 GET /{item_id}。

    成本控制：`MODEL_3D_ENABLED` 在后端硬校验（每次生成约 2~3.5 元），
    即使前端隐藏按钮被绕过，请求也会被 403 拦下。
    """
    if not three_d_service.is_enabled():
        raise HTTPException(403, "3D 模型生成功能未开启")

    item_id = req.item_id
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT user_id, images, model_status FROM item WHERE id=%s LIMIT 1", (item_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(404, "物品不存在")
            if row["user_id"] != user_id:
                raise HTTPException(403, "无权操作该物品")
            # 重复触发保护：正在生成时拒绝，避免并发烧模型额度（单次 2~3.5 元）
            if (row.get("model_status") or "none") == three_d_service.MODEL_STATUS_GENERATING:
                raise HTTPException(400, "3D 模型正在生成中，请稍候刷新查看，请勿重复触发")

    raw_images = row.get("images")
    if not raw_images:
        raise HTTPException(400, "该物品没有图片，无法生成 3D 模型")
    try:
        images = json.loads(raw_images) if isinstance(raw_images, str) else raw_images
    except (TypeError, ValueError):
        raise HTTPException(400, "物品图片数据格式错误")
    if not isinstance(images, list) or not images:
        raise HTTPException(400, "该物品没有图片，无法生成 3D 模型")

    # BackgroundTasks 异步执行：请求立即返回，失败由 run_generate 内部落库为 failed
    background_tasks.add_task(three_d_service.run_generate, item_id)
    return success(
        {"item_id": item_id, "status": three_d_service.MODEL_STATUS_GENERATING},
        "3D 模型生成中，约需 2-4 分钟，完成后可在物品详情页查看。",
    )


@router.get("/{item_id}")
def get_model(item_id: int):
    try:
        result = three_d_service.get_model(item_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return success(result)
