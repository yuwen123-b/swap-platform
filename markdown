# 社区旧物互换平台——管理端需求分析文档（PRD）

## 1. 项目概述

### 1.1 项目名称
社区旧物互换平台——管理端（agent_admin_front）

### 1.2 项目背景
社区旧物互换平台面向社区居民提供闲置物品发布、交换、赠送、社区互动等功能。为保证平台内容合规、交易安全、用户行为规范，需要一套独立的管理后台，支持多角色分级管理，实现用户、物品、订单、社区内容、积分和 AI 能力的统一运营与审核。

### 1.3 项目目标
- 提供独立的管理端登录，基于 `admin` 表认证
- 支持三种角色权限分级：超级管理员、运营、审核员
- 实现用户管理、物品管理、订单管理、社区内容管理、积分管理、AI 监控
- 实现物品上架审核、举报处理等审核流程
- 管理端前端为独立 Vue 项目 `agent_admin_front`，后端与用户端共用

---

## 2. 角色与权限

### 2.1 角色定义

| 角色 | role 值 | 说明 |
|------|--------|------|
| 超级管理员 | 1 | 拥有全部权限 |
| 运营 | 2 | 可管理业务数据，不能管理管理员账号和系统配置 |
| 审核员 | 3 | 只读 + 审核权限，不能删除或修改核心数据 |

### 2.2 权限矩阵

| 功能模块 | 超管(1) | 运营(2) | 审核员(3) |
|----------|:------:|:------:|:--------:|
| 管理员账号管理（增删改查） | ✅ | ❌ | ❌ |
| 系统配置管理 | ✅ | ❌ | ❌ |
| 用户管理（查看/禁用/删除） | ✅ | ✅ | 只读 |
| 物品管理（增删改查） | ✅ | ✅ | 只读 |
| 物品上架审核 | ✅ | ✅ | ✅ |
| 订单管理 | ✅ | ✅ | 只读 |
| 社区内容管理 | ✅ | ✅ | 只读 + 举报处理 |
| 举报处理 | ✅ | ✅ | ✅ |
| 积分管理 | ✅ | ✅ | 只读 |
| AI 监控 | ✅ | ✅ | ❌ |
| 数据统计/看板 | ✅ | ✅ | ✅ |

> 权限校验在后端接口层通过 `role` 字段控制，前端根据角色隐藏/禁用菜单与按钮（前端控制仅作体验优化，后端必须强校验）。

---

## 3. 功能需求

### 3.1 登录模块

- 管理员通过独立的登录页登录，输入 `username` + `password`
- 后端查询 `admin` 表，校验 `password_hash`（推荐 bcrypt 或 sha256，兼容已有实现）
- 校验 `status=1`（启用），否则拒绝登录
- 登录成功返回 JWT，载荷包含 `admin_id`、`username`、`role`
- 前端保存 token 与角色信息，路由守卫据此控制页面访问

### 3.2 管理员账号管理（仅超管）

- 管理员列表：分页展示 `id`、`username`、`real_name`、`role`、`status`、`created_at`
- 新增管理员：设置用户名、密码、姓名、角色
- 编辑管理员：可修改姓名、角色、状态（禁用/启用）
- 重置密码
- 删除管理员（不能删除自己）
- 角色分配：1/2/3

### 3.3 系统配置（仅超管）

- 平台基础参数：平台名称、公告、联系方式
- 积分规则：发布物品得分、成功交换得分、举报扣分等
- 审核开关：是否开启物品上架人工审核
- 敏感词库维护（可扩展）

### 3.4 用户管理

- 用户列表：分页、按用户名/手机号/状态搜索
- 用户详情：基本信息、发布物品数、交换记录、积分余额
- 操作：
  - 超管/运营：禁用/启用、删除
  - 审核员：仅查看

### 3.5 物品管理

- 物品列表：分页、按名称/分类/状态/发布者搜索
- 物品详情：图片、描述、分类、期望交换物、发布者、发布时间
- 操作：
  - 超管/运营：编辑、下架、删除
  - 审核员：只读，可参与审核

### 3.6 物品上架审核

