# 变更影响分析：探索物品页「闲 / 新」双 Tab（一期）

> 分析时间：2026-10-15
> 范围：**仅一期** —— Tab 骨架 + 「新」Tab 展示商家好物
> 前置决策已确认：5 项全按建议执行
> 代码状态：**未修改任何文件**（等你确认后实现）

---

## 一、改动清单（总计 2 个文件）

| # | 文件 | 类型 | 说明 |
|---|---|---|---|
| 1 | `agent_front/src/views/ItemList.vue` | **改** | 外层包 `el-tabs`（2 个 pane）；「闲」pane 内现有内容**原样搬运，JS 逻辑一行不改**；新增 Tab 相关样式 + 非 scoped 主题段 |
| 2 | `agent_front/src/components/MerchantProductGrid.vue` | **新建** | N+1 拉商品、网格渲染、部分失败容错、空态、loading、重试 |

**明确不改**：

| 对象 | 原因 |
|---|---|
| `api/merchant.js` | 已有的 `getMerchantList` / `getShopProducts` **完全够用**，无需新增封装 |
| `router/index.js` | `/items` 内部改 Tab，**路由不变**；`/merchant`、`/merchant/:id` 原样 |
| `MerchantList.vue` / `MerchantDetail.vue` | 一期**只 import 它们的 api**，文件本身不碰 |
| `Home.vue` / `ProfileSubLayout` / `AppNav.vue` | 完全不碰 |
| 后端 / 数据库 | **零改动**（一期不碰 DB、不碰后端） |
| `package.json` | **零新依赖**（element-plus 2.14.6 已装 + 原生 CSS Grid） |

---

## 二、ItemList.vue 改造方案

### 2.1 现状结构（832 行）

```
<section class="page explore-page">
  ├─ .heading-row              ← 标题「正在流动的温暖物品」+ [上传物品] 按钮
  ├─ .filters.glass-card       ← keyword / category_id / exchange_mode + 搜索
  ├─ .sort-row.glass-card      ← 最新发布 / 离我最近 / 碳减排最多
  ├─ <div v-loading>           ← el-row 卡片网格 + 空态 + 错误 alert
  ├─ .pager                    ← el-pagination
  └─ <el-dialog uploadVisible> ← 上传物品弹窗
</section>
<style scoped>                 ← 只有 scoped，**没有非 scoped 段**
```

### 2.2 改造后结构

```
<section class="page explore-page">
  ├─ .heading-row              ← ★ 保留在 tabs 外（页面级）
  ├─ <el-tabs v-model="activeTab" class="explore-tabs">
  │    ├─ <el-tab-pane label="闲" name="used">
  │    │     ├─ .filters.glass-card     ← 原样搬入
  │    │     ├─ .sort-row.glass-card    ← 原样搬入
  │    │     ├─ <div v-loading>         ← 原样搬入
  │    │     └─ .pager                  ← 原样搬入
  │    └─ <el-tab-pane label="新" name="new" lazy>
  │          └─ <MerchantProductGrid />
  └─ <el-dialog uploadVisible> ← 保留在 tabs 外（弹窗，DOM 位置无关）
</section>
```

### 2.3 脚本改动（**只加 4 处，逻辑一行不改**）

```js
// ① import 新组件
import MerchantProductGrid from '../components/MerchantProductGrid.vue'

// ② Tab 状态（初值从 URL 读，见 D3）
const activeTab = ref(route.query.tab === 'new' ? 'new' : 'used')

// ③ Tab → URL 同步（可选，见 D3）
watch(activeTab, (tab) => {
  router.replace({ query: { ...route.query, tab: tab === 'new' ? 'new' : undefined } })
})
```

其余所有内容 —— `load()` 的排序回退与 `isRetry` 防死循环、`guideToSetLocation()`、`onImgError` 单次回填、`normalizeApiItem` 双层归一化、`submitUpload()` 的 11 项前置校验、`applyDraft()` 的中文分类名映射、`onMounted` 的 `from=pricing` 分叉 —— **一个字都不改**。

### 2.4 ★ 需要你拍板的 4 个细节

#### D1：`.heading-row`（含「上传物品」按钮）放 tabs 外还是「闲」内？

| 选项 | 效果 |
|---|---|
| **A. tabs 外（建议）** | 页面标题天然属于整页；「新」Tab 也能看到「上传物品」（用户逛到商家商品时可能想起「我也有闲置」）；改动最小 |
| B. 「闲」内 | 更"纯"，但「新」Tab 顶部空荡、无主操作，且要移动 DOM |

→ **建议 A**。

#### D2：「闲」Tab 的筛选/排序/页码，切到「新」再切回时是否保留？

你的原话是「**Tab 切换时清空对方的状态**」。这句有两种理解：

