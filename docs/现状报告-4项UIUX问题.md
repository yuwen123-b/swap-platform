# 现状报告 —— 4 项 UI/UX 问题

> 勘查方式：任务书 8 个必读文件全部逐行通读 + 真实库 `information_schema`/数据实测 + 后端读/写路径全链路追踪。
> **本报告代码零改动**，仅勘查与建议。待确认后再分两批实现。

---

## 0. 结论速览：4 条阻断级发现

| # | 问题 | 任务书里的假设 | 实测真相 | 后果 |
|---|---|---|---|---|
| **B1** | 私信移走 | 移走私信入口 | 个人中心**当前没有任何私信入口**；`/messages` 除导航外只有一个入口（首页需求墙 `contactDemandOwner`） | **只删导航不加个人中心卡片 = 私信功能事实上不可达** |
| **B2** | 物品没有封面 | 「发布弹窗没有封面图上传，要加 ImageUploader」 | 发布弹窗**已经有** `ImageUploader`（必填单图）。真因是 `POST /items` 把**已签名 URL 落库**，而签名 TTL 只有 **1 小时** → **发布 1 小时后封面必然 403 裂掉** | **按「加 ImageUploader」改 = 完全没修到点上** |
| **B3** | 商家服务封面太丑 | emoji 占位难看 | 数据源本身是空的（`merchant.logo_url` **6/6 全 NULL**、`merchant_product.image_url` **0/10 有值**）；且 `MerchantList`/`MerchantDetail` **压根没读 `logo_url`**；`MerchantDetail` 的商品图用的是**店铺分类 emoji**（同店 10 个商品图完全相同） | **只改 CSS 不补数据 → 仍然没有真图；只补数据不改前端 → 前端根本不读** |
| **B4** | AI 生成封面（wanx） | 需要接入 wanx | 项目**已配置且已有封装** `llm_client.text_to_image()`（`wanx2.1-t2i-turbo`），`DASHSCOPE_API_KEY` 已配置，**但该函数从未被任何人调用** | 技术上可行、**零新依赖**，但有 3 个真实成本（见 3.2），不建议作为默认路径 |

---

## 1. 问题 1：私信

### 1.1 导航栏现在有哪些项

`agent_front/src/components/AppNav.vue:37-46`，`NAV_LINKS` 共 **8 项**，纯文字 `RouterLink`，**无图标、无未读角标、无登录态判断**：

| 序 | path | label |
|---|---|---|
| 1 | `/items` | 探索物品 |
| 2 | `/merchant` | 积分商城 |
| 3 | `/recognition` | 物品识别 |
| 4 | `/pricing` | 智能定价 |
| 5 | `/reviews` | 社区评价 |
| 6 | `/assistant` | 智能体助手 |
| 7 | **`/messages`** | **我的私信** ← 待移走 |
| 8 | `/profile` | 个人中心 |

顶栏结构（`AppNav.vue:1-30`）= `.brand`（品牌 logo + 「闲物焕新」）+ `nav.topnav`（8 项）+ `.account`（已登录显示昵称 + 退出；未登录显示登录 + 加入社区）。
**`.account` 区目前只有一个文字昵称和一个「退出」按钮 —— 预留给图标入口的空间是空的。**

响应式现状（`styles/global.css:456-475`）：≤1100px `gap` 收到 14px，≤900px 收 8px 且 `flex-wrap`，≤800px 导航整行下沉并可横向滚动。**8 项已接近换行临界点，减到 7 项反而缓解压力。**

### 1.2 私信页面的路由与组件

- 路由：`router/index.js:61` → `{ path: '/messages', component: Message, meta: { requiresAuth: true } }`
- 组件：`views/Message.vue`（左右分栏：左侧会话列表 + 未读角标，右侧聊天窗口；支持 `?otherUserId=` 直达会话）
- 接口（`api/message.js`）：`sendMessage` / `getChatHistory` / `getSessionList` / `markRead`
- **关键**：`GET /messages/sessions` 返回的会话项**已带 `unread_count`** → 顶栏做未读角标**零后端改动**，前端 `reduce` 求和即可。

### 1.3 个人中心现在有哪些卡片

`views/Profile.vue`，共 **9 个区块**（自上而下）：

