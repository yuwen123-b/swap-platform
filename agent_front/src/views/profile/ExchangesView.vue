<template>
  <ProfileSubLayout title="我的交换" desc="你发起和收到的交换请求都在这里，确认后即可完成交接">
    <section class="profile-card">
      <!-- Tab：全部 / 我发起的 / 我收到的 / 已完成 / 已取消 -->
      <div class="tabs" role="tablist" aria-label="按状态筛选我的交换">
        <button
          v-for="tab in TABS"
          :key="tab.key"
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

      <p v-if="loading && !orders.length" class="empty-text">加载中…</p>

      <template v-else-if="orders.length">
        <article v-for="order in orders" :key="order.order_id" class="order-row">
          <!-- 整行主体可点击看详情；动作按钮独立成按钮，避免嵌套按钮 -->
          <button type="button" class="row-main" @click="openDetail(order)">
            <span class="row-thumb">
              <img v-if="order.item_image" :src="order.item_image" :alt="`${order.item_title}的图片`" />
              <span v-else class="thumb-fallback" aria-hidden="true">📦</span>
            </span>
            <span class="row-info">
              <span class="row-title">{{ order.item_title || '未命名物品' }}</span>
              <span class="row-time">
                {{ order.viewer_role === 'seller' ? '来自' : '换给' }}
                {{ order.other_nickname }} · {{ formatDate(order.created_at) }}
              </span>
            </span>
          </button>

          <!-- 低价转让单：展示转让价（免费送 / 交换单无金额，什么都不显示） -->
          <span v-if="isPaidOrder(order)" class="row-price">转让价 ¥ {{ formatPrice(order.price) }}</span>

          <span class="status-tag" :class="`os-${order.status}`">{{ order.status_label }}</span>

          <span class="order-actions">
            <!-- 卖家在「待确认」阶段：确认交换 / 拒绝（拒绝复用 cancel，不新增状态） -->
            <el-button
              v-if="order.status === 1 && order.viewer_role === 'seller'"
              type="primary"
              size="small"
              :loading="actingId === order.order_id"
              @click="onConfirm(order)"
            >
              确认交换
            </el-button>
            <el-button
              v-if="order.status === 1 && order.viewer_role === 'seller'"
              type="danger"
              plain
              size="small"
              :loading="actingId === order.order_id"
              @click="onReject(order)"
            >
              拒绝
            </el-button>
            <!-- 交换中：买卖任一方确认完成 -->
            <el-button
              v-if="order.status === 2"
              type="primary"
              size="small"
              :loading="actingId === order.order_id"
              @click="onComplete(order)"
            >
              确认完成
            </el-button>
            <!-- 待确认 / 交换中：买卖任一方可取消 -->
            <el-button
              v-if="order.status === 1 || order.status === 2"
              size="small"
              :loading="actingId === order.order_id"
              @click="onCancel(order)"
            >
              取消
            </el-button>
            <el-button link size="small" @click="openDetail(order)">查看详情</el-button>
          </span>
        </article>

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
          去探索物品
        </button>
      </template>
    </section>

    <!-- 详情弹窗：物品 + 双方 + 状态时间线 + 消息记录 -->
    <el-dialog v-model="detailVisible" title="交换详情" width="520px" append-to-body>
      <div v-if="detailLoading" class="detail-loading">加载中…</div>

      <div v-else-if="detail" class="detail-box">
        <div class="detail-head">
          <span class="detail-thumb">
            <img v-if="detail.item && detail.item.cover" :src="detail.item.cover" alt="" />
            <span v-else aria-hidden="true">📦</span>
          </span>
          <span class="detail-head-info">
            <span class="detail-title">{{ detail.item ? detail.item.title : detail.item_title }}</span>
            <span class="detail-sub">订单号 {{ detail.order_no }}</span>
          </span>
          <span class="status-tag" :class="`os-${detail.status}`">{{ detail.status_label }}</span>
        </div>

        <div class="detail-parties">
          <span>{{ detail.viewer_role === 'seller' ? '接手方' : '发布邻居' }}：{{
            detail.viewer_role === 'seller' ? detail.buyer.nickname : detail.seller.nickname
          }}</span>
          <span>物品状态：{{ detail.item ? detail.item.status_label : '物品已不存在' }}</span>
          <span v-if="isPaidOrder(detail)" class="detail-price">
            转让价 ¥ {{ formatPrice(detail.price) }}
          </span>
        </div>

        <h3 class="detail-sub-title">状态时间线</h3>
        <ul class="timeline">
          <li v-for="node in detail.timeline" :key="node.status" class="timeline-node">
            <span class="timeline-dot" :class="`os-${node.status}`" aria-hidden="true"></span>
            <span class="timeline-label">{{ node.status_label }}</span>
            <span class="timeline-at">{{ node.at ? formatDateTime(node.at) : '—' }}</span>
          </li>
        </ul>
        <p class="detail-hint">「—」表示该节点没有单独记录时间（由当前状态推导而来）</p>

        <h3 class="detail-sub-title">消息记录</h3>
        <ul v-if="detail.messages.length" class="messages">
          <li v-for="msg in detail.messages" :key="msg.id" class="message-item">
            <span class="message-head">
              <span class="message-sender">{{ msg.sender_nickname }}</span>
              <span class="message-at">{{ formatDateTime(msg.created_at) }}</span>
            </span>
            <span class="message-content">{{ msg.content }}</span>
          </li>
        </ul>
        <p v-else class="empty-text">这笔交换还没有留言记录</p>
      </div>
    </el-dialog>
  </ProfileSubLayout>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import ProfileSubLayout from '../../layouts/ProfileSubLayout.vue'