| 理解 | 具体行为 | 评价 |
|---|---|---|
| ① 字面：切走时重置对方 | 切到「新」→「闲」的筛选被清空；切回「闲」→ 回到初始状态（全部分类、最新发布、第 1 页） | ⚠️ 与硬约束「**现有 UI 原样保留**」冲突；用户体验上也偏差（手滑切一下就得重设筛选） |
| ② 隔离：互不干扰 | 两 Tab 各自持有状态、互不影响；「新」不显示「闲」的筛选栏，反之亦然 | ✅ 这才是"不串味"，也符合"原样保留" |

→ **建议按 ② 理解**（用 `el-tab-pane` 不卸载 + 各自独立 state 天然实现）。若你确实要 ① 的字面行为，我在 `watch(activeTab)` 里加一句重置即可，**请明确告知**。

#### D3：Tab 状态是否写进 URL（`?tab=new`）？

- **建议写**：刷新不丢、可分享、可深链
- **兼容性已确认安全**：`Home.vue:37` 的「开始探索」→ `/items`、`Home.vue:98` 的分类入口 → `/items?category_id=xx`，**都不带 `tab`** → 默认落「闲」，**既有入口语义完全不变** ✓
- 实现：`router.replace` 只改 `tab` 键、**保留其他 query**（`{...route.query}`），不破坏 `category_id` / `from=pricing`

#### D4：「新」Tab 是否做分类筛选？

- **建议不做**。原因（实测确认）：

| | 「闲」的分类 | 「新」的分类 |
|---|---|---|
| 数据源 | `GET /categories`（item 分类，**12 类**：图书文具/母婴玩具/数码家电…） | 商家 `category`（**5 类**：打印/便利店/理发/回收/家政） |
| 参数 | `category_id`（数字 ID） | `category`（**中文名精确匹配**） |

两套体系**完全不通用**，共用一套 chip 会误导用户；且一期 N+1 只拉回 10 个商品，无需筛选。
→ 若你希望有，「新」Tab 复用 `MerchantList.vue:123-130` 的 `CATEGORY_FILTERS` 常量（5 类）另起一行 chips 即可，**成本约 15 行**。

---

## 三、MerchantProductGrid.vue 设计

### 3.1 数据流（N+1，并发 + 容错）

```js
async function loadAll() {
  loading = true; error = false; partial = 0
  // ① 拉商家列表
  const data = await getMerchantList({ page: 1, size: 50 }, { skipErrorToast: true })
  const shops = (data?.list || []).filter(s => (s.product_count || 0) > 0)  // ★ 跳过 0 商品店
  if (!shops.length) { items = []; return }

  // ② 并发拉各店商品
  const settled = await Promise.allSettled(
    shops.map(s => getShopProducts(s.id, { skipErrorToast: true }))
  )

  // ③ 展平（部分失败只计数，不阻断）
  const flat = []
  settled.forEach((r, i) => {
    if (r.status !== 'fulfilled') { partial++; return }
    const shop = shops[i]
    for (const p of (r.value?.list || [])) {
      flat.push({ ...p, merchant_id: shop.id, merchant_name: shop.name,
                  merchant_category: shop.category })
    }
  })
  items = flat
}
```

**三个关键设计点**：

| # | 设计 | 理由 |
|---|---|---|
| ★1 | `skipErrorToast: true` **两个接口都要带** | `request.js:16` 对未标记的失败请求会**弹全局 `ElMessage.error`**。若某店在「列表拿到」与「拉商品」之间竞态下架（404），用户会看到一个莫名其妙的错误弹窗 —— 与"部分失败静默降级"直接冲突 |
| ★2 | `shops.filter(product_count > 0)` | 接口已返回 `product_count`（子查询统计的上架商品数，`merchant.py:553`）。空店直接跳过，省掉无效请求（当前 5 家店都有商品，但契约允许 0） |
| ★3 | 展平时**不改商品顺序** | 按「商家 id ASC + 商品 id ASC」（=接口返回顺序）保持稳定；前端**不做二次排序**，避免与店铺详情页的顺序不一致 |

### 3.2 卡片设计

```
┌────────────────────┐
│                    │
│        🖨️          │  ← emoji 占位（按商家 category）
│                    │
├────────────────────┤
│ 打印券10张          │  ← 商品标题（最多 2 行截断）
│ 🏪 社区打印店        │  ← 商家名
│ 50 积分    剩余 95  │  ← 积分 + 库存
└────────────────────┘
         ↓ 点击
   /merchant/{merchant_id}   ← 店铺详情页（商品无独立详情页）
```

**★ 已实测确认的关键事实**：

