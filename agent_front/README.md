# 社区旧物互换智能体平台

## 后端

```powershell
cd agent_back
Copy-Item .env.example .env
# 填写 MySQL swap 数据库密码，并执行 sql/ 下脚本
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 前端

```powershell
cd agent_front
npm install
npm run dev
```

前端默认访问 `http://localhost:5173`，后端默认访问 `http://localhost:8000`。开发环境验证码会打印在后端控制台并通过响应返回 `debug_code`。