- 待审核列表：展示所有提交审核的物品
- 审核操作：
  - 通过：物品状态改为"已上架"
  - 拒绝：填写拒绝理由，状态改为"已拒绝"
- 所有角色均可执行审核

### 3.7 订单管理

- 订单列表：分页、按状态/时间/用户搜索
- 订单状态：待确认、交换中、已完成、已取消、争议中
- 操作：
  - 超管/运营：修改状态、介入处理、取消订单
  - 审核员：只读

### 3.8 社区内容管理

- 帖子/评论列表：分页、按内容/用户/时间搜索
- 操作：
  - 超管/运营：编辑、删除、置顶
  - 审核员：只读 + 处理举报

### 3.9 举报处理

- 举报列表：举报人、被举报对象（物品/帖子/用户）、举报理由、状态
- 操作：
  - 处理：标记为"已处理"，可对被举报内容执行下架/删除
  - 驳回：标记为"已驳回"
- 所有角色均可处理

### 3.10 积分管理

- 积分规则配置（超管）
- 积分流水：分页展示用户积分变化记录
- 手动调整：超管/运营可为用户增减积分并填写原因
- 审核员：只读

### 3.11 AI 监控

- 调用日志：AI 接口调用记录（智能推荐、敏感词检测等）
- 异常告警：模型调用失败、超时、异常输出
- 使用统计：调用次数、成功率、平均耗时
- 仅超管和运营可访问

### 3.12 数据看板（所有角色）

- 概览数据：用户总数、物品总数、订单总数、今日新增
- 图表：近7天发布/交换趋势、热门分类、活跃用户
- 审核员也可查看只读统计

---

## 4. 非功能需求

### 4.1 技术栈

- 前端：Vue 3 + Vite + Element Plus + Axios + Vue Router + Pinia
- 后端：复用原有 FastAPI 后端
- 数据库：MySQL（沿用 `travel` 或项目已有数据库）
- 包管理：前端 npm，后端 uv

### 4.2 性能

- 列表接口响应 < 500ms
- 支持并发管理员 ≥ 20

### 4.3 安全

- 密码使用 bcrypt 或 md5（与现有实现保持一致）
- JWT 携带 `role`，后端接口强校验
- 敏感操作记录操作日志（可选）

### 4.4 兼容性

- 支持主流浏览器
- 响应式适配 1366×768 及以上分辨率

---

## 5. 系统架构

### 5.1 总体架构

```
[管理员浏览器] ⇄ [agent_admin_front (Vue3)] ⇄ [FastAPI 后端] ⇄ [MySQL]
                                                    ⇅
                                             [AI 服务 / 日志]
```

### 5.2 前端目录结构

```
agent_admin_front/
├── public/
├── src/
│   ├── api/                 # 接口封装
│   │   ├── request.js
│   │   ├── auth.js
│   │   ├── admin.js         # 管理员账号管理
│   │   ├── user.js
│   │   ├── item.js
│   │   ├── order.js
│   │   ├── community.js
│   │   ├── points.js
│   │   ├── ai.js
│   │   └── system.js
│   ├── assets/
│   ├── components/
│   ├── router/
│   │   └── index.js
│   ├── store/
│   │   └── admin.js         # 管理员信息与角色
│   ├── layout/
│   │   └── AdminLayout.vue  # 侧边栏 + 顶栏
│   ├── views/
│   │   ├── Login.vue
│   │   ├── Dashboard.vue
│   │   ├── admin/AdminList.vue
│   │   ├── system/SystemConfig.vue
│   │   ├── user/UserList.vue
│   │   ├── item/ItemList.vue
│   │   ├── item/ItemAudit.vue
│   │   ├── order/OrderList.vue
│   │   ├── community/PostList.vue
│   │   ├── community/ReportList.vue
│   │   ├── points/PointsList.vue
│   │   └── ai/AiMonitor.vue
│   ├── App.vue
│   └── main.js
├── .env
├── package.json
└── vite.config.js
```

### 5.3 后端路由模块

在原有后端新增 `app/routers/admin/` 子包：

```
app/routers/admin/
├── __init__.py
├── auth.py           # 管理员登录
├── account.py        # 管理员账号管理（超管）
├── system.py         # 系统配置（超管）
├── user.py           # 用户管理
├── item.py           # 物品管理 + 审核
├── order.py          # 订单管理
├── community.py      # 社区内容 + 举报
├── points.py         # 积分管理
└── ai.py             # AI 监控
```

