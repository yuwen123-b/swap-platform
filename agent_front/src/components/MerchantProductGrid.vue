<template>
  <div class="mpg">
    <!-- ===== 加载中：骨架屏（形状贴近真实卡片，切 Tab / 弱网时不闪烁） ===== -->
    <div v-if="state === 'loading'" class="mpg-grid" aria-busy="true">
      <div v-for="n in SKELETON_COUNT" :key="n" class="mpg-card mpg-card-skeleton">
        <div class="mpg-thumb">
          <span class="mpg-sk mpg-sk-thumb" aria-hidden="true"></span>
        </div>
        <div class="mpg-body">
          <span class="mpg-sk mpg-sk-line mpg-sk-line-lg" aria-hidden="true"></span>
          <span class="mpg-sk mpg-sk-line mpg-sk-line-sm" aria-hidden="true"></span>
        </div>
        <div class="mpg-foot">
          <span class="mpg-sk mpg-sk-pill" aria-hidden="true"></span>
        </div>
      </div>
      <p class="mpg-sr-only" role="status">正在加载商家好物…</p>
    </div>

    <!-- ===== 加载失败：给重试入口，不留死胡同 ===== -->
    <div v-else-if="state === 'error'" class="mpg-error">
      <el-alert
        title="商家好物加载失败"
        description="请检查网络后稍后再试。"
        type="warning"
        show-icon
        :closable="false"
      />
      <button type="button" class="mpg-cta" @click="load">重新加载</button>
    </div>

    <!-- ===== 正常态 ===== -->
    <template v-else>
      <div v-if="goods.length" class="mpg-grid">
        <article
          v-for="good in goods"
          :key="`${good.merchantId}-${good.id}`"
          class="mpg-card"
          role="button"
          tabindex="0"
          :aria-label="`${good.title}，${good.shopName}，${good.costText}`"
          @click="toShop(good)"
          @keydown.enter.prevent="toShop(good)"
          @keydown.space.prevent="toShop(good)"
        >
          <div class="mpg-thumb">
            <!-- 封面：有真图显示真图，否则「分类渐变 + 商品语义图标」。
                 与店铺详情页 / 兑换弹窗同口径（都走 ProductCover），
                 保证同一商品在四处看到的画面一致。 -->
            <ProductCover
              :src="good.image"
              :title="good.title"
              :category="good.category"
              variant="product"
            />
          </div>

          <div class="mpg-body">
            <h3 class="mpg-name">{{ good.title }}</h3>
            <p class="mpg-shop">
              <span class="mpg-shop-icon" aria-hidden="true">{{ good.icon }}</span>
              <span class="mpg-shop-name">{{ good.shopName }}</span>
            </p>
          </div>

          <div class="mpg-foot">
            <!-- 免费券不显示「0 积分」，与店铺详情页 costText 同口径 -->
            <span class="mpg-cost" :class="{ free: good.isFree }">{{ good.costText }}</span>
            <span class="mpg-go">去看看 <span aria-hidden="true">→</span></span>
          </div>
        </article>
      </div>

      <!-- 空态 -->
      <div v-else class="mpg-empty">
        <span class="mpg-empty-icon" aria-hidden="true">🛍️</span>
        <p class="mpg-empty-text">暂无商家好物</p>
        <button type="button" class="mpg-cta" @click="router.push('/merchant')">
          去积分商城看看
        </button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import ProductCover from './ProductCover.vue'
import { getMerchantList, getShopProducts } from '../api/merchant'

/* ============================================================
   「探索物品 → 新」Tab：全平台商家好物平铺网格
   ------------------------------------------------------------
   数据来源是**两个接口的 N+1 组合**（一期方案）：
     1) GET /merchant/shops            → 商家列表（含 product_count）
     2) GET /merchant/shops/{id}/products → 每家的上架商品
   后端没有「全平台商品」接口，故一期由前端并发聚合；
   二期若后端提供干净接口，只需替换本文件的 load()。

   三条 N+1 优化（详见《验证清单-探索物品双Tab一期》）：
   - product_count 预过滤：product_count=0 的店直接跳过，不发无效请求
   - 两个接口都带 skipErrorToast：拦截器对未标记的失败请求会弹全局 toast，
     N+1 下某店竞态下架（404）会莫名弹窗，与「部分失败静默降级」冲突
   - Promise.allSettled：任意一家店失败不影响其它店渲染
   ============================================================ */

const router = useRouter()

const SKELETON_COUNT = 8

// 分类 → emoji：只用于卡片正文的「店家」一行做辅助标识
// （2026-10 起封面不再用 emoji —— 改由 ProductCover 的「分类渐变 + 商品语义图标」承担，
//  因为同店同 emoji + 首字大字会让同店商品封面完全重影）
const CATEGORY_ICONS = {
  打印: '🖨️',
  便利店: '🏪',
  理发: '💇',
  回收: '♻️',
  家政: '🧹',
}

function categoryIcon(category) {
  return CATEGORY_ICONS[category] || '🏬'
}

// 'loading' | 'ready' | 'error'
const state = ref('loading')
const goods = ref([])

