# API 文档：商家端闭环

- 版本：2026-10-15
- 范围：**仅后端**（前端未实现）
- 闭环：用户赚积分 → 兑换商家服务 → 商家核销 → 平台结算 → 商家获得客流
- 接口总数：**20 个**（商家端 9 + 用户端 4 + 平台管理端 7；任务书写"共 19"是其清单自身的算术偏差）

---

## 0. 通用约定

### 0.1 前缀与挂载

| 分组 | 挂载前缀 | 说明 |
|---|---|---|
| 商家端 + 用户端 | `/api/v1/merchant`（同时挂 `/api/merchant`） | 与 `_NEW_ROUTERS` 里其它增量模块同口径双挂载 |
| 平台管理端 | `/api/admin/merchant` | 与其它 `admin_*` 一致，**不**额外挂 `/api/v1/admin` |

### 0.2 响应外壳（两套，刻意不混用）

**用户侧 / 商家侧** `success()`：

```json
{ "code": 0, "message": "success", "data": { } }
```

**平台管理端** `ok()`：

```json
{ "code": 200, "message": "success", "data": { } }
```

**错误**（两侧一致，HTTP 状态码 = `code`）：

```json
{ "code": 400, "message": "积分不足：本次兑换需要 500 积分，你当前有 100 积分", "data": null }
```

### 0.3 鉴权

| 分组 | 请求头 | 说明 |
|---|---|---|
| 商家端 | `Authorization: Bearer <用户 token>` | 商家用**用户账号**登录；身份靠 `merchant.user_id` 反查，`user` 表没有 role 字段 |
| 用户端 | 同上（`/shops`、`/shops/{id}/products` 免登录） | |
| 管理端 | `Authorization: Bearer <管理员 token>` | 角色 1=超管 2=运营 3=只读 |

`user_id` **一律从 JWT 解析**，接口不接受前端传入。

### 0.4 状态枚举

| 字段 | 取值 |
|---|---|
| `merchant.status` | 0 待审核 / 1 已通过 / 2 已拒绝 / 3 已停业 |
| `merchant_product.status` | 0 已下架 / 1 上架中 |
| `redemption_order.status` | 1 待核销 / 2 已核销 / 3 已过期 / 4 已取消 |
| `merchant_settlement.status` | 0 待结算 / 1 已结算 |
| `points_log.source` | 1 发布物品 / 2 完成交换 / 3 收到好评 / 4 管理员调整 / **5 兑换消耗** / 6 免费送出奖励 / **7 兑换过期退还** |

### 0.5 分页

请求：`page`（默认 1）、`size`（默认 10，最大 50；管理端最大 100）。越界**夹紧**不报错。

响应：`{ "total": 42, "page": 1, "size": 10, "list": [ ... ] }`

### 0.6 图片字段

`logo_url` / `image_url` 在库中**只存相对路径**，接口返回时现场补 HMAC 签名：
`/api/v1/static/merchant/xxx.png?exp=1760000000&sig=abcd...`（有效期 1 小时）。
外链（`http(s)://` 开头）原样返回。

### 0.7 总开关

`.env` 的 `MERCHANT_ENABLED=false` 时，**商家端与用户端全部接口返回 403**（管理端不受影响，仍可审核与结算）。

---

## 1. 商家端接口（9 个）

### 1.1 `POST /api/v1/merchant/apply` 入驻申请

请求体：

```json
{ "name": "社区打印店", "category": "打印", "contact": "13800000001",
  "address": "小区北门 1 号楼底商", "description": "打印复印装订" }
```

| 字段 | 必填 | 长度 |
|---|---|---|
| `name` | ✅ | ≤100 |
| `category` / `contact` / `address` / `description` | ❌ | 50 / 100 / 200 / 2000 |

**可选字段只在请求里显式出现时才写入**：重提时未传的字段保留原值，不会被清空；需要清空时显式传空串。

响应（首次）：

```json
{ "code": 0, "message": "入驻申请已提交，请等待审核",
  "data": { "id": 6, "user_id": 7, "name": "社区打印店", "category": "打印",
            "status": 0, "status_label": "待审核", "commission_rate": 5.0,
            "audit_reason": null, "created_at": "2026-10-15T19:30:00" } }
```

失败：

