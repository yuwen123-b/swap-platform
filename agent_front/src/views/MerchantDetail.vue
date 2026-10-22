<template>
  <section class="page merchant-page merchant-detail-page">
    <!-- 顶部返回栏 -->
    <button type="button" class="back-bar" @click="router.push('/merchant')">
      <span class="back-arrow" aria-hidden="true">←</span>
      <span>返回积分商城</span>
    </button>

    <!-- 店铺不存在 / 未通过审核：给出口，不留死胡同 -->
    <div v-if="loadError" class="green-empty">
      <span class="green-empty-icon" aria-hidden="true">🏚️</span>
      <p class="green-empty-text">商家不存在或暂未开放</p>
      <button type="button" class="empty-cta" @click="router.push('/merchant')">返回积分商城</button>
    </div>

    <template v-else>
      <!-- ===== 店铺信息卡 ===== -->
      <section class="shop-hero">
        <!-- 店铺封面：有真图（logo_url）显示真图，否则「分类渐变 + 分类线性图标 + 商家名首字角标」 -->
        <span class="shop-logo">
          <ProductCover
            :src="merchant.logo_url || ''"
            :name="merchant.name"
            :category="merchant.category"
            variant="shop"
          />
        </span>
        <div class="shop-hero-info">
          <h1 class="shop-name">{{ merchant.name || '未命名商家' }}</h1>
          <p class="shop-meta">
            {{ merchant.category || '社区服务' }} · 在售 {{ list.length }} 项
          </p>
          <p v-if="merchant.contact" class="shop-line">联系电话：{{ merchant.contact }}</p>
          <p v-if="merchant.address" class="shop-line">地址：{{ merchant.address }}</p>
        </div>
      </section>

      <p v-if="merchant.description" class="shop-desc">{{ merchant.description }}</p>

      <!-- ===== 可兑换商品 ===== -->
      <h2 class="card-title">可兑换商品</h2>

      <div v-loading="loading" class="product-area">
        <div v-if="list.length" class="product-list">
          <article v-for="product in list" :key="product.id" class="product-card">
            <!-- 商品封面：与「新」Tab / 兑换弹窗同口径（分类渐变 + 商品语义图标）。
                 同店的「打印券10张」与「复印券20张」靠图标一眼可区分，
                 不再出现「首字相同 + 同 emoji」的重影。 -->
            <span class="product-thumb">
              <ProductCover
                :src="product.image_url || ''"
                :title="product.title"
                :category="merchant.category"
                variant="mini"
              />
            </span>

            <div class="product-main">
              <h3 class="product-title">{{ product.title || '未命名商品' }}</h3>
              <p v-if="product.description" class="product-desc">{{ product.description }}</p>
              <p class="product-stock">
                剩余 {{ product.stock ?? 0 }} 份 · 已兑换 {{ product.sold_count ?? 0 }} 次
              </p>
            </div>

            <div class="product-right">
              <!-- 免费券不显示「0 积分」 -->
              <span class="product-cost" :class="{ free: isFree(product) }">
                {{ costText(product) }}
              </span>
              <el-button
                type="primary"
                :disabled="isSoldOut(product)"
                @click="openRedeem(product)"
              >
                {{ buttonText(product) }}
              </el-button>
            </div>
          </article>
        </div>

        <div v-else-if="!loading" class="green-empty">
          <span class="green-empty-icon" aria-hidden="true">🌿</span>
          <p class="green-empty-text">该商家暂未上架商品</p>
          <button type="button" class="empty-cta" @click="router.push('/merchant')">
            看看其他商家
          </button>
        </div>
      </div>
    </template>

    <!-- ===== 兑换确认弹窗（成功后由父页面拉起核销码） ===== -->
    <RedeemConfirmDialog
      v-model="confirmVisible"
      :product="activeProduct"
      :merchant-name="merchant.name || ''"
      :category="merchant.category || ''"
      :balance="profileStore.points"
      @success="onRedeemed"
    />

    <!-- ===== 核销码弹窗 ===== -->
    <RedeemCodeDialog
      v-model="codeVisible"
      :code="result?.code"
      :product-title="result?.product_title"
      :merchant-name="result?.merchant_name || merchant.name || ''"
      :expires-at="result?.expires_at"
      :status="1"
      show-list-button
      @view-list="router.push('/profile/redemptions')"
    />
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ProductCover from '../components/ProductCover.vue'
import RedeemConfirmDialog from '../components/RedeemConfirmDialog.vue'
import RedeemCodeDialog from '../components/RedeemCodeDialog.vue'
import { getShopProducts } from '../api/merchant'
import { useUserStore } from '../store/user'
import { useProfileStore } from '../store/profile'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const profileStore = useProfileStore()

// 封面视觉（分类渐变 + 分类图标 + 商品图标）统一由 ProductCover 承担，
// 本页不再自持 emoji 映射（旧实现用「首字 + 店铺 emoji」，同店商品会重影）

