<template>
  <ProfileSubLayout title="碳积分明细" desc="查看碳积分余额、等级进度、社区排名与每一次积分变动">
    <!-- 汇总 + 进度 -->
    <section class="profile-card">
      <h2 class="card-title">碳积分概览</h2>

      <div class="summary-head">
        <span class="level-badge" :class="`level-${summary.level}`">{{ summary.level_label }}</span>
        <span class="summary-tip">
          <template v-if="summary.next_level">
            距离 {{ summary.next_level }} 还差 {{ summary.next_level_gap }} 分
          </template>
          <template v-else>已达最高等级 {{ summary.level_label }}</template>
        </span>
      </div>

      <div class="stat-grid">
        <div class="stat-block">
          <span class="stat-value">{{ summary.total_points }}<span class="stat-unit">分</span></span>
          <span class="stat-label">碳积分余额</span>
        </div>
        <div class="stat-block">
          <span class="stat-value">{{ carbonDisplay }}<span class="stat-unit">kg</span></span>
          <span class="stat-label">碳减排量</span>
        </div>
        <div class="stat-block">
          <span class="stat-value">{{ summary.exchange_count }}<span class="stat-unit">次</span></span>
          <span class="stat-label">完成交换</span>
        </div>
      </div>

      <div class="progress-wrap">
        <div
          class="progress-track"
          role="progressbar"
          aria-valuemin="0"
          aria-valuemax="100"
          :aria-valuenow="summary.progress_percent"
          :aria-label="`距离 ${summary.next_level || '满级'} 的进度`"
        >
          <div class="progress-fill" :style="{ width: `${summary.progress_percent}%` }"></div>
        </div>
        <p class="progress-text">当前等级进度 {{ summary.progress_percent }}%</p>
      </div>
    </section>

    <!-- 社区排名 -->
    <section class="profile-card">
      <h2 class="card-title">社区排名</h2>
      <template v-if="rank.rank !== null && rank.rank !== undefined">
        <div class="rank-line">
          <span class="rank-no">{{ rank.rank }}</span>
          <span class="rank-unit">/ {{ rank.total }} 位</span>
        </div>
        <p class="card-hint">在「{{ rank.community }}」的碳积分排名</p>
      </template>
      <p v-else class="empty-text">未设置所在社区，暂无排名。可在「位置管理」中填写你的社区</p>
    </section>

    <!-- 积分明细 -->
    <section class="profile-card">
      <h2 class="card-title">积分明细</h2>

      <p v-if="logsLoading && !logs.length" class="empty-text">加载中…</p>

      <template v-else-if="logs.length">
        <div v-for="log in logs" :key="log.id" class="log-row">
          <div class="log-main">
            <div class="log-desc">{{ log.description || log.source_label }}</div>
            <div class="log-time">{{ formatDateTime(log.created_at) }}</div>
          </div>
          <div class="log-right">
            <span class="log-delta" :class="log.points >= 0 ? 'plus' : 'minus'">
              {{ log.points >= 0 ? '+' : '' }}{{ log.points }}
            </span>
            <span class="log-balance">余额 {{ log.balance }}</span>
          </div>
        </div>

        <div v-if="hasMore" class="more-wrap">
          <el-button :loading="logsLoading" @click="loadMore">加载更多</el-button>
        </div>
      </template>

      <p v-else class="empty-text">暂无积分记录。发布物品通过审核、完成交换都能获得积分</p>
    </section>
  </ProfileSubLayout>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import ProfileSubLayout from '../../layouts/ProfileSubLayout.vue'
import { getCarbonLogs, getCarbonRank, getCarbonSummary } from '../../api/user'

// 后端 /carbon/logs 只支持 limit（无 offset），因此用「逐步放大 limit」实现加载更多
const LOG_STEP = 10
const LOG_MAX = 50

const summary = ref({
  total_points: 0,
  carbon_total: 0,
  exchange_count: 0,
  level: 1,
  level_label: 'LV1',
  next_level: 'LV2',
  next_level_gap: 0,
  progress_percent: 0,
})

const rank = ref({ rank: null, total: 0, community: null })
const logs = ref([])
const logsLoading = ref(false)
const limit = ref(LOG_STEP)

// 碳减排量保留 1 位小数展示，避免浮点长尾
const carbonDisplay = computed(() => Number(summary.value.carbon_total || 0).toFixed(1))
const hasMore = computed(() => logs.value.length >= limit.value && limit.value < LOG_MAX)

function formatDateTime(value) {
  if (!value) return '时间未知'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间未知'
  return date.toLocaleString('zh-CN', { hour12: false })
}