1. `hero-card` 个人资料（头像、昵称编辑、加入天数、碳积分、等级进度）
2. 我的物品（3 条 + `/profile/items`）
3. 我的收藏（3 条 + `/profile/favorites`）
4. 我想要的（3 条 + `/profile/demands`）
5. 碳积分概览（3 条明细 + `/profile/carbon`）
6. 我的交换（3 条 + `/profile/exchanges`）
7. 我的兑换（3 条 + `/profile/redemptions`）
8. 我的回收单（3 条 + `/profile/recycle`）← 二期刚加
9. 系统设置（6 格 tile 网格：账户安全 / 位置管理 / 通知设置 / 无障碍设置 / 意见反馈 / 退出登录）

**没有任何私信相关卡片或 tile。** 第 2–8 个区块结构完全同构（`card-head` + `card-title` + `more-link` + `mini-*` 列表 + `mini-empty` 空态），复制一个「我的私信」卡片成本极低、一致性最好。

---

## 2. 问题 2：首页轮播图

### 2.1 有轮播图吗？几张？

**有**，`el-carousel` **4 张**（`Home.vue:11-23`），全屏 `100vh`，`interval=7000ms`，`arrow="never"` + `indicator-position="none"`（指示器隐藏），改用底部**自定义缩略图导航**（82×58px，当前项放大 1.14 倍 + 白边）。
过渡效果：淡入淡出 1.1s（覆写默认横向滑动）+ **Ken Burns 缓慢缩放**（`slowZoom` 12s 无限交替，`scale(1) → 1.12`）。

### 2.2 用的什么素材

**全是 Unsplash 远程 https 图**，定义在 `src/mock/home.js:11-36`（不是本地资源）：

| id | theme | Unsplash photo id |
|---|---|---|
| 1 | 绿色社区 | `photo-1466692476868-aef1dfb1e735` |
| 2 | 旧物改造 | `photo-1558618666-fcd25c85cd64` |
| 3 | 二手书籍 | `photo-1507842217343-583bb7270b66` |
| 4 | 邻里交换 | `photo-1555529669-e69e7aa0ba9a` |

统一切图参数 `?auto=format&fit=crop&w=1920&q=80`（缩略图 `w=320`）。

**本地素材现状**：`src/assets/` 下**只有 1 个文件** `hero-bg.jpg`（1178×1558 竖版，407KB），而且**全项目零引用**（dead asset，很可能是当初打算用但最终没接的图；竖版比例也不适合 100vh 横向 hero）。

### 2.3 文案是什么

Hero 区固定文案（**不随轮播切换**，4 屏共用同一套）：

- eyebrow：`社区 · 循环 · 智能`
- 主标题：`让闲置物品流动起来`
- 副标题：`在邻里之间交换旧物，用一份信任连接彼此，让每一次分享都成为更轻盈、更温暖的生活选择。`
- 按钮：`开始探索`（→ `/items`）/ `让 AI 帮你估价`（→ `/pricing`）

**4 个主题词（绿色社区/旧物改造/二手书籍/邻里交换）虽然写在 `mock/home.js` 里，但页面上一个字都不显示** —— `Home.vue:265-268` 的 `THEME_TEXT` 只用在 `<img :alt>` 和缩略图 `:title`（鼠标悬停 tooltip）。

### 2.4 现在的视觉调性

- 品牌：`闲物焕新`（顶栏 `.brand` = 「闲物」+ `.cyan` 后缀「焕新」，`global.css:162` 把 `.cyan` 映射到 `--green-primary`）
- 主色：`--green-primary: #2f855a`、`--green-active: #22543d`、`--c-main: #4caf50`、`--c-deep: #2e7d32`
- Hero 遮罩：左侧 `rgba(18,58,30,.86)` 向右渐隐到 0 + 底部 `rgba(12,38,20,.62)` 压暗
- 字体：白字、`font-weight: 800`、`letter-spacing: 2px`、`text-shadow` 双层绿色辉光
- 整体调性：**「绿色环保 / 可持续」**，不是「闲物焕新」这个品牌名本身的调性

### 2.5 「看不出是闲物焕新」的 3 个真实原因（按严重度）

1. **Hero `<img>` 没有 `@error` 兜底**（`Home.vue:21`）。
   对比：物品卡片有 `onImgError`（`Home.vue:516-521`）→ 回填内联 SVG 绿叶子占位图；**Hero 什么都没有**。
   Unsplash 在国内网络经常不可达 → 首屏直接变成**纯深绿空块 + 白字**（`.hero` 背景 `var(--c-deep)`）。这是最强解释。
2. **100vh 首屏内没有任何品牌标识**。品牌名只存在于顶栏那行小字（14px 导航旁），Hero 主视觉区 0 品牌元素、0 slogan 关联。「闲物焕新」四个字在首屏的视觉权重几乎为零。
3. **4 张图是泛化的「绿色/旧物/图书/交换」图库照**，彼此之间没有视觉统一性，也没有主题标签 → 用户看到的是「4 张好看的风景照」，无法与品牌建立关联。