| 事实 | 影响 |
|---|---|
| **10 个在售商品的 `image_url` 全为 NULL** | emoji 占位是**主路径**，不是兜底。与 `MerchantDetail.vue:38` 的 `.product-thumb` 做法一致 |
| 有 1 个商品 `points_cost = 0`（旧家电估价券） | 免费券显示「**免费**」而非「0 积分」，沿用 `MerchantDetail.vue:155,165` 的既有口径 |
| 当前无 `stock = 0` 的商品 | 仍要做售罄态（库存会变）：卡片置灰 + 「已兑完」角标 |
| 商家分类只有 5 类 | emoji 映射复用 `CATEGORY_ICONS`（`MerchantDetail.vue:113-119`）：打印🖨️/便利店🏪/理发💇/回收♻️/家政🧹，未知回落 🏬 |

**点击去向**：`/merchant/{merchant_id}` —— 用户任务书明确指定。理由也成立：商品没有独立详情页，且兑换流程需要店铺上下文（`MerchantDetail` 内才有 `RedeemConfirmDialog`）。

⚠️ 注意：一期「新」Tab **只做展示与跳转，不做兑换按钮**（兑换仍在店铺详情页完成）。这符合「一期零后端改动」，也避免在两个地方维护兑换逻辑。

### 3.3 状态机（4 态）

| 状态 | 触发 | UI |
|---|---|---|
| `loading` | 首次加载（`lazy` 首次挂载时） | 骨架屏（6 个灰块闪动，CSS `@keyframes`） |
| `error`（全失败） | 商家列表请求失败 | 整块错误态：「商家好物加载失败」+ **[重试]** 按钮 |
| `partial`（部分失败） | N 家中 M 家失败 | 成功的**照常渲染** + 底部一行浅色提示「M 家店铺加载失败，已展示其余商品」+ **[重试]** |
| `empty` | 无商家 / 商家都无商品 | 🌿「暂无商家好物」 |
| `ready` | 有数据 | 商品网格 |

**重试**：`[重试]` 调 `loadAll()`（幂等，无参数）。

**⭐ 卸载安全**：加 `let alive = true` / `onUnmounted(() => alive = false)`，`await` 之后判 `if (!alive) return`，避免用户在请求飞行中切走 Tab 后，迟到的响应往已卸载组件的 ref 写值。

---

## 四、技术风险与规避（11 项）

| # | 风险 | 规避 |
|---|---|---|
| R1 | **el-tabs 内部 DOM 在 `scoped` 作用域之外**，样式打不中 | 用 `:deep()` 命中 `.el-tabs__header` / `.el-tabs__item` / `.el-tabs__nav-wrap::after` / `.el-tabs__active-bar` |
| R2 | el-tabs 自带的灰色下划线、内边距与现有「绿色玻璃卡」风格不协调 | `::after` 底边线改为透明；`.el-tabs__active-bar` 已是绿色渐变（`global.css:425`）—— **无需重定义，只调间距** |
| R3 | **首屏就发 6 个请求**（1 商家 + 5 商品），拖慢「闲」Tab 首屏 | `el-tab-pane lazy` —— ★ 已实测确认 element-plus **2.14.6** 支持（`tab-pane.mjs:32 lazy: Boolean`）→ **首次切到「新」才挂载并发请求** |
| R4 | 某店竞态 404 弹全局错误 toast | 两接口都带 `skipErrorToast: true` |
| R5 | **高对比度/助老**：`ItemList.vue` 现在**完全没有非 scoped 段**（全靠 `global.css` 通用规则撑着） | 新组件加**非 scoped 段**，前缀 `html.theme-high-contrast .mpg-root` / `html.mode-elderly .mpg-root`；「闲」Tab 可白嫖 `global.css:700` 已有的 `html.theme-high-contrast .el-tabs__item { color: #fff }` ✓ |
| R6 | 助老模式 Tab 点击目标 < 60px（现有 `global.css:545` 只给了 `.el-button` 48px） | 非 scoped 段给 `.explore-tabs .el-tabs__item` 加 `min-height: 60px` + 字号放大，与既有尺度协调 |
| R7 | 商品图裂图 | 主路径为 emoji（无 `<img>`，零风险）；若 `image_url` 有值则渲染 `<img>` + `@error` 单次回落到 emoji（复用 `ItemList.vue:336-341` 的 `dataset.fb` 模式，防死循环） |
| R8 | **切 Tab 闪烁** | 「闲」pane **不卸载**（不用 `v-if`，靠 `el-tab-pane` 原生 `v-show` 语义），列表 DOM 保持；`lazy` 只影响「新」的首次挂载 |
| R9 | 移动端网格挤压 | `grid-template-columns: repeat(auto-fill, minmax(150px, 1fr))`；`@media (max-width:500px)` → `minmax(130px,1fr)`；助老下强制 2 列 |
| R10 | **N+1 的后续扩展**（店铺/商品规模上升） | 把「取数」收敛在 `loadAll()` **单一函数**里，二期若加 `GET /merchant/products`（全平台商品），**只换这一处** |
| R11 | `el-tabs` 与页面顶部 `.filters` 的间距叠加 | `.explore-tabs :deep(.el-tabs__header)` 显式 `margin: 26px 0 0`，再把 `.filters` 的 `margin-top` 由 30px 收到 16px（**只动这一条 scoped 规则**，视觉等价） |

