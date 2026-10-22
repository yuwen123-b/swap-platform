# 现状报告：探索物品页改为「闲 / 新」双 Tab

> 调研时间：2026-10-15
> 调研范围：只读。未修改任何文件。
> 目标：判断把「探索物品」页从单一列表改成「闲（二手交易）/ 新（积分兑换）」双 Tab 的可行性与最小改动面。

---

## 〇、结论速览

| 问题 | 结论 |
|---|---|
| 现有探索物品页有 Tab 吗？ | ❌ 没有，单列表 |
| 用户上架时能选「我要换积分」吗？ | ❌ **完全不能**，且代码里零痕迹 |
| 物品「换积分」需要多少改动？ | 🔴 **跨数据模型**：DB 加列/扩枚举 + 新接口 + 双边积分转账 |
| 「新」Tab 的数据源能直接拿到吗？ | ⚠️ **半能**：商家商品**没有全平台列表接口**，物品换积分**数据根本不存在** |
| 「闲」Tab 可以直接用现有接口吗？ | ✅ 可以（但要澄清一个枚举范围矛盾） |
| 有阻断级冲突吗？ | 🔴 有 2 个（见第七节） |
| 我的建议 | **分两期**：一期只做 Tab 骨架 + 商家好物（零数据模型变更）；二期再做「用户物品换积分」 |

---

## 一、现有「探索物品」页面（A）

**文件**：`agent_front/src/views/ItemList.vue`（832 行）
**路由**：`/items`（`router/index.js:43`）

### A1. 现在展示什么

单页物品瀑布流（`el-row`/`el-col` 响应式栅格：xs/sm 2 列、md 3 列、lg 4 列），数据源 **`GET /api/v1/items`**（`status=1` 审核通过的在售物品）。

每张卡片的字段：

| 元素 | 来源 | 说明 |
|---|---|---|
| 图片 | `item.images[0]` | 失败回落到内联 SVG 绿色占位图 |
| 成色角标 | `condition_level` | 1~5 → 成色一般/七成新/八成新/九成新/几乎全新 |
| 360° 角标 | `panorama_status === 'ready'` | 右下角绿底白字 |
| 标题 | `title` | |
| 交易方式标签 | `exchange_mode` | 见 A3 |
| 距离 | `distance_km` | 仅「离我最近」排序时后端返回 |
| 减碳量 | `carbon_value` | 「减碳 X kg」 |

**关键实现细节**（改动时不能破坏）：

- `load()`（361-410 行）异常处理很讲究：「离我最近」失败会**回退排序并重载一次**（`isRetry` 防死循环），未设置位置时弹引导框；其他错误**保留已加载的真实列表** + `el-alert` 提示，**不再用 mock 覆盖**（第 405 行注释明确写了这是刻意的）
- 图片加载失败只回填一次（`onImgError` 用 `dataset.fb` 标位，防死循环）
- `normalizeApiItem` / `normalizeDisplayItem` 双层归一化，兼容驼峰与下划线两种入参
- 页内嵌「上传物品」弹窗（`el-dialog`），表单随 `exchange_mode` 分支显示「期望交换物品」/「转让价」
- 支持 `?category_id=xxx`（首页分类入口）与 `?from=pricing&action=publish`（AI 估价草稿预填，会 await 分类加载后再映射中文分类名 → id）

### A2. 有没有分类筛选？筛选维度是什么

有，**三个筛选维度 + 一个排序维度**：

| 类型 | 控件 | 参数 | 备注 |
|---|---|---|---|
| 关键词 | `el-input` | `keyword` | 匹配 title / description |
| 分类 | `el-select` | `category_id` | 选项来自 `GET /categories`，失败回落 `mock/home.js` 的静态分类 |
| 交易方式 | `el-select` | `exchange_mode` | **单值**：1 免费送 / 2 交换 / 3 低价转让 |
| 排序 | `el-radio-group` | `sort_by` | `created_at` 最新 / `distance` 离我最近 / `carbon_value` 碳减排最多 |

分页：`pageSize = 12`，`el-pagination` 在 `total > pageSize` 时显示。筛选/排序变更均重置 `page = 1`。

⚠️ **后端 `exchange_mode` 是精确单值匹配**（`item.py:198-200` → `i.exchange_mode=%s`），传 `"2,3"` 不生效。若「闲」Tab 要限定为 2/3 两个值，**必须改后端**。

