# 验证清单 —— 4 项 UI/UX 修复 · 第一批（纯前端）

> 交付范围：问题 1（私信移个人中心）+ 问题 2（首页 Hero 品牌层/兜底）+ 问题 4（商家封面品牌化占位）。
> 决策口径：D1–D8 全按推荐值执行。**零后端改动、零数据迁移、零新增依赖。**
> 验证时间：2026-10-16。环境：`vite dev :5173` → 后端 `:8000`（真实库 `swap`），Chrome 150.0.7871.187 headless。

---

## 1. 构建与静态断言

| 项 | 结果 |
|---|---|
| `vite build`（agent_front） | ✅ **built in 33.03s**（1833 modules，无 error） |
| 静态断言（79 项） | ✅ **79/79** |
| 两个 `package.json` | ✅ 零新增依赖 |

静态断言分布：私信 A1–A26（26 项）、Hero B1–B11（11 项）、商家封面 C1–C25（25 项）、零破坏回归 D1–D16（17 项）。

---

## 2. 真实浏览器验证（CDP 31/31）

| # | 验证点 | 结果 | 证据 |
|---|---|---|---|
| 1 | 首页可进入（登录态不被踢到 /login） | ✅ | `pathname === '/'` |
| 2 | Hero 品牌 eyebrow 可见 | ✅ | 文本 `闲物焕新 · 闲置物品循环平台` |
| 3 | Hero 主题标签随轮播切换 | ✅ | 第 1 屏 `绿色社区` → 点击缩略图 2 → `旧物改造` |
| 4 | 主导航 **7 项**且不含「我的私信」 | ✅ | `count=7, hasMsg=false` |
| 5 | 顶栏私信图标入口存在 | ✅ | `.msg-entry` |
| 6 | 顶栏**未读角标显示数字** | ✅ | `.msg-badge` 文本 `2`（与库中 user 23 未读数一致） |
| 7 | 底图全裂时出现品牌兜底层 | ✅ | `Network.setBlockedURLs(['*unsplash.com*'])` 后 `.hero-fallback` 存在 |
| 8 | 兜底时 Hero 底色为品牌渐变（非空白） | ✅ | computed background = `radial-gradient(...)` |
| 9 | 兜底时标题与 CTA 仍在（非空白首屏） | ✅ | `.hero-title` + `.hero-cta .cta-primary` 均在 |
| 10 | 个人中心有「我的私信」卡片 | ✅ | 卡片标题命中 |
| 11 | 私信卡片展示会话行 | ✅ | `rows=2`（孙丽 / 吴倩） |
| 12 | 私信卡片显示未读数 | ✅ | `.msg-unread` × 2 |
| 13 | 商家列表每张卡都有品牌化占位 | ✅ | 5 家，每卡 `.bt-text` 均为首字（社/2/美/绿/家） |
| 14 | 占位 = 首字大字 + emoji 角标 | ✅ | 例：`('社区打印店','社','🖨️')` |
| 15 | 不同商家配色 ≥3 种 | ✅ | `distinct=5` |
| 16 | 商家详情每件商品都有占位 | ✅ | 2 件 |
| 17 | **同店商品首字互不相同**（不再一模一样） | ✅ | `['纸','洗']` |
| 18 | 同店不同价位档配色不同 | ✅ | `distinct=2/2`（30 积分浅绿 / 100 积分中绿） |
| 19 | 回归：双 Tab（闲/新）仍在 | ✅ | `['闲邻里二手','新积分兑换']` |
| 20 | 页面无未捕获异常 | ✅ | `Runtime.exceptionThrown` 零条 |

**截图（8 张）**：`.workbuddy/_shots_batch1/`
`01-hero-slide1.png`（品牌层+主题标签+角标）· `02-topbar-msg-badge.png`（7 项导航+信封+红点2）·
`03-hero-slide2.png`（切屏主题标签变化）· `04-hero-offline-fallback.png`（断网兜底：品牌渐变+大字水印，非空白）·
`05-profile-msg-card.png`（我的私信卡片）· `06-merchant-list-branded.png`（5 家品牌化占位）·
`07-merchant-detail-products.png`（同店两商品首字/配色不同）· `08-items-dual-tab.png`（一期双 Tab 回归）

