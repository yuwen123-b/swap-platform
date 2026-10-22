<template>
  <section class="mw-page mw-dash">
    <div class="mw-page-head">
      <div>
        <h1 class="mw-page-title">数据看板</h1>
        <p class="mw-page-desc">看看你的服务被多少邻居用上了</p>
      </div>
      <button type="button" class="mw-btn" :disabled="loading" @click="load">
        {{ loading ? '刷新中…' : '刷新数据' }}
      </button>
    </div>

    <!-- 4 张统计卡 -->
    <div class="stat-grid">
      <div v-for="card in statCards" :key="card.key" class="stat-card">
        <span class="stat-icon" aria-hidden="true">{{ card.icon }}</span>
        <span class="stat-value">{{ card.value }}</span>
        <span class="stat-label">{{ card.label }}</span>
        <span class="stat-hint">{{ card.hint }}</span>
      </div>
    </div>

    <p v-if="dashError" class="mw-error" role="alert">
      看板数据加载失败，请点击右上角「刷新数据」重试。
    </p>

    <!-- 热门商品 Top5 -->
    <div class="mw-card">
      <div class="mw-card-head">
        <h2 class="mw-card-title">热门商品 Top 5</h2>
        <span class="card-sub">按累计兑换数排序</span>
      </div>

      <ol v-if="popular.length" class="popular-list">
        <li v-for="(product, index) in popular" :key="product.title + index" class="popular-row">
          <span class="popular-rank" aria-hidden="true">{{ index + 1 }}</span>
          <span class="popular-main">
            <span class="popular-name">{{ product.title || '未命名商品' }}</span>
            <span class="bar-track">
              <span class="bar-fill" :style="{ width: popularWidth(product.sold_count) }"></span>
            </span>
          </span>
          <span class="popular-value">{{ product.sold_count }} 次</span>
        </li>
      </ol>
      <p v-else class="mw-empty">
        {{ dashError ? '数据加载失败，暂无法展示' : '还没有商品被兑换，先去「商品管理」上架几个吧' }}
      </p>
    </div>

    <!-- 7 天核销趋势（纯 CSS 柱状图，零新依赖） -->
    <div class="mw-card">
      <div class="mw-card-head">
        <h2 class="mw-card-title">近 7 天核销趋势</h2>
        <span class="card-sub">单位：次</span>
      </div>

      <div v-if="trend.length" class="chart" role="img" :aria-label="chartLabel">
        <div v-for="point in trend" :key="point.date" class="chart-col">
          <span class="chart-value">{{ point.count }}</span>
          <span class="chart-bar-track">
            <span
              class="chart-bar"
              :style="{ height: barHeight(point.count) }"
              :title="`${point.date} 核销 ${point.count} 次`"
            ></span>
          </span>
          <span class="chart-label">{{ shortDate(point.date) }}</span>
        </div>
      </div>
      <p v-else class="mw-empty">
        {{ dashError ? '数据加载失败，暂无法展示' : '近 7 天还没有核销记录' }}
      </p>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { getMerchantDashboard, getMerchantRedemptions } from '../../api/merchant'

/**
 * 数据看板。
 *
 * 【为什么并发两个请求】
 * `GET /merchant/dashboard` 不返回「待核销订单数」（任务书要的第 4 张卡），
 * 而它等价于 `GET /merchant/redemptions?status=1` 的 total。
 * 为了不强改后端接口，第 4 张卡复用列表接口只取 total（size=1）。
 *
 * 【为什么用 allSettled 而不是 all】
 * 两个请求任一失败都不该让整页空白：正常的那部分照常渲染，
 * 失败的那块显示重试提示。
 */
const dash = ref(null)
const pendingTotal = ref(0)
const loading = ref(true)
const dashError = ref(false)
const pendingError = ref(false)

const popular = computed(() => dash.value?.popular_products || [])
const trend = computed(() => dash.value?.trend || [])

const statCards = computed(() => [
  {
    key: 'today',
    icon: '📅',
    label: '今日核销',
    hint: '今天已核销的单数',
    value: fmt(dash.value?.today_redemptions),
  },
  {
    key: 'total',
    icon: '🎫',
    label: '累计核销',
    hint: '开店至今核销总数',
    value: fmt(dash.value?.total_redemptions),
  },
  {
    key: 'users',
    icon: '🙋',
    label: '服务用户',
    hint: '去重后的兑换人数',
    value: fmt(dash.value?.unique_users),
  },
  {
    key: 'pending',
    icon: '⏳',
    label: '待核销订单',
    hint: '等邻居到店使用',
    value: pendingError.value ? '—' : fmt(pendingTotal.value),
  },
])

function fmt(value) {
  const n = Number(value)
  return Number.isFinite(n) ? String(n) : '0'
}

/* ---------- 热门商品条形宽度 ---------- */
const popularMax = computed(() => Math.max(1, ...popular.value.map((p) => Number(p.sold_count) || 0)))

function popularWidth(value) {
  const ratio = (Number(value) || 0) / popularMax.value
  return `${Math.max(ratio * 100, 4)}%`
}

