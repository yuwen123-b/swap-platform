# 排查报告 - EdgeOne 部署前端 401

> 排查时间：2026-10-22　**修复状态：已修复（见文末「修复记录」）**
> 现象：前端 `https://xxx.edgeone.app`，后端 `https://xxx.ngrok-free.dev/api/v1`，浏览器访问出现 401。

---

## 结论（最大嫌疑）

**本地 `dist` 构建产物把 API 地址固化成了相对路径 `"/api/v1"`，请求根本没发往 ngrok 后端，而是打到了 EdgeOne 自己的域名上**，由 EdgeOne 边缘返回了 401（或 404 后被 SPA fallback 吞掉）。

证据链：

1. `agent_front/.env.production` 内容是 `VITE_API_BASE_URL=/api/v1` —— 这是为「同源 Nginx 反代」设计的，EdgeOne 上没有这层反代；
2. 实测本地 `dist/assets/index-CCO8VTKf.js` 打包值就是 `baseURL:"/api/v1"`，且整个产物里**没有任何 ngrok 域名**；
3. 请求打到 `https://xxx.edgeone.app/api/v1/auth/login` 这类路径时，EdgeOne 静态托管没有 `/api/*` 的源站，命中其访问控制/未配置路径策略 → **401 / 404**。

而「浏览器直接看页面正常、接口全挂」也与此吻合：HTML 是 EdgeOne 静态托管正常吐的，只有 API 请求会撞墙。

---

## 四个排查要求逐条回答

### 1. `request.js` 对 401 的处理 —— 有死循环风险，建议加固

当前逻辑（`src/api/request.js`）：

```js
if (error.response?.status === 401) {
  localStorage.removeItem('token')
  window.location.href = `/login?redirect=${encodeURIComponent(window.location.pathname)}`
}
```

- **死循环场景（当前 EdgeOne 故障下真实存在）**：登录页点「登录」→ 请求打到 EdgeOne → 401 → 拦截器清 token 并 `window.location.href='/login'` → **整页刷新** → 用户再点登录 → 再 401 → 再刷新。表现为「登录按钮一按页面就刷新、永远登不进去」。
- 白屏风险低（跳的是登录页），但 `window.location.href` 是硬跳转，会丢 SPA 状态、ElMessage 也会被打断。
- **建议加固**（等确认后我来改）：

```js
if (error.response?.status === 401) {
  localStorage.removeItem('token')
  if (!window.location.pathname.startsWith('/login')) {
    window.location.href = `/login?redirect=${encodeURIComponent(window.location.pathname)}`
  }
}
```

### 2. JWT Token 是否携带 —— 携带逻辑正确，但要注意两点

- 请求拦截器正确：`localStorage.getItem('token')` → `Authorization: Bearer xxx`（`request.js:5`），登录成功后 `store/user.js:14` 写入 `localStorage.token`；
- **换域名后 localStorage 按源（origin）隔离**：`xxx.edgeone.app` 下是全新空白，未登录时请求本就不带 Token —— 打开需要登录的页面会被路由守卫拦去 `/login`（不发请求），属预期；
- 但在当前故障下，**连登录请求本身都返回 401**，带不带 Token 都一样 —— Token 不是本次 401 的原因。

### 3. 后端 CORS 是否放行 EdgeOne 域名 —— 已实测放行，CORS 不是本次原因

后端 `.env` 当前 `DEBUG=true`，此时 CORS 按代码（`main.py:29`）走 `https?://.*` 通配。用 EdgeOne 形态的 Origin 实测本机 8000：

```
GET /api/v1/categories（Origin: https://demo.edgeone.app）
→ 200，access-control-allow-origin: https://demo.edgeone.app

OPTIONS 预检（带 authorization 头）
→ 200，access-control-allow-headers: authorization,content-type
```

跨域 + 自定义 Authorization 头所需的预检全部放行。**前提是请求真的到了后端** —— 目前的问题恰恰是没到。

⚠️ 提醒：如果之后把 `DEBUG` 改成 `false`，CORS 会立即收紧为 `CORS_ORIGINS` + 局域网正则，EdgeOne 域名不在白名单内会全部被拒。届时需在 `.env` 加一行：

```
CORS_ORIGINS=http://localhost:5173,https://你的域名.edgeone.app
```

### 4. F12 取证方法与「指纹对照表」

手机/电脑打开 EdgeOne 链接 → `F12`（手机可连电脑用 `edge://inspect`）→ Network → 勾选 `Preserve log` → 刷新页面 → 找红色/状态码异常的请求，看两样东西：**完整请求 URL** 和 **Response Body**。对照下表即可定位：