---

## 3. 逐条交付要求核对

| 用户要求 | 结果 |
|---|---|
| 导航栏私信变图标 + 未读红点 | ✅ 8 项→7 项，`.account` 区信封图标 + 红底角标（>99 显示 `99+`），登录后才显示 |
| 个人中心有「我的私信」卡片 | ✅ 位于「我的回收单」之后、「系统设置」之前；最近 3 条会话 + 未读数 + 空态 CTA |
| 首页 Hero 有品牌层 + 断网兜底（不白屏） | ✅ 品牌 eyebrow + 每屏主题标签；两级兜底（单张裂→藏图露渐变；全裂→品牌水印层） |
| 商家列表封面是品牌化占位（不再纯 emoji） | ✅ 首字大字 + 按 `id` 稳定取色的品牌渐变 + 分类 emoji 降为右下角小角标 |
| 商家详情的商品图不再同店一模一样 | ✅ 商品名首字 + 按价位档取色（≤50 浅绿 / ≤200 中绿 / >200 深绿）+ 店铺 emoji 小角标 |
| vite build 通过 | ✅ 33.03s |

---

## 4. 实现要点（供回溯）

**新增**：`agent_front/src/components/BrandThumb.vue`
- 一个组件覆盖「真图 + 占位」两条路径：`src` 有值且加载成功 → 真图；空/裂 → 品牌渐变 + 首字 + emoji 角标。
- `PALETTES` 6 组品牌绿/青，索引 0/1/2 刻意排成「浅→中→深」供价位档复用；按 `seed` 稳定取色（同名同色、可复现）。
- **`priceTier(points)` 从本组件具名导出**，商家详情页 / 探索页「新」Tab / 兑换确认弹窗三处共用同一份口径，不会各抄一遍后漂移。
- 高对比度主题在组件内统一压成纯黑白（浅绿渐变 + 白字对比度不足），避免三处各自漂移。

**改**：`AppNav.vue`（8→7 + 图标入口 + 60s 轮询 + 离开 `/messages` 刷新角标）、`api/message.js`（`getSessionList(config)` 透传 axios 配置，兼容旧调用）、`global.css`（`.msg-entry/.msg-badge` + 助老/高对比）、`Profile.vue`（我的私信卡片 + `.msg-unread`）、`Home.vue`（品牌层/主题标签/两级兜底）、`MerchantList.vue`、`MerchantDetail.vue`、`MerchantProductGrid.vue`、`RedeemConfirmDialog.vue`。

**顺手清理的死代码**：`MerchantProductGrid` 的 `.mpg-emoji` 两处规则、`RedeemConfirmDialog` 的 `.thumb-fallback`、商家页三处 `.shop-logo`/`.product-thumb` 的旧渐变底。

---

## 5. 遗留与建议（不在本批范围）

1. `views/merchant/Settings.vue`（商家工作台）的店铺 logo 仍是分类 emoji——本期按约束**未触碰商家模块**。建议下批或单独任务接 BrandThumb，否则商家上传真图后「自己看到的」与「顾客看到的」不一致。
2. `assets/hero-bg.jpg` 仍是零引用的死资源（1178×1558 竖版，不适合 100vh 横向 hero），建议确认后删除。
3. Unsplash 仍是远程依赖（D3 选了「保留底图」）。已加兜底，不再白屏；若要彻底离线，走 2-C（用户提供 4 张本地 1920×1080 图）。
4. 验证脚本 `capture.py` 必须在 `agent_back/` 目录下运行——`pydantic-settings` 按 CWD 读 `.env`，否则 JWT 密钥落到默认值、注入的登录态会被后端判 401（本次实测踩坑）。