---

## 3. 问题 3：物品封面

### 3.1 发布弹窗现在有哪些字段

`views/ItemList.vue:146-264`（`el-dialog`，560px，`destroy-on-close`）：

| 序 | 字段 | 控件 | 备注 |
|---|---|---|---|
| 1 | 物品名称 | input | 必填，≤50 字 |
| 2 | 物品描述 | textarea | 必填，≤500 字 |
| 3 | **物品图片** | **`ImageUploader`** | **必填，单图**，`:max-size=MAX_IMAGE_SIZE`（5MB） |
| 4 | 分类 | select | 必填 |
| 5 | 交易方式 | radio | 1 免费送 / 2 交换 / 3 低价转让 / **4 交给平台回收** |
| 5a | 期望交换物品 | input | 仅 mode=2 时显示 |
| 5b | 物品成色 / 平台估价 / 取件方式 / 取件地址 | radio+展示+input | 仅 mode=4 时显示（二期新增） |
| 6 | 转让价 | input-number | 仅 mode=3 时显示 |
| 7 | 联系方式 | input | 必填，≤100 字 |

### 3.2 有没有封面图上传？

**有，而且是复用公共组件 `ImageUploader`**（`ItemList.vue:172-181`）：

```
<el-form-item label="物品图片" required>
  <ImageUploader v-model="imageFile" mode="publish" :max-size="MAX_IMAGE_SIZE" />
</el-form-item>
```

`ImageUploader`（`components/ImageUploader.vue`）已具备：文件选择 / 拍照（含降级）/ 拖拽 / 类型与大小校验（jpg/png/webp/gif ≤5MB）/ 预览 / 移除。**组件只产出 `File` 对象，不做上传**，由 `submitUpload()` 组 `FormData` 提交。
后端也是必填校验：`item.py:347-348` —— `if image is None or not image.filename: raise HTTPException(400, "请至少上传 1 张物品图片")`。

> **所以任务书里「用户上传物品时没有封面」的表述，与代码事实不符：上传入口从一期起就存在、且是必填项。真正裂的是「上传之后」。**

### 3.3 物品卡片上的图从哪来？

**取 `images` 的第 0 个（首图），没有随机**：
`Home.vue:378-403` 的 `firstImage(item)` / `normalize(item)`，`ItemList.vue` 同逻辑 → `image: firstImage(item) || FALLBACK_IMAGE`。
取不到（NULL / 空数组 / JSON 解析失败 / 请求 403 触发 `@error`）→ 回填内联 SVG **绿叶子占位图** `FALLBACK_IMAGE`（`Home.vue:307-308`）。
「封面」这个概念**在数据模型里不存在** —— 只有 `images[0]` 即封面，也没有多图上传、没有指定封面。

### 3.4 后端 `items` 表的 `images` 字段怎么用

**写入（`POST /api/v1/items`，`item.py:362-385`）**：

```
items_dir = Path(settings.upload_dir).resolve() / "items"
filename  = f"{uuid.uuid4().hex}.{ext}"          # 磁盘真实文件名
image_path.write_bytes(data)                      # 落盘 uploads/items/xxx.webp
relative_path = f"items/{filename}"               # ← 相对路径
image_url = f"{settings.api_prefix}/static/{relative_path}?{sign_file_path(relative_path)}"
                                                  # ↑ 立刻签了个名（！）
images_json = json.dumps([image_url])             # ← 把「签名后的 URL」写进 DB
```

**读取**：`GET /items` 直接 `SELECT i.*`（`item.py:231-239`）**原样返回** `images`；`user_center._parse_images`、`favorite._parse_images`、`order._parse_images`、前端 `firstImage()` 全都**照用存进去的字符串，不做二次签名**。

**这就是根因链**：

1. `config.py:85` `file_url_expire_seconds = 3600` → **签名有效期只有 1 小时**；
2. `files.py:56` `verify_file_signature()` 过期即 `403 文件链接无效或已过期`；
3. 落库时签的名 1 小时后过期，而读取端**不会重新签名**；
4. ⇒ **任何通过 App 发布的物品，封面在发布 1 小时后必然裂掉**，前端 `@error` 回填绿叶子 → 用户看到「物品没有封面」。

**真实库铁证（实测，非推测）**：

