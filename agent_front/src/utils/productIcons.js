/**
 * 封面图标注册表（商品图标 + 分类图标）
 * ------------------------------------------------------------
 * 为什么用 `import.meta.glob(..., { query: '?raw' })` 而不是 `<img src>`：
 *   外部 SVG 通过 `<img>` 引入后是一个封闭的图片，其内部 `stroke="currentColor"`
 *   不会继承外层 CSS 的 `color`，也就无法被高对比度主题改色。
 *   这里把 SVG 源码在**构建期**内联进来（Vite 原生能力，零新依赖），
 *   由 ProductCover 用 v-html 渲染，于是「图标颜色由 CSS 控制」成立。
 *
 * 图标来源：Tabler Icons v3.31.0 outline（MIT），已落为静态文件：
 *   src/assets/icons/products/   商品图标（11 个，含兜底 package）
 *   src/assets/icons/categories/ 分类图标（3 个：便利店/回收/家政）
 *
 * 图标文件已预处理：剥离 width/height（避免与容器尺寸打架）、去掉来源注释与缩进。
 * 运行期 `normalizeSvg` 仍做一遍防御性清洗，保证 SVG 只受容器尺寸与 CSS 控制。
 */

// 构建期内联 SVG 源码（eager + ?raw → 值为字符串）
const PRODUCT_MODULES = import.meta.glob('../assets/icons/products/*.svg', {
  query: '?raw',
  import: 'default',
  eager: true,
})

const CATEGORY_MODULES = import.meta.glob('../assets/icons/categories/*.svg', {
  query: '?raw',
  import: 'default',
  eager: true,
})

/** 取文件名的 slug（不含扩展名），作为图标 key */
function slugOf(path) {
  const file = String(path).split('/').pop() || ''
  return file.replace(/\.svg$/, '')
}

/**
 * 防御性清洗：去掉注释与 width/height，补 focusable="false"。
 * 保证 `<svg>` 只能被外层 CSS 的 width/height 撑满（`svg { width:100%; height:100% }`）。
 */
function normalizeSvg(raw) {
  return String(raw || '')
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/<svg\b([^>]*)>/, (_match, attrs) => {
      const cleaned = String(attrs)
        .replace(/\s(?:width|height)="[^"]*"/g, '')
        .replace(/\sfocusable="[^"]*"/g, '')
      return `<svg focusable="false"${cleaned}>`
    })
    .trim()
}

/** slug → SVG 源码 */
const ICON_SVG = {}
for (const [path, markup] of Object.entries({ ...PRODUCT_MODULES, ...CATEGORY_MODULES })) {
  ICON_SVG[slugOf(path)] = normalizeSvg(markup)
}

/* ============================================================
   商品图标：标题关键词 → 图标 slug
   ------------------------------------------------------------
   匹配规则是 `title.includes(key)`，按**声明顺序**取第一个命中，
   因此顺序本身是语义的一部分：
   - 「洗剪吹」必须排在「理发」前（洗剪吹套餐不含"理发"，但语义更具体）
   - 「家电清洗」必须排在「旧家电」前（"旧家电清洗券"应判为清洗家电而非估价）
   - 「洗衣液」用完整词，避免和衣物类互相干扰
   关键词刻意留短（如「旧衣」而非「旧衣回收」），以便标题出现变体
   （"旧衣物回收券"、"旧衣回收抵扣券"）时仍能命中。
   ============================================================ */
export const PRODUCT_ICONS = {
  洗剪吹: 'haircut', // 洗剪吹套餐 → 理发工具
  理发: 'scissors', // 基础理发券 → 剪子
  打印: 'printer', // 打印券10张 → 打印机
  复印: 'document', // 复印券20张 → 复印（双页）
  纸巾: 'tissue', // 纸巾1包 → 纸卷
  洗衣液: 'detergent', // 洗衣液500ml → 瓶装液体
  旧衣: 'clothing', // 旧衣回收抵扣券 → 衣物
  旧家电: 'tv', // 旧家电估价券 → 家电
  家电清洗: 'appliance-clean', // 家电清洗 → 洗衣机/家电清洗
  保洁: 'cleaning', // 保洁1小时 → 清洁喷雾
  清洁: 'cleaning', // 泛化的清洁类兜底
}

/** 商品图标兜底：通用商品（找不到任何关键词时使用） */
export const DEFAULT_PRODUCT_ICON = 'package'

/** 分类图标：与商品图标共用同一套 SVG 文件（打印/理发直接复用商品图标） */
export const CATEGORY_ICONS = {
  打印: 'printer',
  便利店: 'store',
  理发: 'scissors',
  回收: 'recycle',
  家政: 'tidy',
}

/** 分类图标兜底：通用店铺（分类为空或未收录时使用，配色另由 categoryColors 兜底为灰） */
export const DEFAULT_CATEGORY_ICON = 'store'

/** 按商品标题取图标 slug */
export function getProductIcon(title) {
  const text = String(title || '')
  for (const [key, icon] of Object.entries(PRODUCT_ICONS)) {
    if (text.includes(key)) return icon
  }
  return DEFAULT_PRODUCT_ICON
}

/** 按分类取图标 slug */
export function getCategoryIcon(category) {
  return CATEGORY_ICONS[category] || DEFAULT_CATEGORY_ICON
}

/** slug → 可 v-html 的内联 SVG 源码（未知 slug 回落到兜底图标） */
export function iconMarkup(slug) {
  return ICON_SVG[slug] || ICON_SVG[DEFAULT_PRODUCT_ICON] || ''
}

/** 商品标题 → 内联 SVG 源码 */
export function productIconMarkup(title) {
  return iconMarkup(getProductIcon(title))
}

/** 分类 → 内联 SVG 源码 */
export function categoryIconMarkup(category) {
  return iconMarkup(getCategoryIcon(category))
}

/** 已注册的图标 slug 列表（调试 / 单测断言用） */
export const ICON_SLUGS = Object.keys(ICON_SVG)