### A3. exchange_mode 怎么展示

卡片上一个圆角标签（`.tag-mode`）：

```js
const MODE_TEXT = { 1: '免费送', 2: '交换', 3: '低价转让' }   // ItemList.vue:270
function modeClass(code) {                                    // ItemList.vue:329
  if (Number(code) === 3) return 'mode-points'  // 低价转让 → 黄底 #fff8e1
  if (Number(code) === 1) return 'mode-free'    // 免费送   → 青底 #e0f2f1
  return 'mode-swap'                            // 交换     → 绿底 #e8f5e9
}
```

发布弹窗是 3 个 `el-radio-button`（1/2/3），与后端 `EXCHANGE_MODES = (1, 2, 3)`（`item.py:32`）**硬校验白名单**一致。

### A4. 现在有没有 Tab

❌ **没有**。`ItemList.vue` 是纯单列表。
全站 `el-tabs` 只有 3 处：`views/Login.vue`、`views/Review.vue`、以及 `styles/global.css:415-429` 的全局定制（`.el-tabs__item` 绿色主题、`.el-tabs__active-bar` 渐变条）。**可直接复用这套 Element Plus tab，不引新依赖**。

`MerchantList.vue` 用的是另一套（原生 `<button class="filter-chip">` chips），与 el-tabs 风格不同 —— 双 Tab 建议用 el-tabs（语义更准，且已有全局主题定制）。

---

## 二、现有积分逻辑（B）

### B1. 用户「发布物品」能获得多少积分

**10 分**（`sys_config.points_publish = '10'`，实测查库确认）。

读取路径：`points_service.get_int_rule(cursor, RULE_POINTS_PUBLISH, DEFAULT_POINTS_PUBLISH)`。

⚠️ **代码兜底默认值是 20，DB 实际值是 10**：
- `points_service.py:58` `DEFAULT_POINTS_PUBLISH = 20`
- `pool.py:213` 种子默认也是 `"20"`
- 但库里被改成了 `10`（说明有人通过管理端调过）

→ **规则以 DB 为准，不要硬编码 20**。

「完成交换」奖励 `sys_config.points_exchange = '20'`（兜底默认 50），碳减排 `carbon_per_exchange = '5.0'` kg。

### B2. 积分在什么时机发放

**两个时机，都不是「发布时」**：

| 时机 | 位置 | source | 分值 | 给谁 |
|---|---|---|---|---|
| **物品审核通过** | `app/routers/admin/item.py:77-86`（`audit_item`，status 4→1 时） | 1 发布物品 | `points_publish` = 10 | 发布者 |
| **完成交换** | `app/services/order_service.py:114-133`（`complete_order`，status 2→3 时） | 2 完成交换 | `points_exchange` = 20 | **买卖双方各一份** |

`audit_item` 的幂等设计值得注意（`admin/item.py:70-73` 注释）：靠开头的 `status != 4 → 400` 使发放分支天然幂等，第二次进入时 status 已是 1 直接返回。

`complete_order` 的幂等靠三层闸：条件更新 `WHERE status=2` 的 rowcount 判定 + `points_log` 唯一索引 `uk_points_log_source(source, related_id, user_id)`。

另外 `order_service.py:108-111` 有个细节：**买卖双方是同一用户时只发一次**（防自换自刷分）。

完整 `points_log.source` 枚举（`app/core/constants.py:66-78`）：

| source | 含义 | 是否已实现 |
|---|---|---|
| 1 | 发布物品 | ✅ |
| 2 | 完成交换 | ✅ |
| 3 | 收到好评 | ❌ 未实现 |
| 4 | 管理员调整 | ✅ |
| 5 | 兑换消耗 | ✅ |
| 6 | 免费送出奖励 | ❌ **未实现（预留）** |
| 7 | 兑换过期退还 | ✅ |

### B3. 用户能不能「直接用物品换积分」

🔴 **完全不能，且代码里零痕迹。**

证据：
1. `item.exchange_mode` 白名单硬校验 `(1, 2, 3)`（`item.py:32, 320-321`），非法值直接 400
2. DB 列注释也只写了「1=免费送 2=等价互换 3=低价转让」
3. 全仓 grep `accept_points` / `换积分` / `redeem_points` / `redeem-points` → **0 命中**

