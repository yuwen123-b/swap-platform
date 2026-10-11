from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.v1 import auth, category, item, message, review, ai, feedback
from app.api.v1 import accessibility, elderly, panorama, user, volunteer
from app.api.v1.i18n import i18n_router, translate_router
from app.routers.admin import account as admin_account
from app.routers.admin import ai as admin_ai
from app.routers.admin import auth as admin_auth
from app.routers.admin import community as admin_community
from app.routers.admin import dashboard as admin_dashboard
from app.routers.admin import feedback as admin_feedback
from app.routers.admin import item as admin_item
from app.routers.admin import order as admin_order
from app.routers.admin import points as admin_points
from app.routers.admin import system as admin_system
from app.routers.admin import user as admin_user
from app.core.config import settings
from app.core.response import error_response
from app.db.pool import ensure_accessibility_columns, ensure_item_contact_column, initialize_schema

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
    (i18n_router, "/i18n", "国际化"),
    (translate_router, "", "翻译"),
    (user.router, "/user", "个人中心"),
]
for _router, _suffix, _tag in _NEW_ROUTERS:
    app.include_router(_router, prefix=f"/api{_suffix}", tags=[_tag])
    app.include_router(_router, prefix=f"{settings.api_prefix}{_suffix}", tags=[_tag])

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


@app.on_event("startup")
def startup() -> None:
    initialize_schema()
    ensure_item_contact_column()
    ensure_accessibility_columns()


UPLOAD_ROOT = Path(settings.upload_dir).resolve()
UPLOAD_ROOT.joinpath("items").mkdir(parents=True, exist_ok=True)
app.mount(
    f"{settings.api_prefix}/static",
    StaticFiles(directory=str(UPLOAD_ROOT)),
    name="static",
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    return error_response(400, str(exc.errors()), 400)


@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(_: Request, exc: FastAPIHTTPException):
    return error_response(exc.status_code, str(exc.detail), exc.status_code)


@app.get("/health")
def health():
    return {"status": "ok"}