统一在 `main.py` 中挂载：

```python
from app.routers.admin import auth, account, user, item, order, community, points, ai

app.include_router(auth.router, prefix="/api/admin")
app.include_router(account.router, prefix="/api/admin")
app.include_router(user.router, prefix="/api/admin")
app.include_router(item.router, prefix="/api/admin")
app.include_router(order.router, prefix="/api/admin")
app.include_router(community.router, prefix="/api/admin")
app.include_router(points.router, prefix="/api/admin")
app.include_router(ai.router, prefix="/api/admin")
```

---

## 6. 数据库设计

### 6.1 管理员表 `admin`（已提供）

```sql
CREATE TABLE `admin` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `username` VARCHAR(32) NOT NULL COMMENT '账号',
  `password_hash` VARCHAR(100) NOT NULL COMMENT '加密密码',
  `real_name` VARCHAR(20) DEFAULT NULL COMMENT '姓名',
  `role` TINYINT DEFAULT 1 COMMENT '角色：1=超级管理员 2=运营 3=审核员',
  `status` TINYINT DEFAULT 1 COMMENT '状态：1=启用 0=禁用',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='管理员表';
```

**初始化数据**：
```sql
INSERT INTO admin (username, password_hash, real_name, role, status)
VALUES ('admin', '加密后的密码', '超级管理员', 1, 1);
```

### 6.2 业务表（沿用用户端）

- `sys_user`：社区用户表
- `goods` / `item`：物品表（含审核状态字段）
- `orders`：交换订单表
- `post` / `comment`：社区内容表
- `report`：举报表
- `points_log`：积分流水表
- `ai_log`：AI 调用日志表

> 具体字段以用户端已建表为准，管理端不新增业务表结构，仅复用并操作数据。

---

## 7. 后端接口设计

### 7.1 通用说明

- 基础路径：`/api/admin`
- 所有接口（除登录）需在请求头携带 `Authorization: Bearer <token>`
- 使用依赖 `get_current_admin` 校验 JWT 并返回管理员信息
- 使用依赖 `require_role([1])` / `require_role([1,2])` / `require_role([1,2,3])` 控制权限
- 统一响应格式：`{ "code": 200, "message": "success", "data": ... }`

### 7.2 登录

**POST** `/api/admin/login`

请求体：
```json
{ "username": "admin", "password": "123456" }
```

响应：
```json
{
  "code": 200,
  "message": "登录成功",
  "data": {
    "token": "eyJhbGciOi...",
    "admin_id": 1,
    "username": "admin",
    "real_name": "超级管理员",
    "role": 1
  }
}
```

### 7.3 管理员账号管理（role=1）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/accounts` | 分页查询管理员列表 |
| POST | `/api/admin/accounts` | 新增管理员 |
| PUT | `/api/admin/accounts/{id}` | 修改管理员信息 |
| DELETE | `/api/admin/accounts/{id}` | 删除管理员 |
| POST | `/api/admin/accounts/{id}/reset-password` | 重置密码 |

### 7.4 系统配置（role=1）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/system/config` | 获取配置 |
| PUT | `/api/admin/system/config` | 更新配置 |

### 7.5 用户管理（role=1,2 写，3 只读）

| 方法 | 路径 | 允许角色 |
|------|------|---------|
| GET | `/api/admin/users` | 1,2,3 |
| GET | `/api/admin/users/{id}` | 1,2,3 |
| PUT | `/api/admin/users/{id}/status` | 1,2 |
| DELETE | `/api/admin/users/{id}` | 1,2 |

### 7.6 物品管理（role=1,2 写，3 只读）

| 方法 | 路径 | 允许角色 |
|------|------|---------|
| GET | `/api/admin/items` | 1,2,3 |
| GET | `/api/admin/items/{id}` | 1,2,3 |
| PUT | `/api/admin/items/{id}` | 1,2 |
| DELETE | `/api/admin/items/{id}` | 1,2 |

