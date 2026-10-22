<template>
  <ProfileSubLayout
    title="我的兑换"
    desc="凭核销码到店使用；过期未核销，积分会自动退还"
  >
    <section class="profile-card">
      <div class="card-head">
        <h2 class="card-title">兑换记录</h2>
        <button type="button" class="more-link" :disabled="loading" @click="load">
          {{ loading ? '刷新中…' : '刷新' }}
        </button>
      </div>

      <!-- Tab：全部 / 待核销 / 已核销 / 已过期
           （后端还有 status=4 已取消，但没有用户侧取消接口，故不做 Tab） -->
      <div class="tabs" role="tablist" aria-label="按状态筛选我的兑换">
        <button
          v-for="tab in TABS"
          :key="String(tab.key)"
          type="button"
          role="tab"
          class="tab"
          :class="{ active: activeTab === tab.key }"
          :aria-selected="activeTab === tab.key"
          @click="switchTab(tab.key)"
        >
          {{ tab.label }}
        </button>
      </div>

      <p v-if="loading && !items.length" class="empty-text">加载中…</p>

      <template v-else-if="items.length">
        <!-- 整行可点：放大展示核销码 -->
        <button
          v-for="item in items"
          :key="item.id"
          type="button"
          class="redeem-row"
          @click="openCode(item)"
        >
          <span class="row-thumb" aria-hidden="true">{{ thumbIcon }}</span>

          <span class="row-info">
            <span class="row-title">{{ item.product_title || '未命名商品' }}</span>
            <span class="row-merchant">{{ item.merchant_name || '商家已下线' }}</span>
            <span class="row-code">
              核销码 <strong>{{ prettyCode(item.code) }}</strong>
            </span>
            <span class="row-time">{{ timeLine(item) }}</span>
          </span>

          <span class="status-tag" :class="statusClass(item.status)">
            {{ item.status_label }}
          </span>
        </button>

        <div v-if="total > size" class="pager">
          <el-pagination
            layout="prev, pager, next"
            background
            :total="total"
            :page-size="size"
            :current-page="page"
            @current-change="onPageChange"
          />
        </div>
      </template>

      <template v-else>
        <p class="empty-text">{{ emptyText }}</p>
        <!-- 空态出口：避免死胡同 -->
        <button type="button" class="empty-cta" @click="router.push('/merchant')">
          去积分商城看看
        </button>
      </template>
    </section>

    <!-- 核销码放大展示（与兑换成功后的弹窗同一个组件） -->
    <RedeemCodeDialog
      v-model="codeVisible"
      :code="active?.code"
      :product-title="active?.product_title"
      :merchant-name="active?.merchant_name"
      :expires-at="active?.expires_at"
      :redeemed-at="active?.redeemed_at"
      :status="active?.status"
    />
  </ProfileSubLayout>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import ProfileSubLayout from '../../layouts/ProfileSubLayout.vue'
import RedeemCodeDialog from '../../components/RedeemCodeDialog.vue'
import { getMyRedemptions } from '../../api/merchant'

const router = useRouter()

const PAGE_SIZE = 10

// status 与后端枚举一致：1 待核销 / 2 已核销 / 3 已过期
const TABS = [
  { key: 'all', label: '全部', status: null },
  { key: 1, label: '待核销', status: 1 },
  { key: 2, label: '已核销', status: 2 },
  { key: 3, label: '已过期', status: 3 },
]

const EMPTY_TEXT = {
  all: '还没有兑换记录，去积分商城看看',
  1: '没有待核销的兑换码',
  2: '还没有已核销的记录',
  3: '没有已过期的兑换码',
}

/* ============================================================
   状态类名：**第三套** rs-*（语义命名，非数字）
   Profile.vue 已有 s-*（物品/需求）与 os-*（交换单）两套数字类名，
   兑换单的枚举与它们不同（1 待核销 / 2 已核销 / 3 已过期），
   复用 s-* 会把「已核销」显示成灰色、「已过期」显示成红色，语义反向。
   ============================================================ */
const STATUS_CLASS = {
  1: 'rs-pending',
  2: 'rs-redeemed',
  3: 'rs-expired',
  4: 'rs-cancelled',
}