| 场景 | 状态码 | message |
|---|---|---|
| 已通过审核再次申请 | 400 | 您已入驻，无需重复申请 |
| 店铺已停业 | 400 | 店铺已停业，暂不支持重新申请 |
| 店名为空 / 超长 | 400 | 店铺名不能为空 / 不能超过 100 个字符 |

- 首次 → INSERT，`status=0`
- 待审核 / 已拒绝 → UPDATE 原行重提，`status` 回到 0、清空 `audit_reason`（**不新增行**，`uk_merchant_user` 保证一账号一店）

---

### 1.2 `GET /api/v1/merchant/info` 我的店铺

未入驻返回 `merchant: null`（**不是 404**，前端据此渲染入驻表单）：

```json
{ "code": 0, "message": "success",
  "data": { "merchant": null, "enabled": true } }
```

已入驻：

```json
{ "code": 0, "message": "success",
  "data": { "merchant": { "id": 6, "name": "社区打印店", "status": 1,
            "status_label": "已通过", "commission_rate": 5.0,
            "audit_reason": null, "logo_url": "/api/v1/static/merchant/x.png?exp=..&sig=.." },
            "enabled": true } }
```

`audit_reason` 是审核意见（被拒原因），商家可见。

---

### 1.3 `GET /api/v1/merchant/products` 我的商品列表

无 query 参数（商家自己的商品全量，含已下架、按 id 倒序）。

```json
{ "code": 0, "message": "success",
  "data": { "merchant_id": 6, "merchant_status": 1,
            "list": [ { "id": 11, "merchant_id": 6, "title": "打印券10张",
                        "description": "A4 黑白 10 张", "image_url": null,
                        "points_cost": 60, "stock": 2, "sold_count": 0,
                        "status": 1, "status_label": "上架中",
                        "created_at": "2026-10-15T19:30:00" } ] } }
```

未入驻：404 `您还不是商家，请先提交入驻申请`

---

### 1.4 `POST /api/v1/merchant/products` 上架商品

请求体：

```json
{ "title": "打印券10张", "description": "A4 黑白 10 张",
  "image_url": "merchant/a.png", "points_cost": 50, "stock": 100 }
```

| 字段 | 必填 | 约束 |
|---|---|---|
| `title` | ✅ | ≤100 |
| `description` | ❌ | ≤2000 |
| `image_url` | ❌ | ≤500 |
| `points_cost` | ✅ | 0 ~ 1,000,000（0 = 免费券） |
| `stock` | ❌ | 0 ~ 1,000,000，默认 0 |

响应 `data` 为商品对象（同 1.3 元素结构），`message` = `商品已上架`。

失败：店铺未通过审核 → 403 `店铺尚未通过审核，暂不能进行该操作`

---

### 1.5 `PUT /api/v1/merchant/products/{product_id}` 修改商品

请求体（**全部可选，只更新传入的字段**）：

```json
{ "points_cost": 80 }
```

`{ "title", "description", "image_url", "points_cost", "stock" }` 任选。

响应 `data` 为更新后的商品对象，`message` = `商品已更新`。

失败：

| 场景 | 状态码 | message |
|---|---|---|
| 无任何字段可改 | 400 | 没有需要修改的内容 |
| 商品不存在 / 不属于本店 | 404 | 商品不存在或不属于本店 |

> 归属校验写进 SQL 的 `WHERE id=%s AND merchant_id=%s`，改不到别人的商品。

---

### 1.6 `PUT /api/v1/merchant/products/{product_id}/offline` 下架商品

无请求体。

```json
{ "code": 0, "message": "商品已下架", "data": { "product_id": 11, "status": 0 } }
```

软下架（`status=0`，不删行），已有兑换记录不受影响。不属于本店 → 404。

---

### 1.7 `GET /api/v1/merchant/redemptions` 核销订单列表

Query：`status`（可选，1/2/3/4）、`page`、`size`。

```json
{ "code": 0, "message": "success",
  "data": { "total": 2, "page": 1, "size": 10,
            "list": [ { "id": 3, "order_no": "RD202610151930000123", "status": 1,
                        "status_label": "待核销", "code": "482913", "points_cost": 60,
                        "product_id": 11, "product_title": "E2E打印券10张",
                        "merchant_id": 6, "merchant_name": "E2E社区打印店",
                        "user_id": 8, "user_nickname": "E2E用户",
                        "expires_at": "2026-11-14T19:30:00", "redeemed_at": null,
                        "created_at": "2026-10-15T19:30:00" } ] } }
```

