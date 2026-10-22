<template>
  <ProfileSubLayout
    title="我的回收单"
    desc="交给平台回收的物品：提交立即得积分，平台安排取件并出售给合作回收商"
  >
    <section class="profile-card">
      <div class="card-head">
        <h2 class="card-title">回收记录</h2>
        <button type="button" class="more-link" :disabled="loading" @click="load">
          {{ loading ? '刷新中…' : '刷新' }}
        </button>
      </div>

      <!-- Tab：全部 / 待取件 / 已入库 / 已售出 / 已取消（与后端 platform_recycle.status 同枚举） -->
      <div class="tabs" role="tablist" aria-label="按状态筛选我的回收单">
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
        <div v-for="item in items" :key="item.id" class="recycle-row">
          <span class="row-thumb" aria-hidden="true">{{ thumbIcon }}</span>

          <span class="row-info">
            <span class="row-title">{{ item.item_title || '未命名物品' }}</span>
            <span class="row-sub">
              估价 <strong class="row-points">+{{ item.points_reward }}</strong> 积分 ·
              {{ item.pickup_method_label }}
              <template v-if="item.pickup_address">（{{ item.pickup_address }}）</template>
            </span>
            <span class="row-no">单号 {{ item.recycle_no }}</span>
            <span class="row-time">{{ timeLine(item) }}</span>
          </span>

          <span class="row-side">
            <span class="status-tag" :class="statusClass(item.status)">
              {{ item.status_label }}
            </span>
            <button
              v-if="Number(item.status) === 1"
              type="button"
              class="cancel-btn"
              :disabled="cancellingId === item.id"
              @click="confirmCancel(item)"
            >
              {{ cancellingId === item.id ? '取消中…' : '取消回收' }}
            </button>
          </span>
        </div>

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
        <button type="button" class="empty-cta" @click="router.push('/items')">
          去发布一件闲置
        </button>
      </template>
    </section>
  </ProfileSubLayout>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import ProfileSubLayout from '../../layouts/ProfileSubLayout.vue'
import { cancelRecycle, getMyRecycles } from '../../api/recycle'

const router = useRouter()

const PAGE_SIZE = 10

// status 与后端 platform_recycle.status 枚举一致
const TABS = [
  { key: 'all', label: '全部', status: null },
  { key: 1, label: '待取件', status: 1 },
  { key: 2, label: '已入库', status: 2 },
  { key: 3, label: '已售出', status: 3 },
  { key: 4, label: '已取消', status: 4 },
]

const EMPTY_TEXT = {
  all: '还没有回收记录，发布物品时选择「交给平台回收」即可立即得积分',
  1: '没有待取件的回收单',
  2: '没有已入库的回收单',
  3: '没有已售出的回收单',
  4: '没有已取消的回收单',
}

/* ============================================================
   状态类名：**第四套** yc-*（语义命名，非数字）。
   项目已有 s-*（物品/需求）、os-*（交换单）、rs-*（兑换单）三套，
   回收单枚举（1 待取件 / 2 已入库 / 3 已售出 / 4 已取消）语义各不相同，
   复用任何一套都会出现「已售出显示成红色」之类的语义反向，故新开一套。
   ============================================================ */
const STATUS_CLASS = {
  1: 'yc-pending',
  2: 'yc-stock',
  3: 'yc-sold',
  4: 'yc-cancelled',
}

function statusClass(status) {
  return STATUS_CLASS[Number(status)] || 'yc-cancelled'
}

// 分类 emoji 占位（回收列表回传首图相对路径，此处保持与兑换记录一致的轻量占位）
const thumbIcon = '♻️'

const activeTab = ref('all')
const items = ref([])
const total = ref(0)
const page = ref(1)
const size = ref(PAGE_SIZE)
const loading = ref(false)
const cancellingId = ref(null)

const emptyText = computed(() => EMPTY_TEXT[activeTab.value] ?? EMPTY_TEXT.all)