| 证据 | 实测结果 |
|---|---|
| 库中 `item` 条数 | 8 条（id 55–61、77）；**无图 0 条** |
| `id=55~61`（演示数据） | 存的是 Unsplash 绝对 URL（`sign_relative` 对外链原样返回，所以目前还能显示） |
| `id=77 沙发`（真实上传） | `["/api/v1/static/items/d81797ab….webp?exp=1791968087&sig=2a7d2ebb…"]` |
| `exp=1791968087` 是何时 | **2026-10-14 16:54**（= 上传时刻 + 1 小时） |
| 当前时间 | 2026-10-16 —— **已过期约 1.7 天** |
| 实跑 `verify_file_signature()` | **`False`** |
| 文件是否还在磁盘 | **在**！`uploads/items/d81797ab….webp` 24204 字节 |

> **结论：图片文件完好无损，只是签名过期被拦在门外。** 这不是「没上传」，是「上传了但链接失效」。

**与项目既有约定直接冲突（这是最有力的一条）**：
`merchant_service.sign_relative()`（`merchant_service.py:133-148`）的 docstring 白纸黑字写着：

> 「与 item / user 的头像口径完全一致：**DB 只存相对路径，签名在读取时现场补（签名带 1 小时有效期，落库会立刻过期）**。」

`panorama_views` 也遵守该约定（`item.py:270` 注释：「DB 存相对路径 + 读取时补 HMAC 签名」）。
**唯独 `item.images` 自己违反了这个约定** —— 把带 `exp/sig` 的 URL 落了库。这是一处**约定违背（convention violation）**，不是单纯的 UI 问题。

---

## 4. 问题 4：商家封面

### 4.1 MerchantList 卡片上的商家图是什么

**纯 emoji，且根本没读 `logo_url`**：

- `MerchantList.vue:56`：`<span class="shop-logo">{{ categoryIcon(shop.category) }}</span>`
- `MerchantList.vue:133-143`：`CATEGORY_ICONS = { 打印:'🖨️', 便利店:'🏪', 理发:'💇', 回收:'♻️', 家政:'🧹' }`，兜底 `🏬`
- `.shop-logo` 样式（`:361-372`）= 64×64、`font-size: 30px`、浅绿→浅青渐变底、1px 描边、14px 圆角
- **数据侧：接口 `GET /merchant/shops` 其实已经返回了 `logo_url`（且已签名），前端只是没用。**

### 4.2 MerchantDetail 的商品图是什么

- 店铺头 `shop-hero .shop-logo`（`:19`）：`{{ shopIcon }}` → 同一个分类 emoji
- **商品缩略图 `.product-thumb`（`:38`）：`{{ shopIcon }}` —— 用的是店铺分类 emoji，不是商品自己的图！**

后果（实测数据）：同一家店所有商品图**完全相同且与商品无关** ——

| 商家 | 商品 | 卡片显示 |
|---|---|---|
| 社区打印店 | 打印券10张 / 复印券20张 | 🖨️ / 🖨️ |
| 24小时便利店 | 纸巾1包 / 洗衣液500ml | 🏪 / 🏪 |
| 美发工作室 | 基础理发券 / 洗剪吹套餐 | 💇 / 💇 |
| 家政服务站 | 保洁1小时 / 家电清洗 | 🧹 / 🧹 |

**这就是「太丑」的根因**：10 个商品只有 5 种图，且每种图只表示「这是哪家店」，完全不表示「这是什么东西」。

**唯一读了图片的是 `MerchantProductGrid.vue`**（探索页「新」Tab，一期双 Tab）：`<img v-if="good.image">`，`good.image = product.image_url || ''`，加载失败回退 emoji（`:195-197` 不回写远程 URL，避免重复请求）。**这说明「读图 + emoji 兜底」的模式在项目里已经有先例可抄。**

### 4.3 后端 `logo_url` / `image_url` 字段现状

| 项 | 结论 |
|---|---|
| 列定义 | `merchant.logo_url VARCHAR(500) NULL`（`pool.py:468`）；`merchant_product.image_url VARCHAR(500) NULL`（`pool.py:486`） |
| DTO 映射 | `to_merchant_brief()` 返回 `"logo_url": sign_relative(...)`；`to_product_item()` 返回 `"image_url": sign_relative(...)` —— **两处都已实现「读取时签名」** |
| 接口透出 | `GET /merchant/shops` SELECT 带 `m.logo_url`；`GET /merchant/shops/{id}/products` SELECT 带 `m.logo_url` 与 `p.image_url` → **数据已在前端手上** |
| 商家侧写入 | `PUT /merchant/info` 支持 `logo_url` 字符串（`_clean_text` 校验，`MAX_IMAGE_URL_LEN`）；`POST/PUT /merchant/products` 支持 `image_url` |
| **是否支持上传** | **否** —— 只能手填 URL 字符串，**没有图片上传接口**（`uploads/` 下也确实没有 `merchant/` 目录） |

