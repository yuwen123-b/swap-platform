<template>
  <section class="page merchant-page">
    <div class="heading-row">
      <div>
        <div class="eyebrow">社区服务</div>
        <h1 class="page-title">
          积分<span class="gradient-text">商城</span>
        </h1>
        <p class="lead">用你的碳积分兑换社区服务</p>
      </div>
    </div>

    <!-- ===== 积分条：登录后显示余额，未登录引导登录 ===== -->
    <div class="points-bar">
      <template v-if="isLoggedIn">
        <span class="points-num">
          {{ pointsDisplay }}<span class="points-unit">分</span>
        </span>
        <span class="points-label">当前积分</span>
        <button type="button" class="points-action" @click="router.push('/profile/carbon')">
          积分明细
        </button>
      </template>
      <template v-else>
        <span class="points-guest">登录后可查看积分并兑换社区服务</span>
        <button type="button" class="points-action" @click="goLogin">去登录</button>
      </template>
    </div>

    <!-- ===== 分类筛选：常量值取自真实库 merchant.category 的实际取值 ===== -->
    <div class="shop-filters" role="tablist" aria-label="按类型筛选商家">
      <button
        v-for="item in CATEGORY_FILTERS"
        :key="item.value || 'all'"
        type="button"
        role="tab"
        class="filter-chip"
        :class="{ active: activeCategory === item.value }"
        :aria-selected="activeCategory === item.value"
        @click="switchCategory(item.value)"
      >
        {{ item.label }}
      </button>
    </div>

    <!-- ===== 商家列表 ===== -->
    <div v-loading="loading" class="shop-area">
      <div v-if="shops.length" class="shop-list">
        <button
          v-for="shop in shops"
          :key="shop.id"
          type="button"
          class="shop-card"
          @click="toShop(shop)"
        >
          <!-- 商家封面：有真图（logo_url）显示真图，否则「分类渐变 + 分类线性图标 + 商家名首字角标」。
               图标为主视觉（分类一眼可辨），首字退为右下角小角标。 -->
          <span class="shop-logo">
            <ProductCover
              :src="shop.logo_url || ''"
              :name="shop.name"
              :category="shop.category"
              variant="shop"
            />
          </span>
          <span class="shop-main">
            <span class="shop-name">{{ shop.name || '未命名商家' }}</span>
            <span class="shop-sub">
              {{ shop.category || '社区服务' }} · 在售 {{ shop.product_count || 0 }} 项
            </span>
            <span class="shop-addr">{{ shop.address || '地址未填写' }}</span>
          </span>
          <span class="shop-go">
            查看
            <span aria-hidden="true">→</span>
          </span>
        </button>
      </div>

      <!-- 空态 -->
      <div v-else-if="!loading && !loadError" class="green-empty">
        <span class="green-empty-icon" aria-hidden="true">🌿</span>
        <p class="green-empty-text">{{ emptyText }}</p>
      </div>

      <!-- 加载失败：保留筛选条件，提示重试 -->
      <el-alert
        v-if="loadError && !loading"
        class="load-error"
        title="商家列表加载失败"
        description="请检查网络后稍后再试，或切换其他类型。"
        type="warning"
        show-icon
        :closable="false"
      />
    </div>

    <!-- ===== 商家入口：导航保持 8 项不动，入驻入口放在页尾 ===== -->
    <button type="button" class="merchant-entry" @click="router.push('/merchant/apply')">
      <span class="entry-main">
        <span class="entry-title">我是商家，我要入驻</span>
        <span class="entry-sub">开店上架服务，让邻居用积分来兑换</span>
      </span>
      <span class="entry-go" aria-hidden="true">→</span>
    </button>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import ProductCover from '../components/ProductCover.vue'
import { getMerchantList } from '../api/merchant'
import { useUserStore } from '../store/user'
import { useProfileStore } from '../store/profile'

const router = useRouter()
const userStore = useUserStore()
const profileStore = useProfileStore()

const isLoggedIn = computed(() => userStore.isLoggedIn)
// 余额只读自 store（数据源 GET /user/profile 的 points），本页不做本地记账
const pointsDisplay = computed(() => profileStore.points)

