import asyncio
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import auth, category, demand, favorite, item, message, order, review, ai, feedback
from app.api.v1 import accessibility, elderly, files, merchant, model, panorama, user, user_center, volunteer
from app.api.v1 import recycle
from app.routers.admin import account as admin_account
from app.routers.admin import ai as admin_ai
from app.routers.admin import auth as admin_auth
from app.routers.admin import community as admin_community
from app.routers.admin import dashboard as admin_dashboard
from app.routers.admin import feedback as admin_feedback
from app.routers.admin import item as admin_item
from app.routers.admin import merchant as admin_merchant
from app.routers.admin import order as admin_order
from app.routers.admin import points as admin_points
from app.routers.admin import recycle as admin_recycle
from app.routers.admin import system as admin_system
from app.routers.admin import user as admin_user
from app.core.config import settings
from app.core.response import error_response
from app.db.pool import (
    ensure_accessibility_columns,
    ensure_demand_table,
    ensure_item_contact_column,
    ensure_location_columns,
    ensure_merchant_seed,
    ensure_merchant_tables,
    ensure_model_columns,
    ensure_notification_columns,
    ensure_personal_center_tables,
    ensure_points_log_columns,
    ensure_points_log_unique_index,
    ensure_points_rules,
    ensure_recycle_tables,
    initialize_schema,
)
from app.services.merchant_service import MerchantError, expire_redemptions_loop
from app.services.points_service import PointsAwardError
from app.services.recycle_service import RecycleError

app = FastAPI(title=settings.app_name, version="1.0.0")
cors_origin_regex = r"https?://.*" if settings.debug else settings.cors_origin_regex
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=cors_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    max_age=600,
)

api = app.router
app.include_router(auth.router, prefix=f"{settings.api_prefix}/auth", tags=["认证"])
app.include_router(item.router, prefix=f"{settings.api_prefix}/items", tags=["物品"])
app.include_router(category.router, prefix=f"{settings.api_prefix}/categories", tags=["分类"])
app.include_router(review.router, prefix=f"{settings.api_prefix}/reviews", tags=["评价"])
app.include_router(ai.router, prefix=f"{settings.api_prefix}/ai", tags=["AI"])
app.include_router(feedback.router, prefix=f"{settings.api_prefix}/feedback", tags=["程序评价"])
app.include_router(message.router, prefix=f"{settings.api_prefix}/messages", tags=["私信"])

# 四个增量功能路由：契约路径（/api/xxx）与 API 前缀路径（/api/v1/xxx）双挂载
_NEW_ROUTERS = [
    (elderly.router, "/elderly", "助老模式"),
    (accessibility.router, "/accessibility", "无障碍模式"),
    (volunteer.router, "/volunteer", "志愿者"),
    (panorama.router, "/panorama", "360°视图"),
    (model.router, "/model", "3D模型"),
    (user.router, "/user", "个人中心"),
    # 个人中心扩展（我的物品 / 碳积分）：与 user.router 同前缀，路径不重叠，无 catch-all 冲突
    (user_center.router, "/user", "个人中心-扩展"),
    # 我的收藏：同上复用 /user 前缀，路径为 /favorites/*，与上面两者均不重叠
    (favorite.router, "/user", "我的收藏"),
    # 我想要的（需求）：个人需求路径 /demands*，与上面三者仍不重叠
    (demand.router, "/user", "我想要的"),
]
for _router, _suffix, _tag in _NEW_ROUTERS:
    app.include_router(_router, prefix=f"/api{_suffix}", tags=[_tag])
    app.include_router(_router, prefix=f"{settings.api_prefix}{_suffix}", tags=[_tag])

# 公开需求墙：路径必须是 /demands（不能复用 /user 前缀，否则与「我的需求列表」同路径冲突）
app.include_router(demand.wall_router, prefix="/api/demands", tags=["需求墙"])
app.include_router(demand.wall_router, prefix=f"{settings.api_prefix}/demands", tags=["需求墙"])

# 我的交换：路径是 /orders*（不带 /user 前缀，故不能并入 _NEW_ROUTERS），
# 与需求墙同套路单独双挂载。管理端订单是 /api/admin/orders，前缀不同无冲突。
app.include_router(order.router, prefix="/api/orders", tags=["我的交换"])
app.include_router(order.router, prefix=f"{settings.api_prefix}/orders", tags=["我的交换"])

# 商家端闭环：商家端 9 个 + 用户端 4 个接口共用 /merchant 前缀，双挂载与 _NEW_ROUTERS 同口径。
# 用户侧路径全部以字面量段开头（/products*、/shops*、/redeem、/redemptions*），
# 与通配段路径无段落重叠，不存在「通配吞掉静态路由」的歧义。
app.include_router(merchant.router, prefix="/api/merchant", tags=["商家端"])
app.include_router(merchant.router, prefix=f"{settings.api_prefix}/merchant", tags=["商家端"])

# 平台回收（二期）：估价 / 我的回收单 / 取消。与 /orders 同套路单独双挂载
# （不能并入 _NEW_ROUTERS，那是 /user 前缀族）。估价放独立 router，
# 避免 /items/{item_id} 把 recycle 字符串吞成 item_id（422 陷阱，见 recycle.py 文件头）。
app.include_router(recycle.router, prefix="/api/recycle", tags=["平台回收"])
app.include_router(recycle.router, prefix=f"{settings.api_prefix}/recycle", tags=["平台回收"])

