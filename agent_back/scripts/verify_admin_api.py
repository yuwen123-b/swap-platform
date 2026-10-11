"""管理端接口层验证脚本（需后端已启动且种子数据已导入）。"""
import json
import urllib.request
import urllib.error

BASE = "http://localhost:8000/api/admin"
PASS = []
FAIL = []


def req(method, path, token=None, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + (f" | {extra}" if extra else ""))


def login(username, password):
    s, b = req("POST", "/login", body={"username": username, "password": password})
    return s, b


# 1. 三角色登录
s1, b1 = login("admin", "admin123")
s2, b2 = login("operator", "123456")
s3, b3 = login("auditor", "123456")
check("admin 登录", s1 == 200 and b1.get("code") == 200 and b1["data"].get("token"), f"status={s1} body={b1}")
check("operator 登录", s2 == 200 and b2.get("code") == 200, f"status={s2}")
check("auditor 登录", s3 == 200 and b3.get("code") == 200, f"status={s3}")
t_admin = b1["data"]["token"]
t_op = b2["data"]["token"]
t_au = b3["data"]["token"]
check("admin role=1", b1["data"]["role"] == 1)
check("operator role=2", b2["data"]["role"] == 2)
check("auditor role=3", b3["data"]["role"] == 3)
admin_self_id = b1["data"]["admin_id"]

# 错误密码
s, b = login("admin", "wrong")
check("错误密码拒绝", s in (400, 401) and b.get("code") != 200, f"status={s} body={b}")

# 2. 越权 403
s, b = req("DELETE", "/users/1", token=t_au)
check("auditor DELETE /users/1 = 403", s == 403, f"status={s} body={b}")
s, b = req("GET", "/accounts", token=t_op)
check("operator GET /accounts = 403", s == 403, f"status={s} body={b}")
s, b = req("GET", "/accounts", token=t_admin)
check("admin GET /accounts = 200", s == 200 and b.get("code") == 200, f"status={s}")

# 未登录
s, b = req("GET", "/users")
check("无 token 401", s == 401, f"status={s}")

# 3. 分页列表
s, b = req("GET", "/users?page=1&size=5", token=t_admin)
d = b.get("data") or {}
check("用户分页", s == 200 and "list" in d and "total" in d and len(d["list"]) <= 5, f"total={d.get('total')}")
s, b = req("GET", "/items?page=1&size=5", token=t_au)
d = b.get("data") or {}
check("物品分页(审核员可读)", s == 200 and "list" in d, f"total={d.get('total')}")
s, b = req("GET", "/orders?page=1&size=5", token=t_op)
check("订单分页", s == 200 and "list" in (b.get("data") or {}))

# 4. 审核流
s, b = req("GET", "/items/audit/list?page=1&size=10", token=t_au)
audit_list = (b.get("data") or {}).get("list") or []
check("待审核列表", s == 200 and len(audit_list) >= 1, f"count={len(audit_list)}")
if audit_list:
    iid = audit_list[0]["id"]
    s, b = req("POST", f"/items/{iid}/audit", token=t_au, body={"approved": True})
    check("审核通过", s == 200 and b.get("code") == 200, f"status={s} body={b}")
    s, b = req("GET", f"/items/{iid}", token=t_au)
    check("通过后 status=1", (b.get("data") or {}).get("status") == 1, f"body={b.get('data')}")
if len(audit_list) >= 2:
    iid2 = audit_list[1]["id"]
    s, b = req("POST", f"/items/{iid2}/audit", token=t_au, body={"approved": False, "reason": "图片不合规"})
    check("审核拒绝", s == 200, f"status={s} body={b}")
    s, b = req("GET", f"/items/{iid2}", token=t_au)
    dd = b.get("data") or {}
    check("拒绝后 status=2 且理由落库", dd.get("status") == 2 and dd.get("reject_reason") == "图片不合规", f"data={dd}")