---

### 1.8 `POST /api/v1/merchant/redemptions/verify` 核销

请求体：

```json
{ "code": "482913" }
```

响应：

```json
{ "code": 0, "message": "核销成功",
  "data": { "success": true, "order_id": 3, "order_no": "RD202610151930000123",
            "product_title": "E2E打印券10张", "points_cost": 60,
            "user_nickname": "E2E用户", "redeemed_at": "2026-10-15T19:35:00" } }
```

失败：

| 场景 | 状态码 | message |
|---|---|---|
| 码不存在 | 404 | 核销码不存在，请核对后重新输入 |
| 码属于别家店 | 403 | 该核销码不属于本店 |
| 已核销 | 400 | 该核销码已使用，请勿重复核销 |
| 已过期（含后台尚未扫到的过期单） | 400 | 该核销码已过期 |
| 已取消 | 400 | 该兑换单已取消 |
| 店铺未通过审核 | 403 | 店铺尚未通过审核，暂不能进行该操作 |

**并发安全**：条件更新 `WHERE id=%s AND merchant_id=%s AND status=1 AND expires_at>NOW()` + `rowcount` 判定，
商家连点两次只有第一次生效。核销**不退积分、不动库存**。

---

### 1.9 `GET /api/v1/merchant/dashboard` 数据看板

```json
{ "code": 0, "message": "success",
  "data": {
    "today_redemptions": 2,
    "total_redemptions": 2,
    "unique_users": 1,
    "popular_products": [ { "title": "E2E打印券10张", "sold_count": 2 } ],
    "trend": [ { "date": "2026-10-09", "count": 0 }, { "date": "2026-10-10", "count": 0 },
               { "date": "2026-10-11", "count": 0 }, { "date": "2026-10-12", "count": 0 },
               { "date": "2026-10-13", "count": 0 }, { "date": "2026-10-14", "count": 0 },
               { "date": "2026-10-15", "count": 2 } ] } }
```

- 实时聚合 `redemption_order`，不读 `merchant_stats` 缓存表（该表建了但本期不写不读）
- `trend` 恒为 **7 个连续日期点**，无核销的日期补 0（前端画折线不会断）

---

## 2. 用户端接口（4 个）

### 2.1 `GET /api/v1/merchant/shops` 商家列表

**免登录可访问**。Query：`category`（可选）、`page`、`size`。只返回 `status=1` 的商家。

> 路径用 `/shops` 而非 `/list`：避免与 `/shops/{id}/products` 这类通配段在 FastAPI 正则匹配下互相抢占。

```json
{ "code": 0, "message": "success",
  "data": { "total": 5, "page": 1, "size": 10,
            "list": [ { "id": 1, "name": "社区打印店", "category": "打印",
                        "address": "小区北门 1 号楼底商", "contact": "13800000001",
                        "description": "打印、复印、扫描、装订……", "logo_url": null,
                        "product_count": 2 } ] } }
```

---

### 2.2 `GET /api/v1/merchant/shops/{merchant_id}/products` 店铺商品

**免登录可访问**。只返回该店 `status=1` 的商品。店铺不存在或未通过审核 → 404 `商家不存在或暂未开放`。

```json
{ "code": 0, "message": "success",
  "data": { "merchant": { "id": 1, "name": "社区打印店", "category": "打印",
                          "address": "小区北门 1 号楼底商", "contact": "13800000001",
                          "description": "……", "logo_url": null, "product_count": 2 },
            "list": [ { "id": 1, "merchant_id": 1, "title": "打印券10张",
                        "description": "A4 黑白单面打印 10 张，不限时段使用。",
                        "image_url": null, "points_cost": 50, "stock": 100,
                        "sold_count": 0, "status": 1, "status_label": "上架中",
                        "created_at": "2026-10-15T19:20:00" } ] } }
```

---

### 2.3 `POST /api/v1/merchant/redeem` 兑换

请求体：

```json
{ "product_id": 1 }
```

响应：

```json
{ "code": 0, "message": "兑换成功，请凭核销码到店使用",
  "data": { "order_id": 5, "order_no": "RD202610151940000456", "code": "482913",
            "points_cost": 50, "product_title": "打印券10张",
            "merchant_name": "社区打印店",
            "expires_at": "2026-11-14T19:40:00", "points_balance": 2950 } }
```

失败：