import { cancelOrder, completeOrder, confirmOrder, getOrderDetail, getOrders } from '../../api/order'

const router = useRouter()

const PAGE_SIZE = 10

// Tab 与后端查询参数的映射：
// 「已完成 / 已取消」走 status 过滤，角色维度保留 all（我在单里的身份由后端判定）
const TABS = [
  { key: 'all', label: '全部', params: { role: 'all' } },
  { key: 'bought', label: '我发起的', params: { role: 'buyer' } },
  { key: 'sold', label: '我收到的', params: { role: 'seller' } },
  { key: 'done', label: '已完成', params: { role: 'all', status: 3 } },
  { key: 'cancelled', label: '已取消', params: { role: 'all', status: 4 } },
]

const EMPTY_TEXT = {
  all: '还没有交换记录，去探索物品发起交换吧',
  bought: '你还没有发起过交换，去物品详情页点「我要换」试试',
  sold: '暂时还没有人向你发起交换',
  done: '还没有已完成的交换',
  cancelled: '没有已取消的交换记录',
}

const activeTab = ref('all')
const orders = ref([])
const total = ref(0)
const page = ref(1)
const size = ref(PAGE_SIZE)
const loading = ref(false)
const actingId = ref(null)

const emptyText = computed(() => EMPTY_TEXT[activeTab.value] || '暂无交换记录')

/* ---------- 详情弹窗 ---------- */
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref(null)

/* ---------- 工具 ---------- */
function formatDate(value) {
  if (!value) return '时间未知'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间未知'
  return date.toLocaleDateString('zh-CN')
}

function formatDateTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('zh-CN', { hour12: false })
}

// 是否是「低价转让」单：order.exchange_type=1（购买，由 item.exchange_mode=3 映射而来）
// 且带正数金额。免费送 / 交换单的 price 恒为 0，因此统一显示「无金额」。
function isPaidOrder(order) {
  return Number(order?.exchange_type) === 1 && Number(order?.price) > 0
}

function formatPrice(value) {
  const num = Number(value)
  return Number.isFinite(num) ? num.toFixed(2) : '0.00'
}

// 后端业务错误走 { code, message } 外壳；这里的请求都带 skipErrorToast，
// 因此提示文案全部由本页给出，不会出现拦截器 + 页面的双弹。
function readErrorText(error) {
  return error?.response?.data?.message || error?.message || ''
}

function errorText(error, fallback) {
  const status = error?.response?.status
  if (status === 401) return '登录状态已失效，请重新登录'
  if (status === 404) return '订单不存在或已被删除'
  return readErrorText(error) || fallback
}