/* ============================================================
   分类筛选
   值取自真实库 merchant 表 status=1 的 category 实际取值（5 类）：
   打印 / 便利店 / 理发 / 回收 / 家政
   ⚠ 后端 /shops 的 category 是**精确匹配**，必须传完整中文名；
     后端没有分类枚举接口，故此处用常量。新增第 6 类时该类仍会在
     「全部」里出现，只是没有专属 chip。
   ============================================================ */
const CATEGORY_FILTERS = [
  { label: '全部', value: null },
  { label: '打印', value: '打印' },
  { label: '便利店', value: '便利店' },
  { label: '理发', value: '理发' },
  { label: '回收', value: '回收' },
  { label: '家政', value: '家政' },
]

// 封面视觉（分类渐变 + 分类线性图标 + 商家名首字角标）统一由 ProductCover 承担，
// 本页不再自持 emoji 映射：emoji 在跨系统渲染下字形差异大，且「首字大字」与
// 商品封面风格不统一；改用与商品封面同一套的「分类色 + 线性图标」语言。

const activeCategory = ref(null)
const shops = ref([])
const loading = ref(false)
const loadError = ref(false)

const emptyText = computed(() =>
  activeCategory.value ? `暂无「${activeCategory.value}」类型的商家，敬请期待` : '暂无商家，敬请期待',
)

async function loadShops() {
  loading.value = true
  loadError.value = false
  try {
    const params = { page: 1, size: 50 }
    if (activeCategory.value) params.category = activeCategory.value
    const data = await getMerchantList(params)
    shops.value = data?.list || []
  } catch {
    // 错误提示由请求拦截器统一处理
    shops.value = []
    loadError.value = true
  } finally {
    loading.value = false
  }
}

function switchCategory(value) {
  if (activeCategory.value === value) return
  activeCategory.value = value
  loadShops()
}

function toShop(shop) {
  router.push(`/merchant/${shop.id}`)
}

// 商家列表免登录可浏览，仅兑换需要登录
function goLogin() {
  router.push({ path: '/login', query: { redirect: '/merchant' } })
}

onMounted(() => {
  loadShops()
  // 刷新余额：MainLayout 的 hydrate 已拉过一次档案，
  // 但用户可能刚兑换完再进来，这里以服务端最新值兜底。
  if (isLoggedIn.value) profileStore.fetchPoints().catch(() => {})
})
</script>

<style scoped>
/* 局部色板：与 ProfileSubLayout / Profile.vue 同构，
   高对比度主题只需重定义这几个局部变量即可整体可读 */
.merchant-page {
  max-width: 820px;
  --pc-green: var(--green-primary);
  --pc-text: var(--text-primary);
  --pc-text-sub: var(--text-secondary);
  --pc-bg: #f7f8f7;
  --pc-card: #ffffff;
  --pc-border: #e5e7eb;
  --pc-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  --pc-shadow-hover: 0 4px 16px rgba(0, 0, 0, 0.08);
}

.heading-row {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
}

/* ---------- 积分条 ---------- */
.points-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 22px;
  padding: 16px 18px;
  background: linear-gradient(135deg, var(--green-soft), var(--teal-soft));
  border: 1px solid var(--green-soft);
  border-radius: 16px;
}

.points-num {
  font-size: 30px;
  font-weight: 800;
  line-height: 1.1;
  color: var(--green-active);
  font-variant-numeric: tabular-nums;
}

.points-unit {
  margin-left: 2px;
  font-size: 15px;
  font-weight: 600;
}

.points-label {
  flex: 1 1 auto;
  font-size: 14px;
  font-weight: 600;
  color: var(--green-active);
}

.points-guest {
  flex: 1 1 200px;
  font-size: 14px;
  font-weight: 600;
  color: var(--green-active);
}

.points-action {
  flex-shrink: 0;
  min-height: 34px;
  padding: 6px 16px;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  color: var(--pc-text);
  background: var(--pc-card);
  border: 1px solid var(--pc-border);
  border-radius: 999px;
  cursor: pointer;
  transition: color 0.2s ease, border-color 0.2s ease, background 0.2s ease;
}

.points-action:hover {
  color: var(--pc-green);
  border-color: var(--pc-green);
}

.points-action:focus-visible {
  outline: 3px solid var(--pc-green);
  outline-offset: 2px;
}

/* ---------- 分类 chips ---------- */
.shop-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 22px 0 18px;
}