| 场景 | 状态码 | message |
|---|---|---|
| 商品不存在 | 404 | 兑换商品不存在 |
| 店铺未通过审核 | 400 | 该店铺暂未开放兑换 |
| 商品已下架 | 400 | 该商品已下架 |
| 兑换自己店铺的商品 | 400 | 不能兑换自己店铺的商品 |
| 积分不足 | 400 | 积分不足：本次兑换需要 500 积分，你当前有 100 积分 |
| 库存不足 | 400 | 库存不足，该商品刚刚被兑完 |

**一次事务完成**：校验余额（`SELECT points ... FOR UPDATE` 行锁）→ 条件扣库存（`WHERE stock>0`，防超卖）
→ INSERT 兑换单 → `award_points(-points_cost, source=5, related_id=订单id)`。
任一环节失败整体回滚，不会出现「积分扣了却没有兑换单」。
`points_cost=0` 的免费券跳过扣分与流水。

---

### 2.4 `GET /api/v1/merchant/my-redemptions` 我的兑换记录

Query：`status`（可选）、`page`、`size`。按 id 倒序。

```json
{ "code": 0, "message": "success",
  "data": { "total": 2, "page": 1, "size": 10,
            "list": [ { "id": 3, "order_no": "RD202610151930000123", "status": 1,
                        "status_label": "待核销", "code": "482913", "points_cost": 60,
                        "product_id": 11, "product_title": "E2E打印券10张",
                        "merchant_id": 6, "merchant_name": "E2E社区打印店",
                        "user_id": 8, "user_nickname": "E2E用户",
                        "expires_at": "2026-11-14T19:30:00", "redeemed_at": null,
                        "created_at": "2026-10-15T19:30:00" } ] } }
```

> 过期退款**不在本接口做**（GET 不产生写副作用），由后台定时任务统一处理，见第 4 节。

---

## 3. 平台管理端接口（7 个）

读接口需 role ∈ {1,2,3}，写接口需 role ∈ {1,2}。无权限 → 403 `无权限访问`。

### 3.1 `GET /api/admin/merchant/list` 商家列表

Query：`status`（0/1/2/3）、`keyword`（匹配店名 / 联系方式 / 地址）、`page`、`size`。

```json
{ "code": 200, "message": "success",
  "data": { "total": 5, "page": 1, "size": 10,
            "list": [ { "id": 1, "user_id": null, "name": "社区打印店", "category": "打印",
                        "contact": "13800000001", "address": "小区北门 1 号楼底商",
                        "description": "……", "logo_url": null, "status": 1,
                        "status_label": "已通过", "commission_rate": 5.0,
                        "audit_reason": null, "created_at": "2026-10-15T19:20:00",
                        "product_count": 2, "redemption_count": 0 } ] } }
```

---

### 3.2 `PUT /api/admin/merchant/{merchant_id}/audit` 审核商家

请求体：

```json
{ "approved": false, "reason": "资质材料不全" }
```

```json
{ "code": 200, "message": "已拒绝该入驻申请",
  "data": { "merchant_id": 6, "status": 2, "status_label": "已拒绝",
            "audit_reason": "资质材料不全" } }
```

| 场景 | 状态码 | message |
|---|---|---|
| 拒绝但未填原因 | 400 | 拒绝入驻时必须填写原因 |
| 原因超长（>255） | 400 | 审核原因不能超过 255 个字符 |
| 商家不存在 | 404 | 商家不存在 |

> **与任务书的差异**：任务书把 `reason` 标为可选，这里收紧为「**拒绝时必填**」——
> 被拒却不知原因对商家是死路。原因写入 `merchant.audit_reason`，商家在 `GET /merchant/info` 可见。
> 通过时 `reason` 可留空。

---

### 3.3 `GET /api/admin/merchant/orders` 全部兑换订单

Query：`status`、`merchant_id`、`keyword`（匹配单号 / 核销码）、`page`、`size`。

```json
{ "code": 200, "message": "success",
  "data": { "total": 2, "page": 1, "size": 10,
            "list": [ { "id": 3, "order_no": "RD202610151930000123", "status": 1,
                        "status_label": "待核销", "code": "482913", "points_cost": 60,
                        "product_id": 11, "product_title": "E2E打印券10张",
                        "merchant_id": 6, "merchant_name": "E2E社区打印店",
                        "user_id": 8, "user_nickname": "E2E用户",
                        "expires_at": "2026-11-14T19:30:00", "redeemed_at": null,
                        "created_at": "2026-10-15T19:30:00" } ] } }
```

