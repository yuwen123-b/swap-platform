<template>
  <!--
    通用封面组件（商品 / 商家）
    ------------------------------------------------------------
    渲染优先级：
      1. src 有值且加载成功 → 真实图片（后端接了图就优先显示真图）；
      2. 否则 → 分类渐变底 + 内联线性图标（+ 可选的首字角标）。

    为什么不用 <BrandThumb> 的「名称首字大字」：
      首字信息量弱（「旧」衣回收 vs「旧」家电估价 → 两个字一模一样），
      且同店商品共用分类 emoji，导致同店封面完全重影。
      改用「分类色 + 语义图标」后，同一商品在任何页面都能一眼认出类型。

    图标为 raw 内联 SVG（见 utils/productIcons.js），因此 `color` 可直接控制描边色，
    高对比度主题下把渐变压黑、图标保持白色即可清晰可辨。

    variant：
      product —— 商品卡片封面（图标 64px）
      shop    —— 商家封面（图标 36px + 商家名首字角标）
      mini    —— 弹窗内的小封面（图标 34px）
    图标尺寸可用 CSS 变量 --pc-icon-size 在调用处覆盖。
  -->
  <span class="product-cover" :class="`pc-${variant}`" :style="rootStyle">
    <img v-if="showImage" :src="src" :alt="alt" class="pc-img" @error="onError" />
    <template v-else>
      <span class="pc-glow" aria-hidden="true"></span>
      <span class="pc-icon" aria-hidden="true" v-html="iconSvg"></span>
      <span v-if="badge" class="pc-badge" aria-hidden="true">{{ badge }}</span>
    </template>
  </span>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { categoryIconMarkup, productIconMarkup } from '../utils/productIcons'
import { gradientCss } from '../utils/categoryColors'

const props = defineProps({
  /** 真实图片地址（后端已是签名后的受控 URL）；有值即优先显示 */
  src: { type: String, default: '' },
  /** 商品标题：决定取哪个商品图标，也是 img 的 alt */
  title: { type: String, default: '' },
  /** 商家名（仅 variant=shop 用：取首字做右下角小角标） */
  name: { type: String, default: '' },
  /** 分类：决定渐变配色；variant=shop 时还决定分类图标 */
  category: { type: String, default: '' },
  /** product | shop | mini */
  variant: { type: String, default: 'product' },
})

// 真图加载失败后永久回退到图标占位（不回写 src，避免失败图片重复请求）
const broken = ref(false)
watch(
  () => props.src,
  () => {
    broken.value = false
  },
)

const showImage = computed(() => Boolean(props.src) && !broken.value)

// 只有走占位分支时才铺渐变；真图分支保持透明，避免图片边缘透色
const rootStyle = computed(() =>
  showImage.value ? undefined : { backgroundImage: gradientCss(props.category) },
)

const isShop = computed(() => props.variant === 'shop')

// 商家封面用「分类图标」，商品封面用「商品图标」
const iconSvg = computed(() =>
  isShop.value ? categoryIconMarkup(props.category) : productIconMarkup(props.title),
)

// 商家名首字角标（空名兜底「商」，保证占位区永远有内容）
const badge = computed(() => (isShop.value ? (props.name || '').trim().charAt(0) || '商' : ''))

const alt = computed(() => props.title || props.name || '封面')

function onError() {
  broken.value = true
}
</script>

<style scoped>
.product-cover {
  position: relative;
  display: grid;
  place-items: center;
  width: 100%;
  height: 100%;
  overflow: hidden;
  /* 图标描边色统一由 color 控制（Tabler 原生 stroke="currentColor"） */
  color: #ffffff;
  /* 圆角交给父容器裁切：父容器已是圆角 + overflow:hidden 时，
     这里再叠一个更小的圆角反而会在边缘露出浅色缺口 */
  border-radius: inherit;
  /* 兜底底色：万一渐变未生效也不会留空洞 */
  background: linear-gradient(135deg, var(--green-primary), var(--teal));
}

.pc-img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.5s ease;
}

/* 光晕：白色径向渐变（12% 透明度），给纯色渐变底一点体积感 */
.pc-glow {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: radial-gradient(
    120% 92% at 28% 16%,
    rgba(255, 255, 255, 0.12),
    rgba(255, 255, 255, 0) 62%
  );
}

.pc-icon {
  position: relative;
  display: grid;
  place-items: center;
  width: var(--pc-icon-size, 64px);
  height: var(--pc-icon-size, 64px);
  /* 白色图标压在浅色渐变（如便利店橙）上时，靠投影补足对比度 */
  filter: drop-shadow(0 2px 5px rgba(0, 0, 0, 0.28));
  transition: transform 0.32s ease;
}

/* v-html 注入的 <svg> 不带 scoped 属性，必须用 :deep() 才能命中 */
.pc-icon :deep(svg) {
  display: block;
  width: 100%;
  height: 100%;
}

.pc-shop .pc-icon {
  --pc-icon-size: 36px;
}

.pc-mini .pc-icon {
  --pc-icon-size: 34px;
}

/* 首字角标：白底深字，保证在任意渐变上都可辨识 */
.pc-badge {
  position: absolute;
  right: 5px;
  bottom: 5px;
  display: grid;
  place-items: center;
  min-width: 20px;
  height: 20px;
  padding: 0 5px;
  font-size: 12px;
  font-weight: 800;
  line-height: 1;
  color: #1b3a26;
  background: rgba(255, 255, 255, 0.94);
  border-radius: 999px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.18);
}

@media (prefers-reduced-motion: reduce) {
  .pc-icon,
  .pc-img {
    transition: none;
  }
}
</style>

<!-- ============================================================
     非 scoped：根级主题选择器（html.theme-* / html.mode-elderly）
     在 scoped 下不生效，必须写在这里，并以 .product-cover 前缀隔离。
     本组件被商品网格 / 店铺详情 / 兑换弹窗 / 商家列表四处复用，
     主题覆盖放在组件内可保证四处口径一致、不会各自漂移。
     ============================================================ -->
<style>
/* ---------- 高对比度：渐变一律压成纯黑 + 白图标 + 关光晕 ---------- */
html.theme-high-contrast .product-cover {
  /* 背景色由组件内联 style 提供，必须 !important 才能覆盖 */
  background: #000000 !important;
  background-image: none !important;
}

html.theme-high-contrast .product-cover .pc-glow {
  display: none;
}

html.theme-high-contrast .product-cover .pc-icon {
  color: #ffffff;
  /* 黑底白线本就清晰，去掉投影避免发灰 */
  filter: none;
}

/* 描边略加粗：黑底细线在小尺寸下会"发虚" */
html.theme-high-contrast .product-cover .pc-icon svg {
  stroke-width: 2.6;
}

html.theme-high-contrast .product-cover .pc-badge {
  color: #000000;
  background: #ffffff;
  box-shadow: none;
}

/* ---------- 助老模式：图标放大（容器尺寸由各页面自行放大） ---------- */
html.mode-elderly .product-cover .pc-icon {
  --pc-icon-size: 96px;
}

html.mode-elderly .product-cover.pc-shop .pc-icon {
  --pc-icon-size: 52px;
}

html.mode-elderly .product-cover.pc-mini .pc-icon {
  --pc-icon-size: 46px;
}

html.mode-elderly .product-cover .pc-badge {
  min-width: 26px;
  height: 26px;
  font-size: 16px;
}
</style>