所以现状是二选一：
- **用物品换物品 / 免费送 / 低价转让** → 走 `POST /api/v1/orders`（交换单），双方各自确认 → 完成时双方各得 20 分
- **用积分换商家服务** → 走 `POST /api/v1/merchant/redeem`

**中间那条路（用积分换用户的物品 / 用物品换积分）不存在。**

### B4. 积分和现金的汇率

`MERCHANT_POINTS_TO_YUAN = 0.01`（**100 积分 = 1 元**），见 `app/core/config.py` + `.env`。

⚠️ **该配置只在后端，没有任何接口暴露给前端**（管理端也没有 —— 这正是阶段四《变更影响分析》里 C1 冲突的根源）。它目前**唯一用途**是计算商家结算佣金（`merchant_service.calculate_commission`）。

---

## 三、现有积分商城（C）

### C1. MerchantList.vue 在哪个路由

- 商家列表：`/merchant` → `agent_front/src/views/MerchantList.vue`（`router/index.js:45`）
- 店铺详情：`/merchant/:id` → `agent_front/src/views/MerchantDetail.vue`（`router/index.js:46`）
- 两者**都免登录可浏览**，只有「兑换」那一步要求登录（`router/index.js:44` 注释）

### C2. 导航栏怎么进入

`agent_front/src/components/AppNav.vue:37-46` 的 `NAV_LINKS`，**第 2 项**：

```js
{ path: '/items',    label: '探索物品' },   // ← 本次要改的页
{ path: '/merchant', label: '积分商城' },   // ← 商家模块入口
// ... 共 8 项，顺序即展示顺序
```

另有两条侧门（阶段三加的）：
- `Profile.vue`「我的兑换」卡片头的 `.head-links` → 「商家工作台」
- `MerchantList.vue` 页尾 `.merchant-entry` → 「我是商家，我要入驻」(`/merchant/apply`)

⚠️ **导航固定 8 项**（阶段三明确约束「导航保持 8 项不动」）。本次改 Tab **不需要动导航**。

### C3. 商家商品列表长什么样

⚠️ 注意层次：`/merchant` 展示的是**商家（店）列表**，不是商品列表。

**商家列表**（`GET /api/v1/merchant/shops`）：
- 顶部积分条（`profileStore.points` + 「积分明细」入口 / 未登录引导）
- 分类 chips：全部 / 打印 / 便利店 / 理发 / 回收 / 家政（**常量硬编码**，因后端无分类枚举接口，且 `/shops` 的 `category` 是**精确匹配**）
- 商家卡片：分类 emoji 占位 logo + 店名 + 「类型 · 在售 N 项」+ 地址
- 响应结构 `{ total, page, size, list: [...] }`，`list[i]` 由 `to_merchant_brief` 产出，含 `product_count`

**店铺商品**（`GET /api/v1/merchant/shops/{merchant_id}/products`）：
- 返回 `{ merchant: {...}, list: [...] }`，`list[i]` 由 `to_product_item` 产出
- 字段：`id / merchant_id / title / description / image_url / points_cost / stock / sold_count / status / created_at`
- **`image_url` 读取时现场 HMAC 签名**（DB 存相对路径），前端直接用即可
- ⚠️ **没有全平台商品列表接口** —— 商品只能按店取（`merchant_id` 必填）

实测在售商品 10 个（5 家店 × 2），积分价 0~800 分：

| id | 商家 | 商品 | 积分 | 库存 |
|---|---|---|---|---|
| 1 | 社区打印店 | 打印券10张 | 50 | 95 |
| 2 | 社区打印店 | 复印券20张 | 80 | 95 |
| 3 | 24小时便利店 | 纸巾1包 | 30 | 200 |
| 4 | 24小时便利店 | 洗衣液500ml | 100 | 60 |
| 5 | 美发工作室 | 基础理发券 | 200 | 50 |
| 6 | 美发工作室 | 洗剪吹套餐 | 300 | 30 |
| 7 | 绿源回收站 | 旧衣回收抵扣券 | 50 | 80 |
| 8 | 绿源回收站 | 旧家电估价券 | **0** | 999 |
| 9 | 家政服务站 | 保洁1小时 | 500 | 20 |
| 10 | 家政服务站 | 家电清洗 | 800 | 10 |