### 4.4 真实库里这些字段有值吗

**全是 NULL。**（实测）

| 表 | 总行数 | 有值行数 |
|---|---|---|
| `merchant.logo_url` | 6 | **0** |
| `merchant_product.image_url` | 10 | **0** |

商家 6 行：`id=1 社区打印店(打印)`、`id=2 24小时便利店(便利店)`、`id=3 美发工作室(理发)`、`id=4 绿源回收站(回收)`、`id=5 家政服务站(家政)` 全部 `status=1, logo_url=NULL`；`id=13` 是 `status=0` 的未审核店（category 也为 NULL）。
商品 10 行（`points_cost` 30/50/80/100/200/300/500/800，含 1 个 `points_cost=0` 的「旧家电估价券」）全部 `image_url=NULL`。

> **所以即使前端立刻改成读 `logo_url`，画面也不会变 —— 数据源是空的。这是「不改数据修不好」的硬约束。**

---

## 5. 修复建议

### 5.1 问题 1：私信移走

**推荐方案 1-A（导航图标入口 + 个人中心卡片，双入口）**

| 改动点 | 内容 |
|---|---|
| 顶栏 | `NAV_LINKS` 删掉「我的私信」→ **8 项降为 7 项**（顺带缓解 ≤1100px 换行压力） |
| 顶栏 `.account` 区 | 新增**信封图标入口**（SVG + `aria-label="我的私信"`），不带文字，不占主导航；登录后显示，**带未读角标**（红点 + 数字，`99+` 截断） |
| 未读数据 | `getSessionList()` → `reduce(sum of unread_count)`；进入 `/messages` 或 `markRead` 后刷新。**零后端改动** |
| 个人中心 | 新增「我的私信」卡片（与「我的回收单」同构：`card-head` + `more-link` + 最近 3 条会话 + `mini-empty` 空态），放在「我的回收单」之后、「系统设置」之前 |
| 未登录 | 图标入口仅登录后显示（未登录时点它会跳登录页，体验差；不如不显示） |

**备选 1-B**：完全移走，只在个人中心留一个 tile/卡片（不保留图标）。
→ 不推荐：私信是**高频**入口，且首页需求墙 `contactDemandOwner` 依赖它；只在个人中心意味着用户每次聊完都要绕一圈。

**备选 1-C**：只加图标入口，个人中心不加卡片。
→ 不推荐：用户按产品直觉会去个人中心找私信，找不到会认为功能消失了。

### 5.2 问题 2：首页轮播图

**先定性：问题不是「图不搭」，是 3 件事叠加** —— ① `<img>` 无 `@error` 兜底（Unsplash 不可达即整屏空白）；② 100vh 首屏零品牌元素；③ 主题词只藏在 `alt` 里。

| 方案 | 做法 | 成本 | 评价 |
|---|---|---|---|
| **2-A（推荐）** | **保留 4 张底图，叠品牌层**：① eyebrow 改为品牌 `闲物焕新 · 社区旧物互换`；② 每屏新增**可见主题标签**（绿色社区/旧物改造/二手书籍/邻里交换），显示在标题上方，随轮播切换；③ `<img>` 加 `@error` 兜底（复用 `FALLBACK_IMAGE` 或改 CSS 渐变底） | 纯前端，1 个文件 | **当天可验证，直接命中「看不出是闲物焕新」的两个直接原因**。零素材、零依赖 |
| 2-B | **弃用 Unsplash，纯 CSS 品牌 Hero**（4 屏品牌渐变 + 大号品牌字 + 分类 emoji 拼贴） | 纯前端，1 个文件 | 彻底离线可用、绝不裂图；但视觉比照片「素」，且工作量大 |
| 2-C | **换成本地大图**（用户提供 4 张 ≥1920×1080 横向图，或复用 `hero-bg.jpg`） | 需素材 | 效果最好；但 `hero-bg.jpg` 是 **1178×1558 竖版**，铺 100vh 横向 hero 会严重裁切，**不建议直接用** |
| 2-D | 只加 `@error` 兜底，不动文案 | 纯前端 | 只治标（不裂了），但「看不出品牌」依旧 |