---

### 3.4 `GET /api/admin/merchant/settlements` 结算记录

Query：`merchant_id`、`period`（`YYYY-MM`）、`status`（0/1）、`page`、`size`。

```json
{ "code": 200, "message": "success",
  "data": { "total": 1, "page": 1, "size": 10,
            "list": [ { "id": 1, "merchant_id": 6, "merchant_name": "E2E社区打印店",
                        "period": "2026-10", "redemption_count": 2, "points_total": 120,
                        "commission_amount": 0.06, "status": 1, "status_label": "已结算",
                        "settled_at": "2026-10-15T19:40:00",
                        "created_at": "2026-10-15T19:40:00" } ] } }
```

---

### 3.5 `POST /api/admin/merchant/settle` 手动触发结算

请求体（可省略）：`{ "merchant_id": 6, "period": "2026-10" }`

- `merchant_id` 为空 → 结算**全部已通过审核**的商家
- `period` 缺省为当月

响应：

```json
{ "code": 200, "message": "结算完成，共 1 家商家",
  "data": { "period": "2026-10", "count": 1, "commission_total": 0.06,
            "list": [ { "merchant_id": 6, "merchant_name": "E2E社区打印店",
                        "period": "2026-10", "redemption_count": 2, "points_total": 120,
                        "commission_amount": 0.06, "status": 1, "status_label": "已结算",
                        "settled_at": "2026-10-15T19:40:00", "already_settled": false } ] } }
```

**计算公式**：

```
commission_amount = points_total × MERCHANT_POINTS_TO_YUAN × (commission_rate / 100)
例：120 积分 × 0.01 元 × 5% = 0.06 元
```

- `points_total` = 该周期内 `status=2（已核销）` 且 `redeemed_at` 落在周期内的兑换单 `points_cost` 之和
- `commission_rate` 取 `merchant` 表该行的值（`.env` 的 `MERCHANT_COMMISSION_RATE` 只是入驻时的初始值）
- **幂等**：已结算的同一 `(merchant_id, period)` 直接返回原记录（`already_settled: true`），不重算不重复写行
- 周期格式非法 → 400 `结算周期格式不正确，应为 YYYY-MM（如 2026-10）`

---

### 3.6 `POST /api/admin/merchant/settle/{merchant_id}` 结算指定商家

请求体（可省略）：`{ "period": "2026-10" }`。响应 `data` 为**单个**结算对象（同 3.5 的 `list` 元素）。

---

### 3.7 `GET /api/admin/merchant/stats` 平台总览

```json
{ "code": 200, "message": "success",
  "data": {
    "merchants": { "total": 5, "pending": 0, "approved": 5, "rejected": 0, "closed": 0 },
    "redemptions": { "total": 3, "pending": 0, "redeemed": 2, "expired": 1, "cancelled": 0 },
    "points_consumed": 120,
    "commission_total": 0.06,
    "top_merchants": [ { "merchant_id": 6, "name": "E2E社区打印店", "redemption_count": 2 } ],
    "trend": [ { "date": "2026-10-09", "count": 0 }, "…共 7 个点" ]
  } }
```

- `points_consumed`：已核销单消耗积分合计
- `commission_total`：已结算佣金合计（元）

---

## 4. 后台定时任务：兑换单过期退还

- 实现：`asyncio` 后台循环（**未引入任何新依赖**），启动时注册、关闭时取消
- 频率：每 **3600 秒**（1 小时）一次；由 `REDEMPTION_EXPIRE_INTERVAL_SECONDS` 配置
- 逻辑：`status=1（待核销）` 且 `expires_at <= now()` → `status=3（已过期）`，
  并 `award_points(+points_cost, source=7, related_id=兑换单id, description="兑换过期退还")`
- 有效期：`REDEMPTION_CODE_EXPIRE_DAYS`（默认 30 天）
- 幂等三道闸：条件更新（已处理的单不再被选中）+ `points_log` 唯一索引（`source=7 + related_id + user_id`）+ 单笔独立事务
- 单笔失败只记日志，不影响同批其它单

