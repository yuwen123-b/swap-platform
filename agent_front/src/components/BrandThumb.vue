<template>
  <!--
    品牌化缩略图（商家 logo / 商品图通用）
    ------------------------------------------------------------
    ⚠ 已弃用（2026-10）：商品与商家封面一律改用 `ProductCover.vue`。
       原因：本组件的占位是「名称首字大字 + 分类 emoji 角标 + 按 seed 取色」，
       首字信息量弱、同店商品共用 emoji，导致「旧衣回收抵扣券 / 旧家电估价券」
       这类同店同首字的商品封面**完全重影**；且 emoji 跨系统字形差异大、
       与「专业产品展示」的视觉要求不符。ProductCover 用「分类渐变 + 语义图标」
       替代，四类封面（新Tab / 店铺详情 / 兑换弹窗 / 商家列表）口径统一。
       本文件暂予保留以备考（当前无任何引用，会被构建 tree-shaking 掉），
       新代码请勿再引用。

    渲染优先级：
      1. src 有值且加载成功 → 显示真实图片；
      2. src 为空或加载失败 → 品牌化占位：
         按 seed 稳定取一组品牌绿/青渐变（同名同色、可复现）+ 名称首字大字
         + 可选的小角标 emoji。

    为什么需要它：真实库 merchant.logo_url 6/6 全为 NULL、
    merchant_product.image_url 0/10 有值 —— 只改 CSS 不补数据看不到真图，
    只补数据不改前端前端又不读。本组件让「真图」与「占位」不是二选一，
    一次改动同时覆盖现在（全占位）与将来（商家自己传图）。
  -->
  <span class="brand-thumb" :class="`bt-${size}`" :style="thumbStyle">
    <img v-if="showImage" :src="src" :alt="name || '图片'" @error="onError" />
    <template v-else>
      <span class="bt-text" aria-hidden="true">{{ initial }}</span>
      <span v-if="emoji" class="bt-emoji" aria-hidden="true">{{ emoji }}</span>
    </template>
  </span>
</template>

<script>
/**
 * 商品价位档 → 配色种子（0 浅绿 / 1 中绿 / 2 深绿，与 PALETTES 前三位对齐）。
 * 放在这里是为了让「店铺详情页 / 探索页新 Tab / 兑换确认弹窗」三处共用同一份口径，
 * 避免各页面各抄一遍后漂移。
 */
export function priceTier(points) {
  const n = Number(points) || 0
  if (n <= 50) return 0
  if (n <= 200) return 1
  return 2
}
</script>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  /** 图片地址（后端已是签名后的受控 URL；外链也可） */
  src: { type: String, default: '' },
  /** 名称：用于取首字与 alt */
  name: { type: String, default: '' },
  /** 配色种子：同一种子恒定同一配色，建议传商家 id / 价位档位 */
  seed: { type: [Number, String], default: 0 },
  /** 右下角小角标 emoji（传空则不显示） */
  emoji: { type: String, default: '' },
  /** 尺寸档：sm | md | lg | banner（banner 用于铺满容器的横幅位） */
  size: { type: String, default: 'md' },
})

// 真图加载失败后永久回退到占位（不回写 src，避免失败图片重复请求）
const broken = ref(false)
watch(() => props.src, () => {
  broken.value = false
})

const showImage = computed(() => Boolean(props.src) && !broken.value)

// 首字：空名兜底「闲」（品牌名首字），保证占位区永远有内容
const initial = computed(() => (props.name || '').trim().charAt(0) || '闲')

/* 品牌色板：全部由品牌绿/青派生，与站点调性一致，同时让不同实体一眼可区分。
   索引 0/1/2 刻意排成「浅 → 中 → 深」，供商品价位档位直接复用。 */
const PALETTES = [
  ['#66bb6a', '#43a047'], // 0 浅绿（低价位档）
  ['#2f855a', '#1f6f4a'], // 1 中绿（中价位档）
  ['#14532d', '#0f766e'], // 2 深绿（高价位档）
  ['#0f766e', '#14b8a6'], // 3 青
  ['#2e7d32', '#66bb6a'], // 4 黄绿
  ['#276749', '#38b2ac'], // 5 墨绿 → 青
]

const thumbStyle = computed(() => {
  if (showImage.value) return undefined
  const n = Math.abs(Number(props.seed) || 0)
  const [from, to] = PALETTES[n % PALETTES.length]
  return { backgroundImage: `linear-gradient(135deg, ${from}, ${to})` }
})

function onError() {
  broken.value = true
}
</script>

<style scoped>
.brand-thumb {
  position: relative;
  display: grid;
  place-items: center;
  width: 100%;
  height: 100%;
  overflow: hidden;
  /* 兜底底色：真图加载失败时也不会留透明空洞 */
  background: linear-gradient(135deg, var(--green-primary), var(--teal));
}

.brand-thumb img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.bt-text {
  color: #fff;
  font-weight: 800;
  line-height: 1;
  letter-spacing: 1px;
  text-shadow: 0 1px 6px rgba(0, 0, 0, 0.2);
}

/* 小角标：白底圆点，保证在任意深浅渐变上都可辨识 */
.bt-emoji {
  position: absolute;
  right: 6%;
  bottom: 6%;
  display: grid;
  place-items: center;
  background: rgba(255, 255, 255, 0.94);
  border-radius: 50%;
  line-height: 1;
}

/* ---------- 尺寸档 ---------- */
.bt-sm .bt-text {
  font-size: 22px;
}

.bt-sm .bt-emoji {
  width: 18px;
  height: 18px;
  font-size: 10px;
}

.bt-md .bt-text {
  font-size: 28px;
}

.bt-md .bt-emoji {
  width: 20px;
  height: 20px;
  font-size: 11px;
}

.bt-lg .bt-text {
  font-size: 36px;
}

.bt-lg .bt-emoji {
  width: 24px;
  height: 24px;
  font-size: 13px;
}

.bt-banner .bt-text {
  font-size: 56px;
}

.bt-banner .bt-emoji {
  width: 30px;
  height: 30px;
  font-size: 16px;
}
</style>

<!-- ============================================================
     非 scoped：根级主题选择器（html.theme-* / html.mode-elderly）
     在 scoped 下不生效，必须写在这里。
     本组件被商家列表 / 商家详情 / 探索页「新」Tab 三处复用，
     主题覆盖放在组件内可保证三处口径一致、不会各自漂移。
     ============================================================ -->
<style>
/* 高对比度：品牌渐变一律压成纯黑（浅绿渐变 + 白字对比度不足），
   角标翻转为白底黑字，与站点其余高对比规则同口径。
   注意：背景色由组件内联 style 提供，必须 !important 才能覆盖。 */
html.theme-high-contrast .brand-thumb {
  background: #000000 !important;
  background-image: none !important;
}

html.theme-high-contrast .brand-thumb .bt-text {
  color: #ffffff;
  text-shadow: none;
}

html.theme-high-contrast .brand-thumb .bt-emoji {
  background: #ffffff;
  color: #000000;
}

/* 助老模式：占位大字同步放大（容器尺寸由各页面自行放大） */
html.mode-elderly .brand-thumb .bt-text {
  font-size: 34px;
}

html.mode-elderly .brand-thumb.bt-banner .bt-text {
  font-size: 64px;
}

html.mode-elderly .brand-thumb .bt-emoji {
  width: 24px;
  height: 24px;
  font-size: 13px;
}
</style>