### 7.7 物品审核（role=1,2,3）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/items/audit/list` | 待审核列表 |
| POST | `/api/admin/items/{id}/audit` | 提交审核结果（通过/拒绝） |

请求体：
```json
{ "approved": true, "reason": "" }
```

### 7.8 订单管理（role=1,2 写，3 只读）

| 方法 | 路径 | 允许角色 |
|------|------|---------|
| GET | `/api/admin/orders` | 1,2,3 |
| GET | `/api/admin/orders/{id}` | 1,2,3 |
| PUT | `/api/admin/orders/{id}/status` | 1,2 |
| DELETE | `/api/admin/orders/{id}` | 1,2 |

### 7.9 社区内容管理（role=1,2 写，3 只读）

| 方法 | 路径 | 允许角色 |
|------|------|---------|
| GET | `/api/admin/posts` | 1,2,3 |
| PUT | `/api/admin/posts/{id}` | 1,2 |
| DELETE | `/api/admin/posts/{id}` | 1,2 |

### 7.10 举报处理（role=1,2,3）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/reports` | 举报列表 |
| POST | `/api/admin/reports/{id}/handle` | 处理举报 |

### 7.11 积分管理（role=1,2 写，3 只读）

| 方法 | 路径 | 允许角色 |
|------|------|---------|
| GET | `/api/admin/points/logs` | 1,2,3 |
| POST | `/api/admin/points/adjust` | 1,2 |
| GET | `/api/admin/points/rules` | 1,2,3 |
| PUT | `/api/admin/points/rules` | 1 |

### 7.12 AI 监控（role=1,2）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/ai/logs` | 调用日志 |
| GET | `/api/admin/ai/stats` | 使用统计 |
| GET | `/api/admin/ai/alerts` | 异常告警 |

### 7.13 数据看板（role=1,2,3）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/dashboard/overview` | 概览数据 |
| GET | `/api/admin/dashboard/trends` | 趋势数据 |

---

## 8. 前端页面设计

### 8.1 整体风格

- 后台管理经典布局：左侧菜单 + 顶部导航 + 内容区
- 使用 Element Plus 组件，风格简洁大方
- 主色调与社区旧物互换主题呼应（森林绿/青绿色 + 暖橙色点缀）
- 顶部显示当前管理员姓名、角色标签、退出登录

### 8.2 页面清单

| 页面 | 路径 | 允许角色 |
|------|------|---------|
| 登录页 | `/login` | 全部 |
| 数据看板 | `/dashboard` | 1,2,3 |
| 管理员账号管理 | `/admin/accounts` | 1 |
| 系统配置 | `/admin/system` | 1 |
| 用户管理 | `/users` | 1,2,3 |
| 物品管理 | `/items` | 1,2,3 |
| 物品审核 | `/items/audit` | 1,2,3 |
| 订单管理 | `/orders` | 1,2,3 |
| 社区内容 | `/community/posts` | 1,2,3 |
| 举报处理 | `/community/reports` | 1,2,3 |
| 积分管理 | `/points` | 1,2,3 |
| AI 监控 | `/ai` | 1,2 |

### 8.3 菜单与权限

- 前端通过 Pinia 存储 `role`，路由 meta 中标记 `roles: [1,2,3]`
- 全局路由守卫：检查 token 是否存在 + 当前路由 roles 是否包含当前角色
- 无权限的路由直接跳转 403 页面或 dashboard
- 侧边栏菜单根据角色动态渲染

### 8.4 通用组件

- 分页表格组件（`PageTable`）
- 搜索工具栏
- 审核弹窗（通过/拒绝 + 理由）
- 富文本编辑器（用于系统公告等）

---

## 9. 环境变量配置

### 9.1 前端 `.env`

```
VITE_API_BASE_URL=http://localhost:8000/api
VITE_APP_TITLE=社区旧物互换管理后台
```

### 9.2 后端 `.env`（新增）

```
# 管理端 JWT 配置
ADMIN_TOKEN_EXPIRE_MINUTES=1440

# AI 监控开关
AI_MONITOR_ENABLED=true
```

---

## 10. 开发计划