async function load() {
  loading.value = true
  try {
    const tab = TABS.find((item) => item.key === activeTab.value) || TABS[0]
    const params = { page: page.value, size: size.value }
    if (tab.status !== null) params.status = tab.status
    const data = await getMyRecycles(params)
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

/* ---------- 取消回收：仅待取件可取消，积分原额退回（二次确认） ---------- */
function confirmCancel(item) {
  ElMessageBox.confirm(
    `取消后「${item.item_title || '该物品'}」的回收单将作废，已获得的 ${item.points_reward} 积分会原额退回。确认取消？`,
    '取消回收',
    {
      confirmButtonText: '确认取消',
      cancelButtonText: '再想想',
      type: 'warning',
    },
  )
    .then(async () => {
      cancellingId.value = item.id
      try {
        const result = await cancelRecycle(item.id, { skipErrorToast: true })
        ElMessage.success(`已取消回收，${result?.refund_points ?? item.points_reward} 积分已退回`)
        load()
      } catch (error) {
        const serverMsg = error?.response?.data?.message || error?.message || ''
        ElMessage.error(serverMsg || '取消失败，请稍后重试')
      } finally {
        cancellingId.value = null
      }
    })
    .catch(() => {})
}

/* ---------- 展示工具 ---------- */
function toDate(value) {
  if (!value) return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d
}

function formatDateTime(value) {
  const d = toDate(value)
  if (!d) return ''
  return `${d.toLocaleDateString('zh-CN')} ${d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
}

// 按状态给出一句「时间」：入库 / 售出 / 取消
function timeLine(item) {
  const status = Number(item?.status)
  if (status === 2) return item.received_at ? `入库于 ${formatDateTime(item.received_at)}` : '已入库'
  if (status === 3) return item.sold_at ? `售出于 ${formatDateTime(item.sold_at)}` : '已售出'
  if (status === 4) return '已取消，积分已退回'
  return item.created_at ? `提交于 ${formatDateTime(item.created_at)}` : ''
}

onMounted(load)
</script>

<style scoped>
/* ---------- 卡片头（与 RedemptionsView 同款） ---------- */
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

/* ---------- 回收记录行 ---------- */
.recycle-row {
  display: flex;
  align-items: center;
  gap: 14px;
  min-height: 48px;
  padding: 14px 12px;
  border-top: 1px solid var(--pc-border);
  border-radius: 8px;
  transition: background 0.2s ease;
}

.tabs + .recycle-row {
  border-top: none;
}

.recycle-row:hover {
  background: var(--pc-bg);
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

.row-sub {
  font-size: 13px;
  color: var(--pc-text-sub);
}

.row-points {
  color: var(--pc-green);
  font-variant-numeric: tabular-nums;
}

.row-no {
  font-size: 12.5px;
  color: var(--pc-text-sub);
}

.row-time {
  font-size: 12.5px;
  color: var(--pc-text-sub);
}

.row-side {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  flex-shrink: 0;
}

/* ---------- 状态标签：第四套 yc-* ---------- */
.status-tag {
  padding: 2px 10px;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  border-radius: 999px;
  white-space: nowrap;
}

.yc-pending {
  background: #f59e0b; /* 待取件：暖色，提示「在路上了」 */
}

.yc-stock {
  background: #2563eb; /* 已入库：蓝色，平台持有中 */
}

.yc-sold {
  background: #16a34a; /* 已售出：完成态 */
}

.yc-cancelled {
  background: #8a8a8a; /* 已取消：中性灰（积分已退回，不是错误） */
}

.cancel-btn {
  padding: 4px 12px;
  font: inherit;
  font-size: 12.5px;
  font-weight: 600;
  color: #b91c1c;
  background: #fff;
  border: 1px solid rgba(185, 28, 28, 0.4);
  border-radius: 999px;
  cursor: pointer;
  transition: color 0.2s ease, border-color 0.2s ease, background 0.2s ease;
}

.cancel-btn:hover:not(:disabled) {
  color: #fff;
  background: #b91c1c;
  border-color: #b91c1c;
}

.cancel-btn:disabled {
  cursor: default;
  opacity: 0.6;
}

.cancel-btn:focus-visible {
  outline: 3px solid #b91c1c;
  outline-offset: 2px;
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
     非 scoped：高对比度可读性 + 助老模式字号/点击目标（与 RedemptionsView 同口径）。
     ============================================================ -->
<style>
html.theme-high-contrast .sub-page .status-tag {
  color: #000000;
}

html.theme-high-contrast .sub-page .yc-pending {
  background: #fcd34d;
}

html.theme-high-contrast .sub-page .yc-stock {
  background: #93c5fd;
}

html.theme-high-contrast .sub-page .yc-sold {
  background: #4ade80;
}

html.theme-high-contrast .sub-page .yc-cancelled {
  background: #e5e5e5;
}

html.theme-high-contrast .sub-page .row-thumb {
  background: #000000;
  border-color: #ffffff;
}

html.mode-elderly .sub-page .recycle-row {
  min-height: 72px;
}

html.mode-elderly .sub-page .row-title {
  font-size: 20px;
  white-space: normal;
}

html.mode-elderly .sub-page .row-sub,
html.mode-elderly .sub-page .row-no,
html.mode-elderly .sub-page .row-time,
html.mode-elderly .sub-page .tab,
html.mode-elderly .sub-page .status-tag,
html.mode-elderly .sub-page .more-link,
html.mode-elderly .sub-page .cancel-btn {
  font-size: 18px;
}

html.mode-elderly .sub-page .row-thumb {
  width: 64px;
  height: 64px;
  font-size: 28px;
}

html.mode-elderly .sub-page .tab,
html.mode-elderly .sub-page .more-link,
html.mode-elderly .sub-page .cancel-btn {
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