function statusClass(status) {
  return STATUS_CLASS[Number(status)] || 'rs-cancelled'
}

// 分类 emoji 占位（商品 image_url 在库里为 NULL，兑换接口也不回图）
const thumbIcon = '🎟️'

const activeTab = ref('all')
const items = ref([])
const total = ref(0)
const page = ref(1)
const size = ref(PAGE_SIZE)
const loading = ref(false)

const codeVisible = ref(false)
const active = ref(null)

const emptyText = computed(() => EMPTY_TEXT[activeTab.value] ?? EMPTY_TEXT.all)

async function load() {
  loading.value = true
  try {
    const tab = TABS.find((item) => item.key === activeTab.value) || TABS[0]
    const params = { page: page.value, size: size.value }
    if (tab.status !== null) params.status = tab.status
    const data = await getMyRedemptions(params)
    items.value = data?.list || []
    total.value = data?.total || 0
    size.value = data?.size || PAGE_SIZE
  } catch {
    // 错误提示由请求拦截器统一处理
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function switchTab(key) {
  if (activeTab.value === key) return
  activeTab.value = key
  page.value = 1
  items.value = []
  load()
}

function onPageChange(next) {
  page.value = next
  load()
}

function openCode(item) {
  active.value = item
  codeVisible.value = true
}

/* ---------- 展示工具 ---------- */
// 6 位核销码按 3+3 分组展示；全程按字符串处理，防止前导 0 丢失
function prettyCode(code) {
  const s = String(code ?? '').replace(/\s+/g, '')
  if (!s) return '——'
  if (s.length === 6) return `${s.slice(0, 3)} ${s.slice(3)}`
  const mid = Math.ceil(s.length / 2)
  return `${s.slice(0, mid)} ${s.slice(mid)}`
}

function toDate(value) {
  if (!value) return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d
}

function formatDate(value) {
  const d = toDate(value)
  return d ? d.toLocaleDateString('zh-CN') : ''
}

function formatDateTime(value) {
  const d = toDate(value)
  if (!d) return ''
  return `${d.toLocaleDateString('zh-CN')} ${d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
}

// 按状态给出一句「时间」：有效期 / 核销时间 / 过期时间
function timeLine(item) {
  const status = Number(item?.status)
  if (status === 2) return item.redeemed_at ? `核销于 ${formatDateTime(item.redeemed_at)}` : '已核销'
  if (status === 3) return item.expires_at ? `已于 ${formatDate(item.expires_at)} 过期` : '已过期'
  if (status === 4) return '已取消'
  return item.expires_at ? `有效期至 ${formatDate(item.expires_at)}` : '有效期未知'
}

onMounted(load)
</script>

<style scoped>
/* ---------- 卡片头（与 FavoritesView 同款） ---------- */
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.more-link {
  flex-shrink: 0;
  padding: 4px 8px;
  font: inherit;
  font-size: 13px;
  color: var(--pc-text-sub);
  background: none;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: color 0.2s ease, background 0.2s ease;
}

.more-link:hover:not(:disabled) {
  color: var(--pc-green);
  background: var(--pc-bg);
}

.more-link:disabled {
  cursor: default;
  opacity: 0.6;
}

.more-link:focus-visible {
  outline: 3px solid var(--pc-green);
  outline-offset: 2px;
}

/* ---------- Tab ---------- */
.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.tab {
  padding: 6px 14px;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  color: var(--pc-text-sub);
  background: var(--pc-card);
  border: 1px solid var(--pc-border);
  border-radius: 999px;
  cursor: pointer;
  transition: color 0.2s ease, border-color 0.2s ease, background 0.2s ease;
}

.tab:hover {
  color: var(--pc-green);
  border-color: var(--pc-green);
}

.tab.active {
  color: #fff;
  background: var(--pc-green);
  border-color: var(--pc-green);
}

.tab:focus-visible {
  outline: 3px solid var(--pc-green);
  outline-offset: 2px;
}

/* ---------- 兑换记录行 ---------- */
.redeem-row {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
  min-height: 48px;
  padding: 14px 12px;
  margin: 0 -12px;
  font: inherit;
  text-align: left;
  color: inherit;
  background: none;
  border: none;
  border-top: 1px solid var(--pc-border);
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s ease;
}

.tabs + .redeem-row {
  border-top: none;
}

.redeem-row:hover {
  background: var(--pc-bg);
}

.redeem-row:focus-visible {
  outline: 3px solid var(--pc-green);
  outline-offset: 2px;
}

.row-thumb {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 52px;
  height: 52px;
  font-size: 24px;
  background: var(--pc-bg);
  border: 1px solid var(--pc-border);
  border-radius: 10px;
}

.row-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1 1 auto;
  min-width: 0;
}

.row-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--pc-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row-merchant {
  font-size: 13px;
  color: var(--pc-text-sub);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row-code {
  font-size: 13px;
  color: var(--pc-text-sub);
}

.row-code strong {
  font-family: var(--font-sans);
  font-size: 16px;
  font-weight: 800;
  letter-spacing: 0.08em;
  color: var(--pc-green);
  font-variant-numeric: tabular-nums;
}

.row-time {
  font-size: 12.5px;
  color: var(--pc-text-sub);
}

/* ---------- 状态标签：第三套 rs-* ---------- */
.status-tag {
  flex-shrink: 0;
  padding: 2px 10px;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  border-radius: 999px;
  white-space: nowrap;
}

.rs-pending {
  background: #f59e0b; /* 待核销：暖色，提示「该去用了」 */
}

.rs-redeemed {
  background: #16a34a; /* 已核销：完成态 */
}

.rs-expired {
  background: #8a8a8a; /* 已过期：中性灰（积分已退还，不是错误） */
}

.rs-cancelled {
  background: #6b7280;
}

/* ---------- 分页 / 空态 ---------- */
.pager {
  display: flex;
  justify-content: center;
  margin-top: 20px;
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
  transition: color 0.2s ease, border-color 0.2s ease, background 0.2s ease;
}

.empty-cta:hover {
  color: var(--pc-green);
  border-color: var(--pc-green);
  background: var(--pc-bg);
}

.empty-cta:focus-visible {
  outline: 3px solid var(--pc-green);
  outline-offset: 2px;
}
</style>

<!-- ============================================================
     非 scoped：本页挂在 .sub-page 下，卡片骨架与色板来自 ProfileSubLayout；
     这里只补 rs-* 状态色在主题下的可读性 + 助老模式字号/点击目标。
     ============================================================ -->
<style>
/* 高对比度：状态标签改浅底黑字；色板随 ProfileSubLayout 的 .sub-page 覆盖自动变黑 */
html.theme-high-contrast .sub-page .status-tag {
  color: #000000;
}

html.theme-high-contrast .sub-page .rs-pending {
  background: #fcd34d;
}

html.theme-high-contrast .sub-page .rs-redeemed {
  background: #4ade80;
}

html.theme-high-contrast .sub-page .rs-expired,
html.theme-high-contrast .sub-page .rs-cancelled {
  background: #e5e5e5;
}

html.theme-high-contrast .sub-page .row-thumb {
  background: #000000;
  border-color: #ffffff;
}

/* 助老模式：放大文字与点击目标（≥60px） */
html.mode-elderly .sub-page .redeem-row {
  min-height: 72px;
}

html.mode-elderly .sub-page .row-title {
  font-size: 20px;
  white-space: normal;
}

html.mode-elderly .sub-page .row-merchant,
html.mode-elderly .sub-page .row-code,
html.mode-elderly .sub-page .row-time,
html.mode-elderly .sub-page .tab,
html.mode-elderly .sub-page .status-tag,
html.mode-elderly .sub-page .more-link {
  font-size: 18px;
}

html.mode-elderly .sub-page .row-code strong {
  font-size: 20px;
}

html.mode-elderly .sub-page .row-thumb {
  width: 64px;
  height: 64px;
  font-size: 28px;
}

html.mode-elderly .sub-page .tab,
html.mode-elderly .sub-page .more-link {
  display: inline-flex;
  align-items: center;
  min-height: 60px;
  padding: 12px 20px;
}

html.mode-elderly .sub-page .empty-cta {
  min-height: 60px;
  padding: 12px 28px;
  font-size: 20px;
}
</style>