> **为什么退分要用 `source=7` 而不是复用 `source=5`**：`points_log` 有唯一索引
> `uk_points_log_source(source, related_id, user_id)`。同一笔兑换单如果消耗与退还都用
> `source=5 + 同一个 related_id`，退还时必然撞唯一键被拒（409）。用 7 之后，
> 同一笔单据可以同时存在「消耗」和「退还」两条流水。

---

## 5. 错误码速查

| 状态码 | 含义 | 典型场景 |
|---|---|---|
| 400 | 参数或业务校验失败 | 积分不足 / 库存不足 / 重复核销 / 已过期 / 拒绝未填原因 |
| 401 | 未登录或 token 失效 | 缺 `Authorization` 头、token 过期 |
| 403 | 无权限 / 功能关闭 | 未审核店铺上架商品 / 核销码非本店 / `MERCHANT_ENABLED=false` / 管理端角色不足 |
| 404 | 资源不存在 | 商家不存在 / 商品不存在 / 核销码不存在 / 未入驻 |
| 409 | 业务冲突（积分重复发放） | `PointsAwardError` |

---

## 6. 与任务书的差异汇总（全部为主动收紧或纠偏）

| # | 任务书 | 实现 | 原因 |
|---|---|---|---|
| 1 | 用户端商家列表 `GET /list` | `GET /shops` | 与 `/shops/{id}/products` 同前缀时通配段会抢占静态路由（FastAPI 匹配失败直接 422，不回退） |
| 2 | 管理端 5 个接口（不含 `/stats`、`/settle/{id}`） | 7 个（含 `/stats`、`/settle/{id}`） | 按你的补充要求；总数因此为 20 而非 19 |
| 3 | `merchant` 表 13 列 | 追加 1 列 `audit_reason VARCHAR(255)` | 审核接口的 `reason` 需要落地，且商家要能看到被拒原因 |
| 4 | 审核 `reason?: str` 可选 | 拒绝时**必填** | 被拒却不知原因对商家是死路 |
| 5 | `sql/seed_merchants.sql` 纯 INSERT | 改为 `pool.ensure_merchant_seed()` | `initialize_schema` 每次启动全量执行，纯 INSERT 会「重启一次多 5 家店」 |
| 6 | 管理端只挂 `/api/admin` | 已按此实现（`/api/admin/merchant`） | 与其它 `admin_*` 一致 |
| 7 | 可选字段 | 重提申请时只覆盖**显式传入**的字段 | 避免「只改店名重提」把 category/address 静默清空 |

---

## 7. 快速联调示例

```bash
# 1) 入驻申请（用户 token）
curl -X POST http://127.0.0.1:8000/api/v1/merchant/apply \
  -H "Authorization: Bearer $USER_TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"社区打印店","category":"打印","contact":"13800000001"}'

# 2) 管理员审核通过
curl -X PUT http://127.0.0.1:8000/api/admin/merchant/6/audit \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"approved":true}'

# 3) 上架商品
curl -X POST http://127.0.0.1:8000/api/v1/merchant/products \
  -H "Authorization: Bearer $USER_TOKEN" -H "Content-Type: application/json" \
  -d '{"title":"打印券10张","points_cost":50,"stock":100}'

# 4) 用户浏览 + 兑换
curl http://127.0.0.1:8000/api/v1/merchant/shops
curl -X POST http://127.0.0.1:8000/api/v1/merchant/redeem \
  -H "Authorization: Bearer $BUYER_TOKEN" -H "Content-Type: application/json" \
  -d '{"product_id":1}'

# 5) 商家核销
curl -X POST http://127.0.0.1:8000/api/v1/merchant/redemptions/verify \
  -H "Authorization: Bearer $USER_TOKEN" -H "Content-Type: application/json" \
  -d '{"code":"482913"}'

# 6) 平台结算
curl -X POST http://127.0.0.1:8000/api/admin/merchant/settle \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"period":"2026-10"}'
```

---

## 8. 相关文件索引

| 层 | 文件 |
|---|---|
| 迁移 / 种子 | `app/db/pool.py` → `ensure_merchant_tables()` / `ensure_merchant_seed()` |
| 业务逻辑 | `app/services/merchant_service.py` |
| 请求/响应模型 | `app/schemas/merchant.py` |
| 商家端 + 用户端路由 | `app/api/v1/merchant.py` |
| 平台管理端路由 | `app/routers/admin/merchant.py` |
| 挂载 / 定时任务 | `app/main.py` |
| 测试 | `tests/test_merchant_api.py`（46 例） |