async function loadSummary() {
  try {
    const data = await getCarbonSummary()
    if (data) summary.value = data
  } catch {
    // 错误提示由请求拦截器统一处理
  }
}

async function loadRank() {
  try {
    const data = await getCarbonRank()
    if (data) rank.value = data
  } catch {
    // 同上
  }
}

async function loadLogs() {
  logsLoading.value = true
  try {
    const data = await getCarbonLogs({ limit: limit.value })
    logs.value = data?.list || []
  } catch {
    logs.value = []
  } finally {
    logsLoading.value = false
  }
}

function loadMore() {
  if (limit.value >= LOG_MAX) return
  limit.value = Math.min(limit.value + LOG_STEP, LOG_MAX)
  loadLogs()
}

onMounted(() => {
  loadSummary()
  loadRank()
  loadLogs()
})
</script>

<style scoped>
/* ---------- 汇总头 ---------- */
.summary-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 18px;
}

.summary-tip {
  font-size: 13px;
  color: var(--pc-text-sub);
}

/* 等级徽章：与 Hero 卡同款配色 */
.level-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.4;
  color: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
}

.level-1 {
  background: #8a8a8a;
}

.level-2 {
  background: #3b82f6;
}

.level-3 {
  background: var(--pc-green);
}

.level-4 {
  background: linear-gradient(135deg, var(--peach), color-mix(in srgb, var(--peach) 70%, #ffffff));
}

/* ---------- 三个数字 ---------- */
.stat-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.stat-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 12px 8px;
  background: var(--pc-bg);
  border-radius: 12px;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.2;
  color: var(--pc-green);
}

.stat-unit {
  margin-left: 2px;
  font-size: 13px;
  font-weight: 500;
  color: var(--pc-text-sub);
}

.stat-label {
  font-size: 13px;
  color: var(--pc-text-sub);
}

/* ---------- 进度条 ---------- */
.progress-wrap {
  margin-top: 20px;
}

.progress-track {
  height: 6px;
  border-radius: 999px;
  background: var(--pc-track);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--pc-green), var(--pc-green-alt));
  transition: width 0.3s ease;
}

.progress-text {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--pc-text-sub);
  text-align: center;
}

/* ---------- 社区排名 ---------- */
.rank-line {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.rank-no {
  font-size: 32px;
  font-weight: 700;
  color: var(--pc-green);
}

.rank-unit {
  font-size: 14px;
  color: var(--pc-text-sub);
}

/* ---------- 积分明细 ---------- */
.log-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 48px;
  padding: 12px;
  margin: 0 -12px;
  border-top: 1px solid var(--pc-border);
  border-radius: 8px;
  transition: background 0.2s ease;
}

.log-row:first-of-type {
  border-top: none;
}

.log-row:hover {
  background: var(--pc-bg);
}

.log-main {
  min-width: 0;
}

.log-desc {
  font-size: 14px;
  color: var(--pc-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 380px;
}

.log-time {
  margin-top: 2px;
  font-size: 12px;
  color: var(--pc-text-sub);
}

.log-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  flex-shrink: 0;
}

.log-delta {
  font-size: 16px;
  font-weight: 700;
}

.log-delta.plus {
  color: var(--pc-green);
}

.log-delta.minus {
  color: #dc2626;
}

.log-balance {
  font-size: 12px;
  color: var(--pc-text-sub);
}

.more-wrap {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}

/* ---------- 响应式 ---------- */
@media (max-width: 480px) {
  .log-desc {
    max-width: 180px;
  }

  .stat-grid {
    gap: 8px;
  }
}
</style>

<style>
/* 助老模式：放大明细文字与可点击区域（需命中 html 根级选择器，故非 scoped） */
html.mode-elderly .sub-page .log-desc,
html.mode-elderly .sub-page .summary-tip,
html.mode-elderly .sub-page .log-balance,
html.mode-elderly .sub-page .log-time,
html.mode-elderly .sub-page .stat-label,
html.mode-elderly .sub-page .stat-unit,
html.mode-elderly .sub-page .progress-text,
html.mode-elderly .sub-page .rank-unit {
  font-size: 18px;
}

html.mode-elderly .sub-page .stat-value,
html.mode-elderly .sub-page .rank-no {
  font-size: 32px;
}

html.mode-elderly .sub-page .level-badge,
html.mode-elderly .sub-page .log-delta {
  font-size: 20px;
}

html.mode-elderly .sub-page .log-row {
  min-height: 72px;
}
</style>