const loading = ref(false)
const loadError = ref(false)
const merchant = ref({})
const list = ref([])

async function loadShop() {
  const id = Number(route.params.id)
  if (!Number.isFinite(id) || id <= 0) {
    loadError.value = true
    return
  }
  loading.value = true
  loadError.value = false
  try {
    // ⚠ 返回 { merchant, list }，不是数组
    const data = await getShopProducts(id)
    merchant.value = data?.merchant || {}
    list.value = data?.list || []
  } catch {
    // 404「商家不存在或暂未开放」等由拦截器提示，这里给出页面级出口
    loadError.value = true
    merchant.value = {}
    list.value = []
  } finally {
    loading.value = false
  }
}

/* ---------- 商品卡片文案 ---------- */
function isFree(product) {
  return Number(product?.points_cost) === 0
}

function isSoldOut(product) {
  const stock = Number(product?.stock)
  return Number.isFinite(stock) && stock <= 0
}

// 免费券显示「免费」而非「0 积分」
function costText(product) {
  return isFree(product) ? '免费' : `${Number(product.points_cost) || 0} 积分`
}

function buttonText(product) {
  if (isSoldOut(product)) return '已兑完'
  return isFree(product) ? '免费领取' : '立即兑换'
}

/* ---------- 兑换流程 ---------- */
const confirmVisible = ref(false)
const codeVisible = ref(false)
const activeProduct = ref(null)
const result = ref(null)

function openRedeem(product) {
  if (isSoldOut(product)) return
  // 商家列表/商品均免登录可浏览，只有兑换这一步要登录
  if (!userStore.isLoggedIn) {
    router.push({ path: '/login', query: { redirect: route.fullPath } })
    return
  }
  activeProduct.value = product
  confirmVisible.value = true
}

function onRedeemed(payload) {
  result.value = payload || null

  // 余额以后端返回的 points_balance 为准（免费券该字段为 null，余额不变）
  const balance = payload?.points_balance
  if (balance !== null && balance !== undefined) {
    profileStore.setPoints(balance)
  } else {
    profileStore.deductPoints(activeProduct.value?.points_cost)
  }

  // 局部更新：核销接口会扣库存与加销量，先本地反映，避免整页重拉
  const target = list.value.find((item) => item.id === activeProduct.value?.id)
  if (target) {
    target.stock = Math.max(Number(target.stock || 0) - 1, 0)
    target.sold_count = Number(target.sold_count || 0) + 1
  }

  codeVisible.value = true
}

onMounted(loadShop)
</script>

<style scoped>
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

/* ---------- 返回栏 ---------- */
.back-bar {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  margin: 0 0 12px -12px;
  font: inherit;
  font-size: 14px;
  color: var(--pc-text-sub);
  background: transparent;
  border: none;
  border-radius: 10px;
  cursor: pointer;
  transition: color 0.2s ease, background 0.2s ease;
}

.back-bar:hover {
  color: var(--pc-green);
  background: var(--green-softer);
}

.back-bar:focus-visible {
  outline: 3px solid var(--pc-green);
  outline-offset: 2px;
}

.back-arrow {
  font-size: 16px;
  line-height: 1;
}

/* ---------- 店铺信息卡 ---------- */
.shop-hero {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 20px;
  background: var(--pc-card);
  border: 1px solid var(--pc-border);
  border-radius: 16px;
  box-shadow: var(--pc-shadow);
}

/* 封面容器：只负责尺寸与裁切，画面交给 ProductCover（真图优先，否则分类渐变 + 图标） */
.shop-logo {
  display: block;
  flex-shrink: 0;
  width: 72px;
  height: 72px;
  overflow: hidden;
  border: 1px solid var(--pc-border);
  border-radius: 16px;
}

.shop-hero-info {
  min-width: 0;
}

.shop-name {
  margin: 0;
  font-size: clamp(20px, 3vw, 26px);
  font-weight: 700;
  letter-spacing: -0.3px;
  color: var(--pc-text);
  word-break: break-all;
}

.shop-meta {
  margin: 6px 0 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--green-primary);
}

.shop-line {
  margin: 4px 0 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--pc-text-sub);
  word-break: break-all;
}

.shop-desc {
  margin: 16px 0 0;
  font-size: 14px;
  line-height: 1.85;
  color: var(--pc-text-sub);
}

/* ---------- 区块标题 ---------- */
.card-title {
  position: relative;
  margin: 26px 0 16px;
  padding-left: 12px;
  font-size: 16px;
  font-weight: 700;
  color: var(--pc-text);
}

.card-title::before {
  content: "";
  position: absolute;
  left: 0;
  top: 50%;
  width: 4px;
  height: 16px;
  border-radius: 2px;
  background: var(--pc-green);
  transform: translateY(-50%);
}

/* ---------- 商品卡片 ---------- */
.product-area {
  min-height: 100px;
}