.filter-chip {
  min-height: 36px;
  padding: 7px 18px;
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  color: var(--pc-text-sub);
  background: var(--pc-card);
  border: 1px solid var(--pc-border);
  border-radius: 999px;
  cursor: pointer;
  transition: color 0.2s ease, border-color 0.2s ease, background 0.2s ease;
}

.filter-chip:hover {
  color: var(--pc-green);
  border-color: var(--pc-green);
}

.filter-chip.active {
  color: #fff;
  background: var(--pc-green);
  border-color: var(--pc-green);
}

.filter-chip:focus-visible {
  outline: 3px solid var(--pc-green);
  outline-offset: 2px;
}

/* ---------- 商家卡片 ---------- */
.shop-area {
  min-height: 120px;
}

.shop-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.shop-card {
  display: flex;
  align-items: center;
  gap: 16px;
  width: 100%;
  padding: 18px;
  font: inherit;
  text-align: left;
  color: inherit;
  background: var(--pc-card);
  border: 1px solid var(--pc-border);
  border-radius: 16px;
  box-shadow: var(--pc-shadow);
  cursor: pointer;
  transition: box-shadow 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
}

.shop-card:hover {
  border-color: rgba(47, 133, 90, 0.34);
  box-shadow: var(--pc-shadow-hover);
  transform: translateY(-2px);
}

/* hover 反馈：图标轻微放大（子组件内元素，需 :deep() 才能命中） */
.shop-card:hover :deep(.pc-icon) {
  transform: scale(1.08);
}

.shop-card:focus-visible {
  outline: 3px solid var(--pc-green);
  outline-offset: 2px;
}

/* 封面容器：只负责尺寸与裁切，画面内容全部交给 ProductCover
   （有真图显示真图，无图/裂图显示分类渐变 + 分类图标 + 首字角标）。
   高对比度下靠 1px 描边保证不隐形。 */
.shop-logo {
  display: block;
  flex-shrink: 0;
  width: 64px;
  height: 64px;
  overflow: hidden;
  border: 1px solid var(--pc-border);
  border-radius: 14px;
}

.shop-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1 1 auto;
  min-width: 0;
}

.shop-name {
  font-size: 17px;
  font-weight: 700;
  color: var(--pc-text);
  word-break: break-all;
}

.shop-sub {
  font-size: 14px;
  font-weight: 600;
  color: var(--green-primary);
}

.shop-addr {
  font-size: 13px;
  color: var(--pc-text-sub);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.shop-go {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  font-size: 14px;
  font-weight: 700;
  color: var(--pc-green);
}

/* ---------- 空态与错误 ---------- */
.green-empty {
  padding: 56px 20px;
  text-align: center;
  background: var(--pc-card);
  border: 1px dashed rgba(76, 175, 80, 0.4);
  border-radius: 16px;
}

.green-empty-icon {
  font-size: 42px;
}

.green-empty-text {
  margin: 12px 0 0;
  font-size: 15px;
  font-weight: 600;
  color: #2e7d32;
}

.load-error {
  margin-top: 4px;
}

/* ---------- 商家入驻入口（页尾） ---------- */
.merchant-entry {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  width: 100%;
  margin-top: 26px;
  padding: 16px 18px;
  font: inherit;
  text-align: left;
  color: inherit;
  background: var(--pc-card);
  border: 1px dashed var(--pc-border);
  border-radius: 16px;
  cursor: pointer;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.merchant-entry:hover {
  border-color: var(--pc-green);
  box-shadow: var(--pc-shadow);
}

.merchant-entry:focus-visible {
  outline: 3px solid var(--pc-green);
  outline-offset: 2px;
}

.entry-main {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.entry-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--pc-text);
}

.entry-sub {
  font-size: 13px;
  color: var(--pc-text-sub);
}

.entry-go {
  flex-shrink: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--pc-green);
}

/* ============================================================
   移动端（≤767px）：商家卡片保持横向（纵向会浪费一屏），
   只压缩封面与内边距，把横向空间还给店名/地址。
   375px 下：343 - 28(padding) - 52(封面) - 12(gap) = 251px 留给文字。
   ============================================================ */