| 阶段 | 内容 |
|------|------|
| 第一阶段 | 后端管理员登录接口、JWT 角色区分、权限依赖 |
| 第二阶段 | 后端各业务管理接口（用户、物品、订单、社区、积分、AI） |
| 第三阶段 | 前端项目初始化、登录页、布局、路由守卫、看板 |
| 第四阶段 | 各业务页面开发与联调 |
| 第五阶段 | 测试、优化、部署 |

---

## 11. 验收标准

- 三种角色均可登录，登录后菜单和按钮按权限显示
- 超管可管理管理员账号和系统配置
- 运营可管理业务数据，但不能访问管理员账号和系统配置
- 审核员只能查看数据和执行审核/举报处理，不能删除或修改核心数据
- 后端接口对越权访问返回 403
- 各列表分页、搜索、操作正常
- 界面美观、运行流畅

---

# 社区旧物互换平台——管理端软件开发文档（SDD）

## 1. 总体设计

### 1.1 技术选型

- 前端：Vue 3 + Vite + Element Plus + Axios + Vue Router + Pinia
- 后端：FastAPI + PyMySQL + DBUtils（复用原有后端）
- 认证：JWT（python-jose）
- 权限：基于 `role` 字段的依赖注入

### 1.2 模块划分

- **后端**：`app/routers/admin/` 子包，按业务拆分路由文件
- **前端**：`agent_admin_front` 独立项目，`layout` + `views` + `api` + `store`

---

## 2. 后端详细设计

### 2.1 JWT 与权限依赖

**生成管理员 token**：
```python
def create_admin_token(admin_id: int, username: str, role: int) -> str:
    payload = {
        "admin_id": admin_id,
        "username": username,
        "role": role,
        "exp": datetime.utcnow() + timedelta(minutes=settings.ADMIN_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
```

**`get_current_admin` 依赖**：
```python
def get_current_admin(authorization: str = Header(None)) -> dict:
    # 解析 token，校验 role in [1,2,3]
    # 查询 admin 表确认 status=1
    return {"admin_id": ..., "username": ..., "role": ...}
```

**角色校验依赖工厂**：
```python
def require_role(allowed_roles: list[int]):
    def checker(admin: dict = Depends(get_current_admin)):
        if admin["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="无权限访问")
        return admin
    return checker
```

使用示例：
```python
@router.get("/accounts", dependencies=[Depends(require_role([1]))])
def list_accounts(...): ...
```

### 2.2 登录逻辑

```python
@router.post("/login")
def admin_login(req: AdminLogin):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM admin WHERE username=%s", (req.username,))
            row = cur.fetchone()
    if not row or not verify_password(req.password, row["password_hash"]):
        return ApiResponse.fail("账号或密码错误", 400)
    if row["status"] != 1:
        return ApiResponse.fail("账号已被禁用", 403)
    token = create_admin_token(row["id"], row["username"], row["role"])
    return ApiResponse.ok(data={
        "token": token,
        "admin_id": row["id"],
        "username": row["username"],
        "real_name": row["real_name"],
        "role": row["role"],
    })
```

### 2.3 账号管理（role=1）

- 新增：校验用户名唯一，密码加密后存入
- 修改：允许改姓名、角色、状态，不允许改用户名
- 删除：禁止删除自己（`admin_id == current_admin["admin_id"]` 时拒绝）
- 重置密码：生成新密码或指定新密码，加密后更新

### 2.4 系统配置（role=1）

- 使用 `sys_config` 表存储键值对配置（key、value、description、updated_at）
- 提供读取和更新接口

### 2.5 用户/物品/订单/社区/积分

- 复用用户端已有的业务表
- 提供分页查询、条件筛选、状态修改、删除接口
- 使用 `require_role` 控制写操作权限
- 删除操作前做关联检查（如用户有未完成订单时不允许删除，可选）

### 2.6 物品审核

- 物品表建议有 `status` 字段：0=待审核、1=已上架、2=已拒绝、3=已下架
- 审核接口根据 `approved` 更新状态，拒绝时记录 `reject_reason`
- 审核员、运营、超管均可操作

### 2.7 举报处理

- `report` 表字段建议：`id, reporter_id, target_type, target_id, reason, status, handler_id, handle_time, result`
- 处理接口更新 status 并记录处理人

### 2.8 积分管理