⚠️ 注意 id=8 `points_cost = 0`（免费券），前端已有「免费」文案分叉（`MerchantDetail.vue:155,165`）。

### C4. 用户兑换流程是什么

```
MerchantDetail.vue
  → 点商品「兑换」（免费券文案分叉）
  → RedeemConfirmDialog 二次确认
  → POST /api/v1/merchant/redeem { product_id }
  → 服务端单事务（merchant_service.redeem，顺序不可变）：
      ① 读商品+商家（校验：存在 / 商家已通过 / 商品上架 / 不是自己的店）
      ② SELECT points FOR UPDATE 校验余额（不足即 400，此时尚无任何写入）
      ③ 条件扣库存 UPDATE ... WHERE stock>0（防超卖）
      ④ INSERT redemption_order → 生成 6 位核销码 + 过期时间
      ⑤ award_points(-points_cost, source=5, related_id=order_id) 扣分写流水
  → RedeemCodeDialog 展示核销码 + 过期时间
  → 到店，商家在 /merchant/verify 输入 6 位码核销（status 1→2）
  → 超期未核销：定时任务置 status=3 已过期 + award_points(+points_cost, source=7) 退还
```

核销单表 `redemption_order` 的关键约束：

```
merchant_id  bigint  NOT NULL  ← ★ 必须有商家
product_id   bigint  NOT NULL  ← ★ 必须是商家商品
code         varchar(16) NOT NULL  ← 6 位核销码
```

🔴 **这两个 NOT NULL 是「用户物品换积分」无法复用 redemption_order 的硬性原因** —— 用户物品兑给个人，没有商家、没有到店核销环节，**谁来核销？** 见第七节冲突 C2。

---

## 四、关键业务问题（D）

### D1. 用户上架物品时能不能选「我要换积分」

❌ **不能。现在没有任何实现。**

要新增的完整链条（不只是加个字段）：

| 层 | 改动 |
|---|---|
| DB | item 加列（`accept_points`）**或**扩 `exchange_mode` 枚举 = 4 + 一个积分价字段 |
| 后端发布 | `EXCHANGE_MODES` 白名单放行 + `create_item` 加 Form 参数 + 校验积分区间 |
| 后端列表 | `list_items` 支持筛选「换积分物品」 |
| 后端**兑换动作** | 🔴 **全新接口**：扣兑换方积分 + 给发布方加积分 + 物品置为已换出（双边转账，事务 + 行锁 + 幂等） |
| 后端审核 | 若沿用「审核通过发 10 分」，换积分物品是否也发？（会叠加） |
| 前端发布弹窗 | 加「换积分」选项 + 积分输入框 |
| 前端详情页 | 加「用积分兑换」按钮（需余额校验、二次确认） |
| 前端列表 | 加 Tab |
| 管理端 | 物品审核页可能要展示 `accept_points`（可延后） |

### D2. 「闲」和「新」两个板块，数据源分别是什么

| 板块 | 任务书定义 | 真实数据源 | 可否直接实现 |
|---|---|---|---|
| **闲** | `item` 表 `exchange_mode=2`（交换）+ `3`（低价转让） | `item` 表（`status=1`） | ⚠️ 有矛盾，见下 |
| **新·用户物品换积分** | 「接受积分兑换」的物品 | 🔴 **数据不存在**（无 `accept_points` 字段、无任何记录） | ❌ 需先建数据模型 |
| **新·商家商品** | `merchant_product` 表 | `merchant_product`（`status=1`，10 条） | ⚠️ 需新增全平台商品接口，或前端并发 N 次拉店 |

**「闲」的矛盾**：任务书写「展示 `exchange_mode=2` 和 `3`」，但同一段的卡片要求又写着「模式标签（**交换/转让/免费送**）」—— **免费送是 `exchange_mode=1`，不在 2/3 范围内**。二者不能同时成立。

- 若按「闲 = 二手交易平台（用户之间交换、转让、**免费送**）」的定位 → 应是 **1/2/3 全部**，即「现有列表原样保留」
- 若严格按 2/3 → 免费送物品从「闲」消失，而「新」也不含它们 → **这些物品在两个 Tab 里都看不到**（当前库里有 2 件免费送物品）