.product-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.product-card {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  padding: 18px;
  background: var(--pc-card);
  border: 1px solid var(--pc-border);
  border-radius: 16px;
  box-shadow: var(--pc-shadow);
  transition: box-shadow 0.2s ease, border-color 0.2s ease;
}

.product-card:hover {
  border-color: rgba(47, 133, 90, 0.34);
  box-shadow: var(--pc-shadow-hover);
}

/* 商品封面容器：同上，画面交给 ProductCover */
.product-thumb {
  display: block;
  flex-shrink: 0;
  width: 64px;
  height: 64px;
  overflow: hidden;
  border: 1px solid var(--pc-border);
  border-radius: 14px;
}

.product-main {
  flex: 1 1 200px;
  min-width: 0;
}

.product-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--pc-text);
  word-break: break-all;
}

.product-desc {
  margin: 6px 0 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--pc-text-sub);
  /* 描述最多两行，避免长短不一把卡片撑得参差 */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.product-stock {
  margin: 6px 0 0;
  font-size: 12.5px;
  color: var(--pc-text-sub);
}

.product-right {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-shrink: 0;
  margin-left: auto;
}

.product-cost {
  font-size: 17px;
  font-weight: 800;
  color: var(--green-primary);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

/* 免费券：不用绿色强调「价格」，改用暖色，避免和「50 积分」混淆 */
.product-cost.free {
  padding: 3px 12px;
  font-size: 14px;
  color: var(--peach-deep, #b7791f);
  background: var(--peach-soft, #fef3c7);
  border-radius: 999px;
}

/* ---------- 空态 ---------- */
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
  margin: 12px 0 8px;
  font-size: 15px;
  font-weight: 600;
  color: #2e7d32;
}

.empty-cta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 40px;
  padding: 8px 20px;
  margin-top: 4px;
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  color: var(--pc-text);
  background: var(--pc-card);
  border: 1px solid var(--pc-border);
  border-radius: 999px;
  cursor: pointer;
  transition: color 0.2s ease, border-color 0.2s ease;
}

.empty-cta:hover {
  color: var(--pc-green);
  border-color: var(--pc-green);
}

.empty-cta:focus-visible {
  outline: 3px solid var(--pc-green);
  outline-offset: 2px;
}

/* ---------- 窄屏：价格与按钮换行到第二行 ---------- */
@media (max-width: 620px) {
  .product-right {
    width: 100%;
    margin-left: 0;
    justify-content: space-between;
  }
}
</style>

<style>
/* 高对比度 */
html.theme-high-contrast .merchant-page {
  --pc-card: #000000;
  --pc-bg: #000000;
  --pc-border: #ffffff;
  --pc-shadow: none;
  --pc-shadow-hover: none;
}

html.theme-high-contrast .merchant-page .shop-logo,
html.theme-high-contrast .merchant-page .product-thumb {
  border-color: #ffffff;
}

html.theme-high-contrast .merchant-page .shop-meta,
html.theme-high-contrast .merchant-page .product-cost {
  color: #4ade80;
}

html.theme-high-contrast .merchant-page .product-cost.free {
  color: #000000;
  background: #fde68a;
}

html.theme-high-contrast .merchant-page .green-empty {
  border-color: #4ade80;
}

html.theme-high-contrast .merchant-page .green-empty-text {
  color: #4ade80;
}

/* 助老模式：字号与点击目标放大 */
html.mode-elderly .merchant-page .back-bar {
  font-size: 18px;
  min-height: 60px;
}

html.mode-elderly .merchant-page .shop-hero {
  padding: 24px;
  gap: 22px;
}

html.mode-elderly .merchant-page .shop-name {
  font-size: 28px;
}

html.mode-elderly .merchant-page .shop-logo {
  width: 88px;
  height: 88px;
}

html.mode-elderly .merchant-page .shop-meta,
html.mode-elderly .merchant-page .shop-line,
html.mode-elderly .merchant-page .shop-desc,
html.mode-elderly .merchant-page .product-stock {
  font-size: 18px;
}

html.mode-elderly .merchant-page .card-title {
  font-size: 22px;
}

html.mode-elderly .merchant-page .product-card {
  padding: 22px;
  gap: 20px;
}

html.mode-elderly .merchant-page .product-thumb {
  width: 80px;
  height: 80px;
}

html.mode-elderly .merchant-page .product-title {
  font-size: 22px;
}

html.mode-elderly .merchant-page .product-desc {
  font-size: 18px;
  -webkit-line-clamp: 3;
  line-clamp: 3;
}

html.mode-elderly .merchant-page .product-cost,
html.mode-elderly .merchant-page .product-cost.free {
  font-size: 20px;
}

html.mode-elderly .merchant-page .el-button,
html.mode-elderly .merchant-page .empty-cta {
  min-height: 60px;
  padding: 12px 26px;
  font-size: 18px;
}
</style>