- `points_log` 表记录流水
- 手动调整接口需记录操作人、原因、时间
- 积分规则可存入 `sys_config`

### 2.9 AI 监控

- `ai_log` 表记录调用时间、接口、耗时、状态、错误信息
- 统计接口聚合调用次数、成功率、平均耗时
- 告警接口返回最近异常记录

---

## 3. 前端详细设计

### 3.1 项目初始化

```bash
npm create vite@latest agent_admin_front -- --template vue
cd agent_admin_front
npm install
npm install element-plus axios vue-router pinia
```

### 3.2 `vite.config.js`

```javascript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') }
  },
  server: {
    host: '0.0.0.0',
    port: 5174,          // 与用户端 5173 区分
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true }
    }
  }
})
```

### 3.3 `request.js`

```javascript
import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'

const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api',
  timeout: 15000
})

service.interceptors.request.use(config => {
  const token = localStorage.getItem('admin_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

service.interceptors.response.use(
  res => {
    const data = res.data
    if (data.code !== 200) {
      ElMessage.error(data.message || '请求失败')
      if (data.code === 401) {
        localStorage.removeItem('admin_token')
        router.push('/login')
      }
      return Promise.reject(new Error(data.message))
    }
    return data
  },
  err => {
    const status = err.response?.status
    if (status === 401) {
      localStorage.removeItem('admin_token')
      router.push('/login')
    } else if (status === 403) {
      ElMessage.error('无权限访问')
    } else {
      ElMessage.error(err.message || '网络错误')
    }
    return Promise.reject(err)
  }
)

export default service
```

### 3.4 Pinia Store（admin）

```javascript
import { defineStore } from 'pinia'

export const useAdminStore = defineStore('admin', {
  state: () => ({
    token: localStorage.getItem('admin_token') || '',
    adminInfo: JSON.parse(localStorage.getItem('admin_info') || '{}')
  }),
  getters: {
    role: state => state.adminInfo.role || 0
  },
  actions: {
    setLogin(data) {
      this.token = data.token
      this.adminInfo = data
      localStorage.setItem('admin_token', data.token)
      localStorage.setItem('admin_info', JSON.stringify(data))
    },
    logout() {
      this.token = ''
      this.adminInfo = {}
      localStorage.removeItem('admin_token')
      localStorage.removeItem('admin_info')
    }
  }
})
```

### 3.5 路由守卫

```javascript
router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('admin_token')
  const adminInfo = JSON.parse(localStorage.getItem('admin_info') || '{}')
  if (to.path === '/login') return next()
  if (!token) return next('/login')
  if (to.meta.roles && !to.meta.roles.includes(adminInfo.role)) {
    return next('/403')
  }
  next()
})
```

路由 meta 示例：
```javascript
{ path: '/admin/accounts', component: ..., meta: { roles: [1] } }
{ path: '/users', component: ..., meta: { roles: [1,2,3] } }
{ path: '/ai', component: ..., meta: { roles: [1,2] } }
```

### 3.6 布局组件 `AdminLayout.vue`

- 左侧 `el-menu`，菜单项根据 `role` 动态渲染
- 顶部显示管理员姓名、角色标签、退出按钮
- 内容区 `router-view`

菜单渲染示例：
```javascript
const menus = [
  { path: '/dashboard', title: '数据看板', icon: 'Odometer', roles: [1,2,3] },
  { path: '/admin/accounts', title: '管理员账号', icon: 'UserFilled', roles: [1] },
  { path: '/admin/system', title: '系统配置', icon: 'Setting', roles: [1] },
  { path: '/users', title: '用户管理', icon: 'User', roles: [1,2,3] },
  { path: '/items', title: '物品管理', icon: 'Goods', roles: [1,2,3] },
  { path: '/items/audit', title: '物品审核', icon: 'Checked', roles: [1,2,3] },
  { path: '/orders', title: '订单管理', icon: 'List', roles: [1,2,3] },
  { path: '/community/posts', title: '社区内容', icon: 'ChatDotRound', roles: [1,2,3] },
  { path: '/community/reports', title: '举报处理', icon: 'Warning', roles: [1,2,3] },
  { path: '/points', title: '积分管理', icon: 'Coin', roles: [1,2,3] },
  { path: '/ai', title: 'AI 监控', icon: 'Cpu', roles: [1,2] },
]
```