→ 见第九节：**建议「闲」= 全量 1/2/3**（等价于现有列表原样保留，改动最小、不漏物品）。

**「新」的异构问题**：`item` 与 `merchant_product` 是**两个完全异构的实体**：

| | item（用户物品） | merchant_product（商家商品） |
|---|---|---|
| 主键空间 | `item.id` | `merchant_product.id` |
| 详情页 | `/items/:id` | `/merchant/:merchantId`（无独立商品详情页） |
| 兑换机制 | `order` 交换单 | `redemption_order` 核销单 |
| 交付方式 | 线下当面交接 | 到店核销 |
| 卖点字段 | 成色、减碳量、距离 | 库存、已兑换数、商家名 |
| 列表接口 | `GET /items`（全平台 + 分页） | **无全平台接口**，只能 `GET /merchant/shops/{id}/products` 按店取 |

→ **强烈建议「新」Tab 内部再分两个区块，不混排成一个列表**。理由：混排后分页无法合并（两个接口的 `total` 不可加），排序无意义，点击去向不一致。

---

## 五、数据模型变更：三方案对比

### 方案 A：item 加 `accept_points` 列（任务书方案 A）

```sql
ALTER TABLE item ADD COLUMN accept_points INT NOT NULL DEFAULT 0
  COMMENT '接受积分兑换的积分值，0表示不接受';
```

- ✅ 语义清晰，与 `exchange_mode` 正交（一个物品既能换物也能换积分）
- ✅ 迁移安全（走 `pool.py` 的 `_ensure_column`，幂等）
- ❌ **兑换动作接口仍需从零设计**（谁扣分、谁得分、物品怎么置状态、如何防自换自、幂等键怎么定）
- ❌ 与「免费送」语义冲突：免费送物品要不要也能换积分？

### 方案 B：扩 `exchange_mode = 4`（任务书方案 B）

- ❌ **会污染两处既有映射**：`item.exchange_mode → order.exchange_type` 的映射表（`order.py:84-92`）需要加分支；`EXCHANGE_MODES` 白名单、`MODE_TEXT`、`modeClass()`、发布弹窗的 radio 分支、`ItemDetail.vue` 的文案分叉全都要改
- ❌ `exchange_mode=4` 的物品还能不能发起普通「交换单」？语义互斥，容易出脏数据
- ❌ 还需要额外的积分价字段（`exchange_mode` 是 tinyint，放不下价）
- ⚠️ 破坏既有枚举的稳定性，与「不重构无关代码」冲突

### 方案 C（我推荐探索）：复用 `order.diff_points` + 加 `accept_points`

**重大发现**：`order` 表**已经有 `diff_points INT DEFAULT 0` 列（「补差积分」）**，且**代码里从未读写过**（全仓 grep 零业务引用）——这是一块**预留未用的能力**。

```
order 表现有列（全部可用）：
  item_id       目标物品ID
  buyer_id      发起方ID
  seller_id     发布方ID
  exchange_type 1=购买 2=以物换物 3=赠送
  diff_points   ★ 补差积分（DEFAULT 0，从未使用）
  status        1待联系 2已约定 3已完成 4已取消 5申诉中
  meet_time / meet_location / completed_at
```

「用积分换物品」天然就是**「以物换物 + 用积分补差」**的退化形态：买家出积分、卖家出物品。走 order 表的好处：

- ✅ **双边转账与幂等已有现成范式**：`complete_order` 的「条件更新 + `uk_points_log_source` 双闸」可直接套用
- ✅ **物品下架（status=2）已有现成逻辑**（`order.py:650`）
- ✅ 时间线、私信、双方确认流转**全部免费复用**
- ✅ 无需新建表，无需改 `redemption_order`
- ⚠️ 需要新增 `exchange_type=4`（或用 `diff_points>0` 表达），并**只读**复用给「新」Tab 的列表筛选

**方案对比结论**：

| 维度 | A（accept_points） | B（mode=4） | C（accept_points + order.diff_points） |
|---|---|---|---|
| 迁移风险 | 低 | **高**（污染既有枚举） | 低 |
| 兑换动作实现 | 从零设计 | 从零设计 | **可复用 order 流程** |
| 与现有代码冲突 | 低 | 高 | **最低** |
| 改动量 | 中 | 中高 | 中 |
| 我的推荐 | ⭕ 次选 | ❌ 不推荐 | ✅ **推荐** |