---

## 五、与硬约束的逐项对照

| 约束 | 是否满足 | 说明 |
|---|---|---|
| 一期不碰数据库 | ✅ | 零 SQL、零迁移 |
| 一期不碰后端 | ✅ | 零后端改动，纯复用现有 2 个接口 |
| 一期不做「用户物品换积分」 | ✅ | 二期（方案 C） |
| 不改动 MerchantList / MerchantDetail | ✅ | 只 `import` 其 api 函数，文件不打开 |
| 不引入新依赖 | ✅ | element-plus 2.14.6（已装）+ 原生 CSS Grid |
| 不重构无关代码 | ✅ | ItemList 只做「外包一层 + DOM 搬运」，`<script setup>` 仅加 3 处、逻辑零改动 |
| Hero / 网格 / ProfileSubLayout 样式不动 | ✅ | 完全不碰 `Home.vue` / `ProfileSubLayout.vue` |
| 「闲」Tab 现有 UI 原样 | ✅ | 卡片/筛选栏/发布按钮/360°角标/成色标签/CSS 全部原样（含 `modeClass` 三色、`.green-empty` 空态、`el-alert` 错误态） |
| Tab 切换流畅无闪烁 | ✅ | 见 R8 |
| 助老 / 高对比度正常 | ✅ | 见 R5、R6 |
| 移动端响应式 | ✅ | 见 R9 |

---

## 六、验证计划（实现后跑）

| 层 | 手段 |
|---|---|
| 静态 | `npx vite build` 通过；`@vue/compiler-sfc` 编译校验（组件解析为直接标识符、无漏 import） |
| 静态 | 断言：`el-tabs` 存在、「闲」pane 含 `.filters`/`.sort-row`/`.pager`、「新」pane 含 `<MerchantProductGrid/>`、`lazy` 属性在位、`skipErrorToast` 数量 = 2 |
| 静态 | 断言：`<script setup>` 的既有函数名全部仍在（`load`/`search`/`onSortChange`/`submitUpload`/`applyDraft`/`openUploadDialog`/`guideToSetLocation`/`onImgError`/`modeText`/`modeClass`/`conditionText`/`loadCategories`）—— 保证没误删逻辑 |
| 端到端 | 真实 HTTP：`GET /merchant/shops` 返回 5 家（`product_count` 均 > 0）→ 5 次 `GET /merchant/shops/{id}/products` 各返回 2 个商品 → 展平 10 条 |
| 截图 | headless Chrome 12 张：闲 Tab（列表+筛选）、新 Tab（网格）、Tab 切换后、商品卡 hover、空态、部分失败态、助老、高对比度、移动端 375px、店铺详情跳转落地页 |
| 回归 | 确认「闲」Tab 的筛选/排序/分页/上传弹窗/`?category_id=` 入口 / `?from=pricing` 草稿预填 **行为与改造前一致** |
| 数据 | 全程只读，`item` / `merchant_product` / `points_log` 行数与快照不变 |

---

## 七、我的执行顺序（确认后立即开始）

1. 新建 `components/MerchantProductGrid.vue`（自包含，可独立验证）
2. 改 `views/ItemList.vue`（外包 `el-tabs` + 搬运 DOM + 3 处脚本 + Tab 样式）
3. `vite build` + 静态断言脚本
4. 真实接口跑 N+1 数据核对
5. headless Chrome 截图目检（含助老/高对比度/移动端）
6. 输出《验证清单-探索物品双Tab一期.md》
7. 更新工作区日志

---

## 八、待你确认（4 项）

| # | 决策 | 我的建议 |
|---|---|---|
| **D1** | `.heading-row`（标题 + 上传按钮）位置 | **留在 tabs 外** |
| **D2** | 「Tab 切换时清空对方的状态」的语义 | 按**「互不干扰」**理解（筛选不重置，切回原样）；若要**字面重置**请明示 |
| **D3** | Tab 状态是否写 URL `?tab=` | **写**（`router.replace` 保留其他 query，既有 `/items?category_id=` 入口默认「闲」不受影响） |
| **D4** | 「新」Tab 是否做分类筛选 | **不做**（两套分类体系不通用；若要做，约 15 行复用商家 5 类 chips） |

四项都按建议走的话，实现完全落在一期内，**不碰 DB、不碰后端、不碰商家模块**。