### 3.7 页面通用模式

- 顶部工具栏：搜索条件 + 操作按钮
- 中间 `el-table` 展示数据
- 底部 `el-pagination` 分页
- 操作按钮根据角色和权限显示

示例（用户管理）：
```vue
<template>
  <div class="page">
    <div class="toolbar">
      <el-input v-model="keyword" placeholder="搜索用户名" clearable @keyup.enter="load(1)" />
      <el-button type="primary" @click="load(1)">搜索</el-button>
    </div>
    <el-table :data="list" v-loading="loading" border stripe>
      <el-table-column prop="user_id" label="ID" width="80" />
      <el-table-column prop="username" label="用户名" min-width="180" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 1 ? 'success' : 'info'">
            {{ row.status === 1 ? '正常' : '禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" v-if="role !== 3">
        <template #default="{ row }">
          <el-button link type="primary" @click="toggleStatus(row)">禁用/启用</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination ... />
  </div>
</template>
```

---

## 4. 数据库脚本

### 4.1 管理员表

```sql
CREATE TABLE `admin` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `username` VARCHAR(32) NOT NULL,
  `password_hash` VARCHAR(100) NOT NULL,
  `real_name` VARCHAR(20) DEFAULT NULL,
  `role` TINYINT DEFAULT 1,
  `status` TINYINT DEFAULT 1,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 4.2 系统配置表（可选）

```sql
CREATE TABLE `sys_config` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `config_key` VARCHAR(64) NOT NULL,
  `config_value` TEXT,
  `description` VARCHAR(255),
  `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_key` (`config_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 4.3 AI 日志表（可选）

```sql
CREATE TABLE `ai_log` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `api_name` VARCHAR(64),
  `request_body` TEXT,
  `response_body` TEXT,
  `status` TINYINT,
  `duration_ms` INT,
  `error_msg` VARCHAR(500),
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 5. 接口示例

### 5.1 管理员登录

- URL：`/api/admin/login`
- Method：POST
- 请求体：`{ "username": "admin", "password": "123456" }`
- 响应：
```json
{
  "code": 200,
  "message": "登录成功",
  "data": {
    "token": "...",
    "admin_id": 1,
    "username": "admin",
    "real_name": "超级管理员",
    "role": 1
  }
}
```

### 5.2 获取管理员列表（role=1）

- URL：`/api/admin/accounts?page=1&size=10`
- Method：GET
- Headers：`Authorization: Bearer <token>`
- 响应：
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 3,
    "list": [
      { "id": 1, "username": "admin", "real_name": "超级管理员", "role": 1, "status": 1, "created_at": "2025-01-01 10:00:00" }
    ]
  }
}
```

### 5.3 物品审核

- URL：`/api/admin/items/{id}/audit`
- Method：POST
- 请求体：`{ "approved": true, "reason": "" }`
- 响应：`{ "code": 200, "message": "审核成功", "data": null }`

---

## 6. 错误码

| code | 含义 |
|------|------|
| 200 | 成功 |
| 400 | 参数错误 |
| 401 | 未登录 / token 失效 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 500 | 服务器错误 |

---

## 7. 开发计划

1. **第一阶段**：后端管理员登录、JWT、角色依赖、账号管理接口
2. **第二阶段**：后端业务接口（用户、物品、订单、社区、积分、AI）
3. **第三阶段**：前端项目初始化、登录、布局、路由守卫、看板
4. **第四阶段**：各业务页面开发与联调
5. **第五阶段**：测试与部署

---

## 8. 验收标准

- 三种角色可登录，菜单与操作按钮按权限展示
- 超管可管理账号与系统配置，运营不可
- 审核员只能只读 + 审核 + 举报处理
- 越权访问接口返回 403
- 列表分页、搜索、审核、删除等功能正常
- 界面美观、响应式良好

---

以上文档已完整覆盖社区旧物互换平台管理端的需求与开发细节，可直接交给 AI 智能体生成代码。开发时请严格遵循接口规范和目录结构，确保前后端联调顺畅。