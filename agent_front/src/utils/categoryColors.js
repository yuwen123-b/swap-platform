/**
 * 分类配色（封面渐变）
 * ------------------------------------------------------------
 * 一个分类一组线性渐变（135°），让「同类型商品」共享同一视觉语言、
 * 「不同分类」一眼可辨。色值取自 Tailwind 调色板，
 * 起点色偏亮、终点色偏深，保证白色图标在整条渐变上都有足够对比度。
 *
 * ⚠ 与 utils/productIcons.js 的 CATEGORY_ICONS 保持**同一套分类键**：
 *   键值取自真实库 merchant.category 的取值集合 {打印, 便利店, 理发, 回收, 家政}。
 *   新增分类时两处一起加，否则会出现「有图标没配色」或反之。
 */

export const CATEGORY_GRADIENTS = {
  打印: ['#3b82f6', '#1e40af'], // 蓝
  便利店: ['#f59e0b', '#d97706'], // 橙
  理发: ['#a855f7', '#7e22ce'], // 紫
  回收: ['#10b981', '#047857'], // 绿
  家政: ['#06b6d4', '#0e7490'], // 青
}

/** 兜底：分类为空 / 未收录时用中性灰，保证不出现透明或撞色 */
export const FALLBACK_GRADIENT = ['#64748b', '#334155']

/** 分类 → [起点色, 终点色] */
export function getGradient(category) {
  return CATEGORY_GRADIENTS[category] || FALLBACK_GRADIENT
}

/** 分类 → 可直接绑到 style.backgroundImage 的 CSS 渐变串 */
export function gradientCss(category) {
  const [from, to] = getGradient(category)
  return `linear-gradient(135deg, ${from}, ${to})`
}

/** 分类 → 起点色（用于需要单色点缀的场景，如小标签底色） */
export function accentColor(category) {
  return getGradient(category)[0]
}