**我的推荐：2-A 立即做**（第一优先），若要更好视觉，再叠加 2-C（用户供图）。
**文案改法建议**：
- eyebrow：`社区 · 循环 · 智能` → **`闲物焕新 · 闲置物品循环平台`**（把品牌名放进首屏最大视觉权重位置）
- 保留主标题「让闲置物品流动起来」与副标题（文案本身不弱，弱的是缺品牌锚点）
- 每屏主题标签：`① 绿色社区 ② 旧物改造 ③ 二手书籍 ④ 邻里交换`（pill 胶囊样式，与 eyebrow 同族）
**附带建议**：`assets/hero-bg.jpg` 零引用，若确定不用，建议**一并清理**（或明确留作移动端竖屏底图），避免继续当死资源。

### 5.3 问题 3：物品封面

**核心结论：不需要加 ImageUploader（已有），要修的是「封面 1 小时后过期」。**

| 方案 | 做法 | 评价 |
|---|---|---|
| **3-A（强烈推荐，唯一正确解）** | **改回项目约定：DB 只存相对路径，读取时现场签名** | 见下方展开 |
| 3-B | 用户上传 + 无图则 AI 生成（wanx） | 见 3.2 |
| 3-C | 只做 AI 生成（去掉上传） | 不建议：二手交易让买家看到 AI 图 = 图文不符 |
| 3-D | 只加「多图上传 / 指定封面」 | 治的不是本问题；建议单开 |

**3-A 具体改法（4 处读 + 1 处写）**：

| # | 位置 | 改什么 |
|---|---|---|
| 1 | `item.py:369-376`（写） | `images_json = json.dumps([relative_path])` —— 只存 `items/uuid.webp`，**不签名落库** |
| 2 | `item.py` `list_items`（`SELECT i.*`） | 返回前把 `images` 里的相对路径过 `sign_relative()` |
| 3 | `item.py` `get_item`（详情） | 同上 |
| 4 | `user_center._parse_images` / `favorite._parse_images` | 同上（这两处是「我的物品」「我的收藏」的封面来源） |
| 5 | `order._parse_images`（交换记录里的物品图） | 同上，保持一致 |

**兜底与存量兼容（必做，否则会二次踩坑）**：

- `sign_relative()` 对 `http(s)://` 外链**原样返回** → 演示数据 55–61 不受影响；
- 对**已含 `?exp=&sig=` 的旧值**（如 id=77）必须**先剥掉 query 再重签**，否则会双重签名（`?exp=..&sig=..?exp=..&sig=..`）→ 需要一个 `_resign_images()` 辅助函数：`取 path 部分 → sign_relative()`。
- 存量修复：**不需要写 SQL**。改完读取逻辑后，id=77 的封面**当场自动恢复**（`verify_file_signature` 从 `False` 变 `True`），因为文件名没变、只是在读取时补了新签名。**这是这套改法最漂亮的地方：数据零迁移。**

**3-B（AI 生成封面）的真实成本 —— 技术上可行，但不建议**

好消息（比预期好）：**项目已有现成能力，零新依赖**
- `settings.llm_image_gen_model = "wanx2.1-t2i-turbo"`（`config.py:46`）
- `llm_client.text_to_image(prompt, size)` 已封装好（`llm_client.py:244-251`），走百炼异步任务 + 轮询
- `DASHSCOPE_API_KEY` **已配置**（实测 `bool(key) == True`），`requests` 已是既有依赖
- 但**该函数全项目从未被调用**（grep 零调用方）—— 是「已铺好但没接」的休眠能力

坏消息（3 个必须正视的成本）：

1. **返回的是远程临时 URL**（百炼 OSS，通常 24h 内失效）→ **必须立刻下载字节并落到 `uploads/items/`**，否则就是**问题 3 的坑原样重演一次**（又存一个会过期的 URL 进 DB）。
2. **同步等待 10–60 秒**（异步任务 + 轮询）→ 若放进 `POST /items` 同步流程，发布按钮会转圈近一分钟；若异步，则要新增「封面生成中/失败」状态字段与轮询接口 —— **这是不小的工作量，且会改动发布主流程**。
3. **语义风险**：用户上传的是实物照，AI 凭标题生成的图与实物不符，对二手交易是**负向**（买家按图索骥落空 = 投诉级问题）。

**我的推荐：3-A 必做；3-B 不做**（至少本期不做）。
**建议的决策：D5 确认按 3-A 修（含存量 77 自动恢复验证）；D6 本期不加多图/指定封面。**

### 5.4 问题 4：商家封面