@media (max-width: 767px) {
  .points-bar {
    margin-top: 16px;
    padding: 12px 14px;
    gap: 10px;
  }

  .points-num {
    font-size: 26px;
  }

  .shop-filters {
    margin: 16px 0 14px;
    /* 类型筛选在手机上一行放不下：横向滚动，别换行把首屏顶掉 */
    flex-wrap: nowrap;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    padding-bottom: 2px;
    /* 滚动条会压在筛选贴片上很难看；可滚性由"最后一个 chip 被截断"暗示 */
    scrollbar-width: none;
  }

  .shop-filters::-webkit-scrollbar {
    display: none;
  }

  .filter-chip {
    flex-shrink: 0;
    min-height: 34px;
    padding: 6px 14px;
  }

  .shop-list {
    gap: 10px;
  }

  .shop-card {
    padding: 14px;
    gap: 12px;
  }

  /* 触屏无 hover：去掉上浮，避免点击瞬间卡片位移 */
  .shop-card:hover {
    transform: none;
  }

  .shop-logo {
    width: 52px;
    height: 52px;
    border-radius: 12px;
  }

  .shop-card:active {
    border-color: rgba(47, 133, 90, 0.34);
  }
}
</style>

<!-- ============================================================
     非 scoped：根级主题选择器（html.theme-* / html.mode-elderly）
     在 scoped 下不生效，必须写在这里，并以 .merchant-page 前缀隔离。
     ============================================================ -->
<style>
/* 高对比度：局部色板改为纯黑 + 白描边 */
html.theme-high-contrast .merchant-page {
  --pc-card: #000000;
  --pc-bg: #000000;
  --pc-border: #ffffff;
  --pc-shadow: none;
  --pc-shadow-hover: none;
}

html.theme-high-contrast .merchant-page .points-bar {
  background: #000000;
  border-color: #4ade80;
}

html.theme-high-contrast .merchant-page .points-num,
html.theme-high-contrast .merchant-page .points-label,
html.theme-high-contrast .merchant-page .points-guest {
  color: #4ade80;
}

html.theme-high-contrast .merchant-page .shop-logo {
  border-color: #ffffff;
}

/* 选中态在白底主题是绿底白字，黑底主题下改为浅绿底黑字保证对比度 */
html.theme-high-contrast .merchant-page .filter-chip.active {
  color: #000000;
  background: #4ade80;
  border-color: #4ade80;
}

html.theme-high-contrast .merchant-page .shop-go {
  color: #4ade80;
}

html.theme-high-contrast .merchant-page .shop-sub {
  color: #4ade80;
}

html.theme-high-contrast .merchant-page .green-empty {
  border-color: #4ade80;
}

html.theme-high-contrast .merchant-page .green-empty-text {
  color: #4ade80;
}

html.theme-high-contrast .merchant-page .merchant-entry {
  border-color: #ffffff;
}

html.theme-high-contrast .merchant-page .entry-go {
  color: #4ade80;
}

html.mode-elderly .merchant-page .merchant-entry {
  min-height: 60px;
  padding: 18px 20px;
}

html.mode-elderly .merchant-page .entry-title {
  font-size: 20px;
}

html.mode-elderly .merchant-page .entry-sub,
html.mode-elderly .merchant-page .entry-go {
  font-size: 18px;
}

/* 助老模式：字号放大、点击目标 ≥60px */
html.mode-elderly .merchant-page .page-title {
  font-size: clamp(40px, 5.2vw, 64px);
}

html.mode-elderly .merchant-page .lead,
html.mode-elderly .merchant-page .points-label,
html.mode-elderly .merchant-page .points-guest {
  font-size: 18px;
}

html.mode-elderly .merchant-page .points-num {
  font-size: 38px;
}

html.mode-elderly .merchant-page .filter-chip {
  min-height: 60px;
  padding: 12px 24px;
  font-size: 18px;
}

html.mode-elderly .merchant-page .points-action,
html.mode-elderly .merchant-page .el-button {
  min-height: 60px;
  padding: 12px 24px;
  font-size: 18px;
}

html.mode-elderly .merchant-page .shop-card {
  min-height: 96px;
  padding: 20px;
  gap: 20px;
}

html.mode-elderly .merchant-page .shop-logo {
  width: 80px;
  height: 80px;
}

html.mode-elderly .merchant-page .shop-name {
  font-size: 22px;
}

html.mode-elderly .merchant-page .shop-sub,
html.mode-elderly .merchant-page .shop-go {
  font-size: 18px;
}

html.mode-elderly .merchant-page .shop-addr,
html.mode-elderly .merchant-page .green-empty-text {
  font-size: 18px;
  white-space: normal;
}
</style>