/* ---------- 列表 ---------- */
async function load() {
  loading.value = true
  const tab = TABS.find((item) => item.key === activeTab.value) || TABS[0]
  try {
    const data = await getOrders({ ...tab.params, page: page.value, size: size.value })
    orders.value = data?.list || []
    total.value = Number(data?.total || 0)
  } catch {
    // 列表查询交给请求拦截器统一提示
    orders.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function switchTab(key) {
  if (activeTab.value === key) return
  activeTab.value = key
  // 切换筛选条件必须回到第 1 页，否则可能落到不存在的页码上显示空列表
  page.value = 1
  load()
}

function onPageChange(next) {
  page.value = next
  load()
}

/* ---------- 动作（均二次确认） ---------- */
async function askConfirm(message, title, confirmText) {
  try {
    await ElMessageBox.confirm(message, title, {
      confirmButtonText: confirmText,
      cancelButtonText: '再想想',
      type: 'warning',
    })
    return true
  } catch {
    return false // 用户放弃
  }
}

async function runAction(order, action, successText) {
  actingId.value = order.order_id
  try {
    const data = await action()
    ElMessage.success(typeof successText === 'function' ? successText(data) : successText)
    await load()
    // 详情弹窗开着时同步刷新，避免看到过期状态
    if (detailVisible.value && detail.value?.order_id === order.order_id) {
      await refreshDetail(order.order_id)
    }
  } catch (error) {
    ElMessage.error(errorText(error, '操作失败，请稍后再试'))
  } finally {
    actingId.value = null
  }
}

async function onConfirm(order) {
  const ok = await askConfirm(
    `确认接受「${order.item_title || '该物品'}」的交换请求吗？确认后订单进入「交换中」。`,
    '确认交换',
    '确认交换',
  )
  if (!ok) return
  await runAction(order, () => confirmOrder(order.order_id), '已确认交换，请及时完成交接')
}

async function onReject(order) {
  const ok = await askConfirm(
    `确定拒绝「${order.item_title || '该物品'}」的交换请求吗？拒绝后订单将变为「已取消」。`,
    '拒绝交换',
    '拒绝',
  )
  if (!ok) return
  await runAction(order, () => cancelOrder(order.order_id), '已拒绝该交换请求')
}

async function onComplete(order) {
  const ok = await askConfirm(
    `确认「${order.item_title || '该物品'}」已经完成交接吗？确认后双方各获得交换积分，物品将下架。`,
    '确认完成',
    '确认完成',
  )
  if (!ok) return
  await runAction(
    order,
    () => completeOrder(order.order_id),
    (data) =>
      `交换已完成，双方各获得 ${data?.points_awarded ?? 0} 积分，减碳 ${data?.carbon_added ?? 0} kg`,
  )
}

async function onCancel(order) {
  const ok = await askConfirm(
    `确定取消「${order.item_title || '该物品'}」的这笔交换吗？`,
    '取消交换',
    '取消',
  )
  if (!ok) return
  await runAction(order, () => cancelOrder(order.order_id), '订单已取消')
}

/* ---------- 详情 ---------- */
async function refreshDetail(orderId) {
  detailLoading.value = true
  try {
    const data = await getOrderDetail(orderId)
    detail.value = data ? { ...data, item_title: data.item ? data.item.title : '物品已不存在' } : null
  } catch (error) {
    ElMessage.error(errorText(error, '详情加载失败，请稍后再试'))
  } finally {
    detailLoading.value = false
  }
}

async function openDetail(order) {
  detail.value = null
  detailVisible.value = true
  await refreshDetail(order.order_id)
}

onMounted(load)
</script>

<style scoped>
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

/* ---------- 订单行 ---------- */
.order-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  min-height: 48px;
  padding: 12px;
  margin: 0 -12px;
  border-top: 1px solid var(--pc-border);
  border-radius: 8px;
  transition: background 0.2s ease;
}

.tabs + .order-row {
  border-top: none;
}

.order-row:hover {
  background: var(--pc-bg);
}

.row-main {
  display: flex;
  align-items: center;
  gap: 14px;
  flex: 1 1 240px;
  min-width: 0;
  padding: 0;
  font: inherit;
  text-align: left;
  color: inherit;
  background: none;
  border: none;
  cursor: pointer;
}

.row-main:focus-visible {
  outline: 3px solid var(--pc-green);
  outline-offset: 2px;
  border-radius: 10px;
}

.row-thumb {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 56px;
  height: 56px;
  overflow: hidden;
  background: var(--pc-bg);
  border: 1px solid var(--pc-border);
  border-radius: 10px;
}

.row-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb-fallback {
  font-size: 24px;
  opacity: 0.6;
}

.row-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.row-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--pc-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 280px;
}

.row-time {
  margin-top: 4px;
  font-size: 13px;
  color: var(--pc-text-sub);
}

/* ---------- 动作区 ---------- */
.order-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  flex-shrink: 0;
}

/* ---------- 转让价 ---------- */
.row-price {
  flex-shrink: 0;
  padding: 2px 10px;
  font-size: 12.5px;
  font-weight: 600;
  color: #b7791f;
  background: #fff8e1;
  border-radius: 999px;
  white-space: nowrap;
}

.detail-price {
  font-weight: 600;
  color: #b7791f;
}

/* ---------- 状态标签 ---------- */
.status-tag {
  flex-shrink: 0;
  padding: 2px 10px;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  border-radius: 999px;
}