/* ---------- 7 天柱状图 ---------- */
// 全 0 时给 3% 兜底高度：否则整排柱子高度为 0，图表看起来像没渲染
const trendMax = computed(() => Math.max(1, ...trend.value.map((p) => Number(p.count) || 0)))

function barHeight(count) {
  const ratio = (Number(count) || 0) / trendMax.value
  return `${Math.max(ratio * 100, 3)}%`
}

function shortDate(value) {
  const text = String(value || '')
  return text.length >= 10 ? text.slice(5) : text
}

const chartLabel = computed(
  () => `近 7 天核销：${trend.value.map((p) => `${p.date} ${p.count} 次`).join('；') || '暂无数据'}`,
)

/* ---------- 加载 ---------- */
async function load() {
  loading.value = true
  dashError.value = false
  pendingError.value = false

  const [dashboard, pending] = await Promise.allSettled([
    getMerchantDashboard(),
    // 只取 total：size=1，列表本身不用
    getMerchantRedemptions({ status: 1, page: 1, size: 1 }),
  ])

  if (dashboard.status === 'fulfilled') {
    dash.value = dashboard.value
  } else {
    dashError.value = true
  }

  if (pending.status === 'fulfilled') {
    pendingTotal.value = Number(pending.value?.total || 0)
  } else {
    pendingError.value = true
  }

  loading.value = false
}

onMounted(load)
</script>

<style scoped>
/* ---------- 4 张统计卡 ---------- */
.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 14px;
  margin-bottom: 18px;
}

.stat-card {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 16px;
  background: var(--mw-card);
  border: 1px solid var(--mw-border);
  border-radius: 16px;
  box-shadow: var(--mw-shadow);
}

.stat-icon {
  font-size: 20px;
}

.stat-value {
  margin-top: 4px;
  font-size: 32px;
  font-weight: 800;
  line-height: 1.1;
  color: var(--mw-green);
  font-variant-numeric: tabular-nums;
}

.stat-label {
  font-size: 14px;
  font-weight: 700;
  color: var(--mw-text);
}

.stat-hint {
  font-size: 12px;
  line-height: 1.6;
  color: var(--mw-text-sub);
}

.card-sub {
  font-size: 12px;
  color: var(--mw-text-sub);
}

/* ---------- 热门商品 ---------- */
.popular-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.popular-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.popular-rank {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  font-size: 12px;
  font-weight: 800;
  color: #fff;
  background: var(--mw-green);
  border-radius: 8px;
}

.popular-main {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1 1 auto;
  min-width: 0;
}

.popular-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--mw-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bar-track {
  display: block;
  height: 8px;
  overflow: hidden;
  background: var(--mw-track);
  border-radius: 999px;
}

.bar-fill {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--mw-green), var(--teal, #38b2ac));
  border-radius: 999px;
  transition: width 0.3s ease;
}

.popular-value {
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 700;
  color: var(--mw-text-sub);
  font-variant-numeric: tabular-nums;
}

/* ---------- 柱状图（纯 CSS） ---------- */
.chart {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding-top: 8px;
}

.chart-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  flex: 1 1 0;
  min-width: 0;
}

.chart-value {
  font-size: 12px;
  font-weight: 700;
  color: var(--mw-text);
  font-variant-numeric: tabular-nums;
}

.chart-bar-track {
  display: flex;
  align-items: flex-end;
  width: 100%;
  height: 132px;
  background: var(--mw-track);
  border-radius: 8px;
  overflow: hidden;
}

.chart-bar {
  display: block;
  width: 100%;
  background: linear-gradient(180deg, var(--mw-green), var(--teal, #38b2ac));
  border-radius: 8px 8px 0 0;
  transition: height 0.3s ease;
}

.chart-label {
  font-size: 11px;
  color: var(--mw-text-sub);
  white-space: nowrap;
}
</style>

<!-- ============================================================
     非 scoped：高对比度 / 助老模式
     ============================================================ -->
<style>
html.theme-high-contrast .mw-shell .bar-fill,
html.theme-high-contrast .mw-shell .chart-bar {
  background: #4ade80;
}

html.theme-high-contrast .mw-shell .popular-rank {
  color: #000000;
  background: #ffffff;
}

html.theme-high-contrast .mw-shell .stat-value {
  color: #4ade80;
}

html.theme-high-contrast .mw-shell .chart-bar-track,
html.theme-high-contrast .mw-shell .bar-track {
  background: rgba(255, 255, 255, 0.25);
}

html.mode-elderly .mw-shell .stat-value {
  font-size: 38px;
}

html.mode-elderly .mw-shell .stat-label {
  font-size: 18px;
}

html.mode-elderly .mw-shell .stat-hint,
html.mode-elderly .mw-shell .card-sub,
html.mode-elderly .mw-shell .popular-value,
html.mode-elderly .mw-shell .chart-value,
html.mode-elderly .mw-shell .chart-label {
  font-size: 16px;
}

html.mode-elderly .mw-shell .popular-name {
  font-size: 18px;
  white-space: normal;
}

html.mode-elderly .mw-shell .popular-rank {
  width: 32px;
  height: 32px;
  font-size: 16px;
}

html.mode-elderly .mw-shell .chart-bar-track {
  height: 170px;
}
</style>