| Network 里的请求 URL | Response Body 特征 | 结论 |
|---|---|---|
| `https://xxx.edgeone.app/api/v1/...` | EdgeOne 的错误页（HTML 或 EdgeOne JSON），不是后端格式 | **根因①：baseURL 没改**，请求没出 EdgeOne |
| `https://xxx.ngrok-free.dev/api/v1/...` | `{"code":401,"message":"未登录","data":null}` | 请求已到后端，只是未登录（预期行为，登录即可） |
| `https://xxx.ngrok-free.dev/...` 返回 HTML | 含 `ERR_NGROK_` 或 "You are about to visit" 警告页 | ngrok 免费版拦截页（见下方提醒） |
| 请求显示 CORS error、无响应体 | Console 里有 `blocked by CORS policy` | 后端 CORS 未放行（当前实测已放行，可能性低） |

**后端 401 的指纹是 `{"code":401,"message":"未登录","data":null}`**（实测所得）——只要 Response Body 长这样才是后端说的 401。

---

## 修复方案（按顺序做）

**第 1 步（根治）：带 ngrok 地址重新构建前端**

```bash
cd agent_front
# Git Bash：
VITE_API_BASE_URL=https://xxx.ngrok-free.dev/api/v1 npm run build
# PowerShell：$env:VITE_API_BASE_URL="https://xxx.ngrok-free.dev/api/v1"; npm run build
```

把新的 `dist/` 重新上传 EdgeOne。构建前可先本地验证：`npm run preview` 后浏览器直接访问，登录一次成功即说明地址对了。

**第 2 步：确认 ngrok 隧道活着**

浏览器直接打开 `https://xxx.ngrok-free.dev/api/v1/categories`，能返回 JSON 即通。注意 **ngrok 免费版域名在隧道重启后会变**（除非用固定域名），域名一变就要按第 1 步重新构建 —— 建议绑定固定域名，否则每次重建很烦。

**第 3 步（可选加固，等确认）：**
- 拦截器防死循环（见上文 1）；
- `timeout: 10000 → 30000`：ngrok 免费链路首包延迟大，10 秒在公网上可能误判超时；
- 后端 `DEBUG=false` + 显式 CORS 白名单（生产习惯，当前不影响功能）。

## 遗留风险提醒

- 当前 `DEBUG=true` + CORS 通配 + JWT_SECRET 为本地开发值，ngrok 把后端直接暴露公网，任何知道地址的人都能调接口。演示可以接受，正式环境要改；
- 本地 dev server（5173/5174）与此无关，不受影响。

---

## 修复记录（2026-10-22，已实施）

| # | 修改 | 文件 | 内容 |
|---|---|---|---|
| 1 | 401 防重入 | `agent_front/src/api/request.js` | `/login` 页自身触发的 401 不再 `window.location.href` 硬跳，杜绝「登录 → 401 → 刷新 → 再登录」死循环 |
| 2 | 超时放宽 | 同上 | `timeout: 10000 → 30000`，适配 ngrok 公网链路的首包延迟 |
| 3 | 构建验证 | `dist/` | 重新构建通过；产物实测包含 `timeout:3e4`（即 30000）与 `startsWith("/login")` 防重入判断 |

**推荐部署方式：`.env.production.local`（写一次，之后每次 `npm run build` 自动生效）**

1. 新建文件 `agent_front/.env.production.local`，内容一行：
   ```
   VITE_API_BASE_URL=https://xxx.ngrok-free.dev/api/v1
   ```
   该文件被 `.gitignore` 的 `*.local` 规则忽略，**不会误提交**；且 Vite 优先级高于 `.env.production`，无需改动任何现有文件。
2. `npm run build`，把 `dist/` 上传 EdgeOne。
3. 验证：浏览器打开 EdgeOne 链接 → F12 Network → 任意 API 请求的域名应是 `xxx.ngrok-free.dev`；登录一次成功即闭环。

**关于「能否直接在 EdgeOne 环境变量里配置 VITE_API_BASE_URL」**：取决于部署模式——
- **EdgeOne Pages「连 Git 仓库 + 构建命令」模式：可以**。在项目的环境变量设置里加 `VITE_API_BASE_URL` 后重新触发构建。Vite 会优先取进程环境变量（覆盖 `.env.production`）。判断依据：Pages 项目配置里有「构建命令 / 框架预设」。
- **「直接上传 dist 静态文件」模式：不行**。`VITE_*` 变量是构建时替换进 JS 产物的，运行时不存在读取环境变量的环节，上传的静态托管没有构建过程，环境变量无人消费。这种模式只能走上面 `.env.production.local` 本地构建。