// 组件卸载后不再写状态（避免迟到响应触发无意义渲染）
let alive = true

function normalizeGood(product, shop) {
  const points = Number(product?.points_cost) || 0
  return {
    id: product.id,
    merchantId: shop.id,
    shopName: shop.name || '未命名商家',
    icon: categoryIcon(shop.category),
    // 分类用于封面渐变（ProductCover 内部取色）；后端商品接口不带自身分类，
    // 由所属店铺携带过来（仅内存字段，不涉及任何数据变更）
    category: shop.category || '',
    title: product.title || '未命名商品',
    image: product.image_url || '',
    isFree: points === 0,
    costText: points === 0 ? '免费' : `${points} 积分`,
  }
}

async function load() {
  if (!alive) return
  state.value = 'loading'
  goods.value = []

  let shops = []
  try {
    const data = await getMerchantList({ page: 1, size: 50 }, { skipErrorToast: true })
    // product_count 预过滤：字段缺失时不预过滤（宁可多发一次请求也不漏店）
    shops = (data?.list || []).filter((shop) => {
      const count = Number(shop?.product_count)
      return !Number.isFinite(count) || count > 0
    })
  } catch {
    if (!alive) return
    // 商家列表本身失败：没有可回退的数据源，直接给错误态 + 重试
    state.value = 'error'
    return
  }

  if (!alive) return
  if (!shops.length) {
    state.value = 'ready'
    return
  }

  const results = await Promise.allSettled(
    shops.map((shop) => getShopProducts(shop.id, { skipErrorToast: true })),
  )

  if (!alive) return

  const flat = []
  let failedShops = 0
  results.forEach((result, index) => {
    if (result.status !== 'fulfilled') {
      failedShops += 1
      return
    }
    const shop = shops[index]
    const list = result.value?.list || []
    list.forEach((product) => flat.push(normalizeGood(product, shop)))
  })

  // 保持「商家 id ASC + 商品 id ASC」的服务端顺序：不重排、不随机
  goods.value = flat
  // 全部商品都失败（而非「真的没有商品」）时给错误态，否则会误报空
  state.value = flat.length === 0 && failedShops > 0 ? 'error' : 'ready'
}

function toShop(good) {
  router.push(`/merchant/${good.merchantId}`)
}

onMounted(load)
onBeforeUnmount(() => {
  alive = false
})
</script>

<style scoped>
/* 局部色板：与 ItemList / MerchantList 同构，
   高对比度主题只需重定义局部变量即可整体可读 */
.mpg {
  --mpg-green: var(--green-primary);
  --mpg-text: var(--text-primary);
  --mpg-text-sub: var(--text-secondary);
  --mpg-card: #ffffff;
  --mpg-border: rgba(76, 175, 80, 0.22);
  --mpg-shadow-hover: 0 16px 34px rgba(46, 125, 50, 0.16);
}

.mpg-sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
  border: 0;
}

/* ---------- 网格：桌面 4 列（与「闲」Tab lg=6 同密度），窄屏 2 列 ---------- */
.mpg-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 18px;
}

/* ---------- 商品卡片：与「闲」Tab 的 .item-card 同款（白底 / 圆角 / 浅绿边 / 悬浮上浮） ---------- */
.mpg-card {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--mpg-border);
  border-radius: 16px;
  background: var(--mpg-card);
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.28s ease, box-shadow 0.28s ease, border-color 0.28s ease;
}

.mpg-card:hover {
  border-color: #4caf50;
  transform: translateY(-6px);
  box-shadow: var(--mpg-shadow-hover);
}

.mpg-card:focus-visible {
  outline: 3px solid var(--mpg-green);
  outline-offset: 2px;
}

.mpg-thumb {
  position: relative;
  display: grid;
  place-items: center;
  height: 160px;
  overflow: hidden;
  background: #f4fbf6;
}

/* 封面内部（真图 / 图标）由 ProductCover 渲染（子组件，需 :deep() 才能命中）：
   真图 hover 轻微放大；图标 hover 轻微放大，与卡片整体上浮叠成层次感 */
.mpg-card:hover :deep(.pc-img) {
  transform: scale(1.06);
}

.mpg-card:hover :deep(.pc-icon) {
  transform: scale(1.1);
}

.mpg-body {
  flex: 1 1 auto;
  padding: 14px 16px 0;
}

.mpg-name {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: #1b3a26;
  /* 标题最多两行，避免长短不一把卡片撑得参差 */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.mpg-shop {
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 8px 0 0;
  font-size: 12.5px;
  color: var(--mpg-text-sub);
}

.mpg-shop-icon {
  font-size: 13px;
}

.mpg-shop-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mpg-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px 16px 16px;
}