# 管理端路由（统一挂载于 /api/admin）
app.include_router(admin_auth.router, prefix="/api/admin", tags=["管理端-登录"])
app.include_router(admin_account.router, prefix="/api/admin", tags=["管理端-账号"])
app.include_router(admin_system.router, prefix="/api/admin", tags=["管理端-系统配置"])
app.include_router(admin_user.router, prefix="/api/admin", tags=["管理端-用户"])
app.include_router(admin_item.router, prefix="/api/admin", tags=["管理端-物品"])
app.include_router(admin_order.router, prefix="/api/admin", tags=["管理端-订单"])
app.include_router(admin_community.router, prefix="/api/admin", tags=["管理端-社区"])
app.include_router(admin_points.router, prefix="/api/admin", tags=["管理端-积分"])
app.include_router(admin_ai.router, prefix="/api/admin", tags=["管理端-AI监控"])
app.include_router(admin_feedback.router, prefix="/api/admin", tags=["管理端-情感分析"])
app.include_router(admin_dashboard.router, prefix="/api/admin", tags=["管理端-看板"])
# 管理端-商家：按决策只挂 /api/admin（与其它 admin_* 一致，不额外挂 /api/v1/admin）
app.include_router(admin_merchant.router, prefix="/api/admin/merchant", tags=["管理端-商家"])
# 管理端-平台回收：同口径只挂 /api/admin/recycle
app.include_router(admin_recycle.router, prefix="/api/admin/recycle", tags=["管理端-平台回收"])


@app.on_event("startup")
def startup() -> None:
    initialize_schema()
    ensure_item_contact_column()
    ensure_accessibility_columns()
    ensure_location_columns()
    # 3D 模型：item 补 model_url / model_status / model_generated_at / model_error 四列（幂等）
    ensure_model_columns()
    ensure_notification_columns()
    ensure_points_rules()
    # 先补列（线上旧表缺 balance 会导致积分明细 500），再建唯一索引
    ensure_points_log_columns()
    ensure_points_log_unique_index()
    # 个人中心扩展区：我的收藏（复用既有 favorite 表 + 补唯一索引）
    ensure_personal_center_tables()
    # 我想要的：swap_demand 表（个人需求 + 首页公开需求墙共用）
    ensure_demand_table()
    # 商家端闭环：5 张表 + 索引，随后写入模拟商家数据（幂等，绝不覆盖管理员改动）
    ensure_merchant_tables()
    ensure_merchant_seed()
    # 平台回收（二期）：2 张新表 + item 补 accept_points / recycle_status（幂等）
    ensure_recycle_tables()


@app.on_event("startup")
async def start_redemption_expiration_worker() -> None:
    """启动「兑换单过期退还积分」后台扫描任务（每小时一次）。

    刻意继续用 `@app.on_event("startup")` 而**不改用 lifespan**：
    FastAPI 一旦传入 `lifespan`，既有的 `on_event("startup")` 处理器（initialize_schema
    等全部迁移）会被**静默跳过**，后端会以「表没建」的状态起来。
    注册顺序在 `startup()` 之后，保证任务启动时 5 张表已就绪。

    任务本身对 DB 的调用是同步阻塞的 pymysql，服务层用 `asyncio.to_thread`
    丢到线程池执行，不会阻塞事件循环。
    """
    app.state.redemption_expire_task = asyncio.create_task(expire_redemptions_loop())


@app.on_event("shutdown")
async def stop_redemption_expiration_worker() -> None:
    """关闭时取消后台扫描任务，避免进程退出时残留协程告警。"""
    task = getattr(app.state, "redemption_expire_task", None)
    if task is not None:
        task.cancel()


UPLOAD_ROOT = Path(settings.upload_dir).resolve()
UPLOAD_ROOT.joinpath("items").mkdir(parents=True, exist_ok=True)
# 静态资源改为受控路由（签名校验 + nosniff），不再直接挂载目录，杜绝图片直链访问。
# 挂在 /api/v1/static 前缀下，与旧 URL 形态兼容；files.router 内部自行校验签名。
app.include_router(files.router, prefix=f"{settings.api_prefix}/static", tags=["文件"])


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    return error_response(400, str(exc.errors()), 400)


@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(_: Request, exc: FastAPIHTTPException):
    return error_response(exc.status_code, str(exc.detail), exc.status_code)


@app.exception_handler(PointsAwardError)
async def points_award_exception_handler(_: Request, exc: PointsAwardError):
    """积分重复发放（命中唯一索引）：属于业务冲突，返回 409 + 明确提示。

    此时调用方的 `with connection()` 已把整笔事务回滚——
    user.points 的加分与 points_log 的流水一起撤销，不会留下半截脏账。
    """
    return error_response(409, exc.message, 409)


@app.exception_handler(MerchantError)
async def merchant_exception_handler(_: Request, exc: MerchantError):
    """商家端业务错误：由服务层带上明确的状态码与中文提示。

    例如「积分不足」（400）、「店铺尚未通过审核」（403）、「核销码不属于本店」（403）、
    「商家不存在」（404）。抛出时调用方的事务已回滚，不会留下半截脏账。
    """
    return error_response(exc.status_code, exc.message, exc.status_code)


@app.exception_handler(RecycleError)
async def recycle_exception_handler(_: Request, exc: RecycleError):
    """平台回收业务错误：由服务层带上明确的状态码与中文提示。

    例如「该物品已在回收流程中」（400）、「只能操作自己的回收单」（403）、
    「回收单不存在」（404）、批量销售并发冲突（409）。
    抛出时调用方的事务已回滚，不会留下半截脏账。
    """
    return error_response(exc.status_code, exc.message, exc.status_code)


@app.get("/health")
def health():
    return {"status": "ok"}