---

## 六、阻断级冲突与风险

### 🔴 C1：没有「全平台商家商品」接口

「新」Tab 要展示「商家商品兑换」，但现有接口只有：
- `GET /merchant/shops` → **商家列表**（含 `product_count`，不含商品明细）
- `GET /merchant/shops/{id}/products` → **某一家店**的商品

→ 前端要展示全平台商品，只能**并发拉 5 家店**（1 + 5 = 6 次请求）。当前规模可用，但商品/店铺规模上去就是 N+1 问题。

**选项**：① 一期接受 N+1（零后端改动）；② 新增 `GET /merchant/products`（全平台上架商品，带分页 + 可复用 `to_product_item`）—— 约 30 行。

### 🔴 C2：任务书第 2 步的 `POST /api/v1/items/{id}/redeem-points`「生成 redemption_order」不可行

`redemption_order` 的 `merchant_id` 与 `product_id` 都是 **NOT NULL**，语义是「商家核销单」。用户物品兑给个人：

- 没有 `merchant_id`（硬性 NOT NULL → 写不进去）
- 没有 `product_id`
- **没有核销环节** —— 谁核销？到哪核销？核销码给谁？
- 也没有「过期退还」的语义（个人之间当面交接，不该有 15 天超时退分）

→ 这条路走不通。**必须换落点**（见方案 C：走 `order` 表）。这是本次最大的设计分歧，需要你拍板。

### 🟡 C3：「新」Tab 的两类卡混排会破坏分页契约

`item` 与 `merchant_product` 是两个接口、两个 ID 空间、两个 `total`。混排后：
- 分页总数无法计算
- 排序无统一口径
- 点击去向不同（`/items/:id` vs `/merchant/:merchantId`）

→ 建议「新」Tab 内部**分两个独立区块**，各自加载/各自空态。

### 🟡 C4：Tab 状态是否写进 URL

不写 URL → 刷新回「闲」、无法分享/深链。
建议 `?tab=new` 双向同步（`watch` route.query），且**首页原有入口 `/items?category_id=xxx` 不带 `tab` 时默认落「闲」**，保证既有入口语义不变（`Home.vue:37,98` 与 `ItemList.vue:573` 都依赖 `category_id`）。

### 🟡 C5：换积分物品与「审核通过发 10 分」会叠加

若换积分物品沿用现有审核流程，发布者会同时拿到「发布奖励 10 分」+「被兑换所得的积分」。是否接受？是否需要限制（如发布 24h 内不可换积分）？

### 🟡 C6：改动面比想象大（涉及 4 个已完成模块的只读展示）

即便只做一期（Tab 骨架 + 商家好物），也要注意 **不能碰**：
- `MerchantList.vue` / `MerchantDetail.vue`（阶段一二三的商家模块，用户明确约束「不改动」）
- `Home.vue` 的物品展示区（`Home.vue:107-176`，独立拉 `/items`，共用 `mock/items.js` 回落逻辑）
- `ItemDetail.vue` 的「我要换」弹窗（`openSwap` + 文案分叉）
- `profile/ItemsView.vue`（我的物品，有下架能力）

---

## 七、需要你确认的 5 件事

| # | 问题 | 我的建议 |
|---|---|---|
| 1 | **「闲」的范围**：`exchange_mode` 1/2/3 全量 / 严格 2+3 | **全量 1/2/3**（=现有列表原样，卡片能正常显示「免费送」，且不漏物品） |
| 2 | **「新」Tab 是否混排** | **不混排**，内部两个区块：① 商家好物 ② 用户物品换积分 |
| 3 | **是否一期就做「用户物品换积分」** | **建议分两期**：一期只做 Tab 骨架 + 商家好物（零数据模型变更、零后端改动）；二期再做换积分 |
| 4 | **换积分的落点**（若二期做） | **方案 C**：`item.accept_points` 标价 + 复用 `order.diff_points` 流程（**不要**用方案 B 的 `exchange_mode=4`，也不要用 `redemption_order`） |
| 5 | **全平台商品**：N+1 / 新增接口 | 一期 N+1（零后端改动）；若你希望接口干净，我加 `GET /merchant/products` |

---

## 八、我的建议方案