/* 积分徽标：与「低价转让」标签同配色体系（暖橙 = 积分） */
.mpg-cost {
  display: inline-flex;
  padding: 3px 10px;
  border-radius: 999px;
  background: #fff8e1;
  color: #b7791f;
  font-size: 12.5px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.mpg-cost.free {
  background: #e0f2f1;
  color: #00695c;
}

.mpg-go {
  flex-shrink: 0;
  font-size: 12.5px;
  font-weight: 700;
  color: var(--mpg-green);
}

/* ---------- 空态 / 错误 ---------- */
.mpg-empty {
  padding: 56px 20px;
  text-align: center;
  background: var(--mpg-card);
  border: 1px dashed rgba(76, 175, 80, 0.4);
  border-radius: 16px;
}

.mpg-empty-icon {
  font-size: 42px;
}

.mpg-empty-text {
  margin: 12px 0 0;
  font-size: 15px;
  font-weight: 600;
  color: #2e7d32;
}

.mpg-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.mpg-cta {
  min-height: 40px;
  padding: 8px 22px;
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  color: var(--mpg-green);
  background: var(--mpg-card);
  border: 1px solid var(--mpg-green);
  border-radius: 999px;
  cursor: pointer;
  transition: color 0.2s ease, background 0.2s ease;
}

.mpg-cta:hover {
  color: #fff;
  background: var(--mpg-green);
}

.mpg-cta:focus-visible {
  outline: 3px solid var(--mpg-green);
  outline-offset: 2px;
}

/* ---------- 骨架屏 ---------- */
.mpg-card-skeleton {
  cursor: default;
}

.mpg-card-skeleton:hover {
  border-color: var(--mpg-border);
  transform: none;
  box-shadow: none;
}

.mpg-sk {
  display: block;
  background: linear-gradient(90deg, #eef4ee 25%, #f7fbf8 37%, #eef4ee 63%);
  background-size: 400% 100%;
  animation: mpg-shimmer 1.4s ease infinite;
  border-radius: 8px;
}

.mpg-sk-thumb {
  width: 100%;
  height: 100%;
  border-radius: 0;
}

.mpg-sk-line {
  height: 14px;
  margin-top: 10px;
}

.mpg-sk-line-lg {
  width: 78%;
}

.mpg-sk-line-sm {
  width: 52%;
  margin-top: 12px;
}

.mpg-sk-pill {
  width: 72px;
  height: 20px;
  border-radius: 999px;
}

@keyframes mpg-shimmer {
  0% {
    background-position: 100% 50%;
  }

  100% {
    background-position: 0 50%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .mpg-sk {
    animation: none;
  }

  .mpg-card {
    transition: none;
  }
}

/* 窄屏 2 列：与「闲」Tab 的 el-col :xs="12" 保持一致 */
@media (max-width: 560px) {
  .mpg-grid {
    gap: 14px;
  }

  .mpg-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .mpg-body {
    padding: 12px 12px 0;
  }

  .mpg-foot {
    padding: 10px 12px 14px;
  }
}
</style>

<!-- ============================================================
     非 scoped：根级主题选择器（html.mode-elderly / html.theme-high-contrast）
     在 scoped 下不生效，必须写在这里，并以 .mpg 前缀隔离。
     ============================================================ -->
<style>
/* ---------- 高对比度：黑底 + 白描边 ---------- */
html.theme-high-contrast .mpg-card {
  background: #000000;
  border-color: #ffffff;
}

html.theme-high-contrast .mpg-thumb {
  background: #000000;
  border-bottom: 1px solid #ffffff;
}

html.theme-high-contrast .mpg-name {
  color: #ffffff;
}

html.theme-high-contrast .mpg-shop {
  color: #f2f2f2;
}

html.theme-high-contrast .mpg-go {
  color: #4ade80;
}

html.theme-high-contrast .mpg-cost {
  background: #000000;
  color: #fbbf24;
  border: 1px solid #fbbf24;
}

html.theme-high-contrast .mpg-cost.free {
  color: #5eead4;
  border-color: #5eead4;
}

html.theme-high-contrast .mpg-empty {
  background: #000000;
  border-color: #4ade80;
}

html.theme-high-contrast .mpg-empty-text {
  color: #4ade80;
}

html.theme-high-contrast .mpg-cta {
  background: #000000;
  color: #4ade80;
  border-color: #4ade80;
}

html.theme-high-contrast .mpg-cta:hover {
  background: #4ade80;
  color: #000000;
}

html.theme-high-contrast .mpg-sk {
  background: #1a1a1a;
  animation: none;
}

/* ---------- 助老模式：字号放大、点击目标 ≥60px、窄屏单列 ---------- */
html.mode-elderly .mpg-grid {
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 20px;
}

html.mode-elderly .mpg-card {
  min-height: 60px;
}

html.mode-elderly .mpg-thumb {
  height: 200px;
}

html.mode-elderly .mpg-name {
  font-size: 20px;
  -webkit-line-clamp: 3;
  line-clamp: 3;
}

html.mode-elderly .mpg-shop,
html.mode-elderly .mpg-go {
  font-size: 17px;
}

html.mode-elderly .mpg-cost {
  padding: 6px 14px;
  font-size: 17px;
}

html.mode-elderly .mpg-foot {
  padding: 14px 16px 18px;
}

html.mode-elderly .mpg-empty-text {
  font-size: 20px;
}

html.mode-elderly .mpg-cta {
  min-height: 60px;
  padding: 12px 26px;
  font-size: 18px;
}
</style>