/* 订单状态与物品/需求状态（s-*）刻意分开命名：数值含义不同，
   订单 3 是「已完成」，s-3 是「审核未通过（红）」，复用会把语义显示反。 */
.os-1 {
  background: #f59e0b; /* 待确认 */
}

.os-2 {
  background: #3b82f6; /* 交换中 */
}

.os-3 {
  background: #16a34a; /* 已完成 */
}

.os-4 {
  background: #8a8a8a; /* 已取消 */
}

.os-5 {
  background: #7c3aed; /* 争议中 */
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

/* ---------- 详情弹窗 ---------- */
.detail-loading {
  padding: 12px 0;
  font-size: 14px;
  color: var(--pc-text-sub);
}

.detail-box {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.detail-head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.detail-thumb {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 56px;
  height: 56px;
  overflow: hidden;
  font-size: 24px;
  background: var(--pc-bg);
  border: 1px solid var(--pc-border);
  border-radius: 10px;
}

.detail-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.detail-head-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  flex: 1;
}

.detail-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--pc-text);
}

.detail-sub {
  font-size: 12.5px;
  color: var(--pc-text-sub);
}

.detail-parties {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 20px;
  padding: 10px 12px;
  font-size: 13px;
  color: var(--pc-text-sub);
  background: var(--pc-bg);
  border-radius: 10px;
}

.detail-sub-title {
  margin: 4px 0 0;
  font-size: 14px;
  font-weight: 700;
  color: var(--pc-text);
}

.timeline {
  margin: 0;
  padding: 0;
  list-style: none;
}

.timeline-node {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 32px;
  font-size: 13px;
}

.timeline-dot {
  flex-shrink: 0;
  width: 12px;
  height: 12px;
  border-radius: 50%;
}

.timeline-label {
  font-weight: 600;
  color: var(--pc-text);
}

.timeline-at {
  color: var(--pc-text-sub);
}

.detail-hint {
  margin: -6px 0 0;
  font-size: 12px;
  color: var(--pc-text-sub);
}

.messages {
  margin: 0;
  padding: 0;
  list-style: none;
  max-height: 220px;
  overflow-y: auto;
}

.message-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  margin-bottom: 8px;
  background: var(--pc-bg);
  border-radius: 10px;
}

.message-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 12.5px;
  color: var(--pc-text-sub);
}

.message-sender {
  font-weight: 600;
  color: var(--pc-text);
}

.message-content {
  font-size: 13.5px;
  line-height: 1.7;
  color: var(--pc-text);
  word-break: break-word;
}

/* ---------- 响应式 ---------- */
@media (max-width: 480px) {
  .row-title {
    max-width: 150px;
  }

  .row-thumb {
    width: 48px;
    height: 48px;
  }
}
</style>

<!-- ============================================================
     高对比度 / 助老模式适配（必须非 scoped 才能命中 html 根级选择器）
     ============================================================ -->
<style>
html.theme-high-contrast .sub-page .status-tag {
  color: #000000;
}

html.theme-high-contrast .sub-page .os-1 {
  background: #fcd34d;
}

html.theme-high-contrast .sub-page .os-2 {
  background: #93c5fd;
}

html.theme-high-contrast .sub-page .os-3 {
  background: #4ade80;
}

html.theme-high-contrast .sub-page .os-4 {
  background: #e5e5e5;
}

html.theme-high-contrast .sub-page .os-5 {
  background: #c4b5fd;
}

/* 转让价：黑底上用浅黄底 + 黑字，保证对比度 */
html.theme-high-contrast .sub-page .row-price {
  background: #fde68a;
  color: #000000;
}

html.theme-high-contrast .sub-page .detail-price {
  color: #fde68a;
}

/* 助老模式：放大文字与点击目标 */
html.mode-elderly .sub-page .row-title,
html.mode-elderly .sub-page .detail-title {
  font-size: 20px;
  max-width: 100%;
}

html.mode-elderly .sub-page .row-time,
html.mode-elderly .sub-page .status-tag,
html.mode-elderly .sub-page .tab,
html.mode-elderly .sub-page .timeline-node,
html.mode-elderly .sub-page .message-content {
  font-size: 18px;
}

html.mode-elderly .sub-page .order-row {
  min-height: 72px;
}

html.mode-elderly .sub-page .row-thumb,
html.mode-elderly .sub-page .detail-thumb {
  width: 72px;
  height: 72px;
}

html.mode-elderly .sub-page .empty-cta {
  min-height: 60px;
  padding: 12px 28px;
  font-size: 20px;
}
</style>