# 5. 举报处理
s, b = req("GET", "/reports?status=0&page=1&size=10", token=t_op)
reps = (b.get("data") or {}).get("list") or []
check("待处理举报列表", s == 200 and len(reps) >= 1, f"count={len(reps)}")
if reps:
    rid = reps[0]["id"]
    s, b = req("POST", f"/reports/{rid}/handle", token=t_op, body={"action": "resolve", "result": "已处理完毕"})
    check("举报处理 resolve", s == 200, f"status={s} body={b}")
    if len(reps) >= 2:
        rid2 = reps[1]["id"]
        s, b = req("POST", f"/reports/{rid2}/handle", token=t_au, body={"action": "dismiss", "result": "证据不足"})
        check("举报驳回 dismiss(审核员)", s == 200, f"status={s} body={b}")

# 6. 积分调整一致性
s, b = req("GET", "/users?page=1&size=1", token=t_admin)
uid = b["data"]["list"][0]["id"]
s, b = req("GET", f"/users/{uid}", token=t_admin)
before = (b.get("data") or {}).get("points")
s, b = req("POST", "/points/adjust", token=t_op, body={"user_id": uid, "points": 30, "reason": "验证脚本调整"})
check("积分调整接口", s == 200, f"status={s} body={b}")
s, b = req("GET", f"/users/{uid}", token=t_admin)
after = (b.get("data") or {}).get("points")
check("user.points 增加 30", before is not None and after == before + 30, f"before={before} after={after}")
s, b = req("GET", "/points/logs?page=1&size=5", token=t_admin)
logs = (b.get("data") or {}).get("list") or []
check("积分流水含 source=4 记录", any(l.get("source") == 4 and l.get("points") == 30 and l.get("user_id") == uid for l in logs), f"logs={logs[:2]}")

# 7. 看板
s, b = req("GET", "/dashboard/overview", token=t_au)
d = b.get("data") or {}
check("看板 overview", s == 200 and "user_total" in d and "item_total" in d and "order_total" in d, f"data={d}")
s, b = req("GET", "/dashboard/trends", token=t_op)
d = b.get("data") or {}
items7 = d.get("item_trend") or []
orders7 = d.get("order_trend") or []
days = d.get("days") or []
check("看板 trends 7 天数组", s == 200 and len(days) == 7 and len(items7) == 7 and len(orders7) == 7, f"days={len(days)} items={len(items7)} orders={len(orders7)}")

# 8. AI 监控
s, b = req("GET", "/ai/stats", token=t_op)
d = b.get("data") or {}
check("AI stats", s == 200 and "total" in d and "success_rate" in d, f"data={d}")
s, b = req("GET", "/ai/logs?page=1&size=5", token=t_admin)
check("AI logs 分页", s == 200 and "list" in (b.get("data") or {}))
s, b = req("GET", "/ai/logs?page=1&size=5", token=t_au)
check("auditor AI logs = 403", s == 403, f"status={s}")

# 9. 系统配置
s, b = req("GET", "/system/config", token=t_admin)
d = b.get("data") or {}
check("系统配置读取", s == 200 and "platform_name" in d, f"keys={list(d)[:5]}")
s, b = req("PUT", "/system/config", token=t_admin, body={"platform_name": "社区旧物互换平台"})
check("系统配置更新", s == 200, f"status={s} body={b}")
s, b = req("PUT", "/system/config", token=t_op, body={"platform_name": "x"})
check("operator 改配置 = 403", s == 403, f"status={s}")

# 10. 账号管理
s, b = req("POST", "/accounts", token=t_admin, body={"username": "temp_auditor2", "password": "abc12345", "real_name": "临时审核", "role": 3})
check("新增管理员", s == 200, f"status={s} body={b}")
new_id = (b.get("data") or {}).get("id")
if new_id:
    s, b = req("POST", f"/accounts/{new_id}/reset-password", token=t_admin, body={"new_password": "newpass123"})
    check("重置密码", s == 200, f"status={s}")
    s, b = login("temp_auditor2", "newpass123")
    check("新密码可登录", s == 200 and b.get("code") == 200, f"status={s}")
    s, b = req("DELETE", f"/accounts/{new_id}", token=t_admin)
    check("删除管理员", s == 200, f"status={s}")
s, b = req("DELETE", f"/accounts/{admin_self_id}", token=t_admin)
check("禁止删除自己", s in (400, 403), f"status={s} body={b}")

print()
print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败项:", FAIL)
    raise SystemExit(1)