**先定性：三个问题叠加 —— ① 库里图全 NULL；② `MerchantList`/`MerchantDetail` 不读 `logo_url`；③ 商品图错用店铺 emoji。**

| 方案 | 做法 | 素材 | 评价 |
|---|---|---|---|
| **4-A（推荐先做）** | **CSS 品牌化占位**：① 商家 logo = **商家名首字大字** + 分类 emoji 小角标 + 按 `id % N` 稳定取一组品牌色渐变（同名不同色、可复现）；② 商品图 = **商品名首字** + emoji 小角标 + 按 `points_cost` 分档品牌色（≤50 浅绿 / ≤200 中绿 / >200 深绿）→ 「打印券10张」与「复印券20张」一眼区分 | 零 | **纯模板+CSS，零素材零依赖不动后端**，直接解决「同店商品图全一样」和「大灰块里的 emoji」 |
| 4-B | 统一风格插画（5 个分类 × 1 张 SVG） | 需 5 个 SVG | 效果最好，但要备素材、新增 5 个文件 |
| 4-C | 真实实拍图（6 商家 + 10 商品） | 需 16 张图 | 最真实，但**需先补图片上传接口**（现在只能填 URL） |
| 4-D | 品牌色几何图形占位（不用 emoji） | 零 | 最干净，但辨识度低 |

**我的推荐：4-A 立即做（治「丑」）+ 4-C 作为数据侧长期方案（走已支持的 `sign_relative` 口径，将来商家自己能传图就自动生效）。**
**同时建议（低成本、高价值）**：**让前端真正读 `logo_url` / `image_url`** —— 后端已返回、已签名、`MerchantProductGrid` 已有先例；改动只是 `:src` + `v-if` + `@error` 回退三段式。这样「CSS 占位」与「真图」不是二选一，而是**有真图就显示真图、没有才占位**，一次改动同时覆盖现在与将来。
**决策 D7**：占位方案（4-A / 4-B / 4-C）？
**决策 D8**：是否同时接上 `logo_url` / `image_url` 的真图渲染（我建议**是**）？

---

## 6. 分批建议（按「是否触碰后端与数据」切，便于隔离回滚）

### 第一批：纯前端（零后端、零数据、零迁移）

| 问题 | 内容 | 触及文件（估） |
|---|---|---|
| 1 | 导航 8→7 + `.account` 信封图标 + 未读角标；Profile 新增「我的私信」卡片 | `AppNav.vue`、`Profile.vue`、`api/message.js`（复用）、`global.css`(样式) |
| 2 | Hero 品牌层（品牌 eyebrow + 每屏主题标签）+ `<img @error>` 兜底 | `Home.vue`、`mock/home.js` |
| 4 | CSS 品牌化占位 + 接上 `logo_url`/`image_url` 真图渲染 | `MerchantList.vue`、`MerchantDetail.vue`、`MerchantProductGrid.vue`（保持一致） |

**特点**：一个 `vite build` 即可交付，不碰接口、不碰表、不碰数据，风险最低。
**不破坏性**：双 Tab（`ItemList.vue` 的 `el-tabs`）、商家模块、回收模块**均不触碰**。

### 第二批：动后端 + 修存量数据

| 问题 | 内容 | 触及文件（估） |
|---|---|---|
| 3 | `item.images` 改存相对路径（写 1 处）+ 读取时签名（读 4 处）+ 旧值重签兼容 + 存量 77 自动恢复验证 | `item.py`、`user_center.py`、`favorite.py`、`order.py` |

**特点**：唯一涉及数据/后端改动的一批，**必须单独隔离**，便于出问题单独回滚。
**为什么不和第一批合并**：它要动 `GET /items` / 详情 / 我的物品 / 我的收藏 / 交换记录 **5 条读路径**，并跑全量 pytest 回归 + 端到端验证；混在一起会让第一批的「纯 UI 快交付」优势丧失。

### 备选划分（按用户感知优先级）
第一批 1+3（可达性 + 封面裂图，都是「功能级」问题），第二批 2+4（视觉美化）。
→ **我更推荐上面的「按风险面」划分**，因为问题 3 是唯一的后端/数据改动。

---

## 7. 待决策清单