### 一期（低风险，建议先做）

**目标**：探索物品页立刻有「闲 / 新」两个板块，且**零数据模型变更**。

| 层 | 改动 |
|---|---|
| 前端 | `ItemList.vue` 外层包 `el-tabs`（复用 `global.css` 已有主题）；「闲」= 现有全部逻辑原样；「新」= 新增商家好物区块（`/shops` + 并发拉各店商品，复用 `api/merchant.js` 的 `getMerchantList` / `getShopProducts`） |
| 前端 | `?tab=` URL 双向同步，默认「闲」 |
| 前端 | 「新」区块卡片：图片 / 标题 / 所需积分 / 商家名 / 库存；点击 → `/merchant/:merchantId` |
| 后端 | **零改动** |
| 风险 | 低。不动 DB、不动既有接口、不碰商家模块页面 |

### 二期（需你确认后做）

**目标**：打通「用户物品换积分」。

| 层 | 改动 |
|---|---|
| DB | `item` 加 `accept_points INT NOT NULL DEFAULT 0`（走 `pool.py` `_ensure_column`，幂等） |
| 后端 | `create_item` 加 `accept_points` Form 参数 + 校验；`list_items` 支持 `?accept_points=1` 筛选 |
| 后端 | **兑换动作**：复用 `order` 表（`diff_points`）+ 双边积分转账（行锁 + `uk_points_log_source` 幂等）；`complete_order` 增加「换积分」分支 |
| 后端 | 新增 `source=8`？或复用 source=2（完成交换）—— 需定 |
| 前端 | 发布弹窗加「换积分」选项 + 积分输入；`ItemDetail.vue` 加「用积分兑换」按钮（余额校验 + 二次确认）；「新」Tab 加「用户物品换积分」区块 |
| 测试 | pytest（发布/筛选/兑换/余额不足/自换自/幂等）+ vite build + 《验证清单》 |

---

## 九、与本次任务书的三处偏差（供修正）

1. **`Publish.vue` 不存在** —— 发布是 `ItemList.vue` 内嵌的 `el-dialog`（125-206 行），不是独立页面。
2. **`item_service.py` 不存在** —— 实际是 `app/services/item_query_service.py`（**只供智能体 function-calling 用的只读查询**，与物品发布/列表接口无关）；物品业务逻辑直接写在 `app/api/v1/item.py` 里。
3. **`POST /items/{id}/redeem-points` 生成 `redemption_order` 不可行** —— 见冲突 C2。

---

## 十、附：本次调研的关键文件与行号索引

| 关注点 | 位置 |
|---|---|
| 物品列表接口 | `agent_back/app/api/v1/item.py:191-238`（`list_items`） |
| 交易方式白名单 | `agent_back/app/api/v1/item.py:32-35` |
| 物品发布 | `agent_back/app/api/v1/item.py:289-389`（`create_item`，`status=4` 待审核） |
| 审核通过发分 | `agent_back/app/routers/admin/item.py:57-88` |
| 完成交换发分 | `agent_back/app/services/order_service.py:100-133` |
| 兑换（商家） | `agent_back/app/services/merchant_service.py:301-394` |
| 商家列表接口 | `agent_back/app/api/v1/merchant.py:527-567` |
| 店铺商品接口 | `agent_back/app/api/v1/merchant.py:570-600` |
| 兑换接口 | `agent_back/app/api/v1/merchant.py:606-617` |
| 积分枚举 | `agent_back/app/core/constants.py:66-78` |
| 汇率配置 | `agent_back/app/core/config.py`（`merchant_points_to_yuan = 0.01`） |
| 探索物品页 | `agent_front/src/views/ItemList.vue` |
| 积分商城页 | `agent_front/src/views/MerchantList.vue` |
| 店铺详情页 | `agent_front/src/views/MerchantDetail.vue` |
| 导航 | `agent_front/src/components/AppNav.vue:37-46` |
| tabs 全局主题 | `agent_front/src/styles/global.css:415-429` |
| 路由 | `agent_front/src/router/index.js:43-46` |
| item 表结构 | 29 列（`accept_points` 不存在） |
| order 表结构 | 含 **`diff_points`（补差积分，从未使用）** |
| redemption_order 表结构 | `merchant_id` / `product_id` **NOT NULL** |