| # | 决策 | 我的推荐 |
|---|---|---|
| **D1** | 顶栏是否保留私信图标入口？ | **保留**（`.account` 区信封图标 + 未读角标） |
| **D2** | 个人中心用「卡片」还是「系统设置里加一格 tile」？ | **卡片**（与「我的兑换」「我的回收单」同构，可预览最近会话） |
| **D3** | Hero 底图方案（保留 Unsplash / 换本地图 / 纯 CSS）？ | **保留 Unsplash + 加品牌层 + `@error` 兜底**（2-A） |
| **D4** | Hero 文案是否按建议改（eyebrow 换品牌名 + 每屏主题标签）？ | **是** |
| **D5** | 问题 3 按 3-A 修（DB 存相对路径 + 读取时签名 + 存量自动恢复）？ | **是** |
| **D6** | 本期是否加「多图上传 / 指定封面」？ | **不加**（避免 diff 过大，建议单开） |
| **D7** | 商家封面占位方案（4-A / 4-B / 4-C）？ | **4-A**（CSS 品牌化占位） |
| **D8** | 是否同时接上 `logo_url`/`image_url` 真图渲染？ | **是**（成本低、覆盖将来） |

---

## 8. 验证计划

### 第一批（纯前端）
- `vite build` 通过；
- 静态断言（预计 ≥20 项）：导航项 8→7 且不含 `/messages`；`.account` 含信封入口与 `aria-label`；未读角标逻辑存在；Profile 含「我的私信」卡片且路由 `/profile/recycle` 与新卡片并存；Hero eyebrow 含「闲物焕新」；Hero `<img>` 有 `@error`；每屏主题标签存在；`MerchantList`/`MerchantDetail`/`MerchantProductGrid` 三处 `logo_url`/`image_url` 使用一致；
- CDP 截图（预计 5–6 张）：首页 Hero（2 屏，验证品牌层与主题标签）、个人中心（私信卡片）、积分商城（新占位）、商家详情（商品图可区分）；
- **回归红线**：`ItemList.vue` 的 `el-tabs` / `load` / `applyDraft`、商家模块、回收模块**零改动**（沿用既有静态断言脚本）。

### 第二批（动后端）
- `pytest` 全量：**基线 471 必须保持全绿**（既有用例零修改），新增 ≥8 例：
  1. 发布后 `item.images` 存的是**相对路径**（不含 `exp=`/`sig=`）；
  2. `GET /items` 列表返回的 images **含** `exp=`&`sig=`；
  3. `GET /items/{id}` 详情同上；
  4. 「我的物品」封面同上；
  5. 「我的收藏」封面同上；
  6. **旧值重签**：喂入已含 `?exp=&sig=` 的旧值 → 输出**只有一个** `exp=`（不双重签名）；
  7. **外链原样**：`https://…` 不被改写；
  8. 脏数据（NULL / 空串 / 非 JSON 裸路径 / 坏 JSON）不 500，降级空或按既有约定处理；
- 端到端（真实库真事务）：发布 → 读回 URL 带新签名 → `verify_file_signature()` 为 `True`；**以 `item.id=77` 做存量回归** —— 改前 `False`（实测已确认）→ 改后 **`True`**，页面封面从绿叶子恢复为真实图片；
- 截图：探索页/我的物品中 id=77 封面恢复正常。

---

## 9. 约束核对

| 约束 | 本方案是否满足 | 说明 |
|---|---|---|
| 不改动核心业务逻辑 | ✅ | 第一批纯展示层；第二批只改「图片 URL 的存储形态与读取时签名」，**不改状态机、不改积分、不改订单/回收事务** |
| 不破坏双 Tab | ✅ | `ItemList.vue` 模板中 `el-tabs` 区块不在任何改动清单内 |
| 不破坏商家模块 | ✅ | 只改 `MerchantList`/`MerchantDetail`/`MerchantProductGrid` 的**图片渲染**；后端 merchant 接口零改动 |
| 不破坏回收模块 | ✅ | 回收相关文件零触碰（`item.py` 第二批只改图片相关行） |
| 不引入新依赖 | ✅ | 两个 `package.json` 均不加依赖；后端不动 `requirements.txt`（若做 3-B 也只需已装的 `requests`） |
| 不重构无关代码 | ✅ | 最小 diff；`ImageUploader` 直接复用不改造 |

---

## 10. 一句话总结

**4 个问题里，3 个的真实根因和任务书假设不同**：私信是「移走会真的消失」（缺入口）、物品封面是「签名 1 小时过期」（不是缺上传）、商家封面是「数据空 + 前端不读」（不是单纯丑）；只有首页轮播图的判断方向基本正确（确实缺品牌要素，且多了个 `@error` 缺失）。
建议**第一批修 1/2/4（纯前端，一天可验）**，**第二批单独修 3（动后端 + 存量自动恢复）**，等确认后开工。
