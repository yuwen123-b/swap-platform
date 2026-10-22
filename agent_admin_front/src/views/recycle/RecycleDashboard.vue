<template>
  <div class="recycle-dashboard">
    <div class="page-head">
      <h2 class="page-title">平台回收 · 运营数据</h2>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </div>

    <!-- 4 个核心指标 -->
    <el-row :gutter="14">
      <el-col v-for="card in metricCards" :key="card.label" :xs="12" :sm="6">
        <div class="metric-card">
          <div class="metric-label">{{ card.label }}</div>
          <div class="metric-value" :class="card.danger && isNegative ? 'metric-danger' : ''">
            {{ card.value }}
          </div>
          <div class="metric-sub">{{ card.sub }}</div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="14" class="chart-row">
      <el-col :xs="24" :md="10">
        <div class="panel">
          <h3 class="panel-title">回收单状态分布</h3>
          <div ref="pieRef" class="pie-box"></div>
        </div>
      </el-col>
      <el-col :xs="24" :md="14">
        <div class="panel">
          <h3 class="panel-title">回收商贡献排行（按销售金额 TOP 10）</h3>
          <el-table :data="stats.top_recyclers || []" size="small" border>
            <el-table-column type="index" label="#" width="46" align="center" />
            <el-table-column prop="recycler_name" label="回收商" min-width="130" />
            <el-table-column prop="total_amount" label="累计金额（元）" width="130" align="center">
              <template #default="{ row }">{{ Number(row.total_amount || 0).toFixed(2) }}</template>
            </el-table-column>
            <el-table-column prop="sale_count" label="成交笔数" width="90" align="center" />
            <el-table-column prop="item_count" label="物品数" width="80" align="center" />
          </el-table>
          <p v-if="!(stats.top_recyclers || []).length" class="empty-hint">
            暂无销售记录，成交后这里会出现排行
          </p>
        </div>
      </el-col>
    </el-row>

    <p class="cost-note">
      成本口径：累计发放积分 × 汇率（当前 {{ stats.points_to_yuan ?? 0.01 }} 元/积分，与商家结算同源）；
      已取消的回收单不计入成本。
    </p>
  </div>
</template>

<script setup>
import * as echarts from 'echarts'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import { getRecycleStats } from '@/api/recycle'

const stats = ref({})
const loading = ref(false)
const pieRef = ref(null)
let pieChart = null

const isNegative = computed(() => Number(stats.value.gross_profit) < 0)

const metricCards = computed(() => {
  const s = stats.value
  const gross = Number(s.gross_profit || 0)
  return [
    { label: '累计入库', value: s.total_received ?? 0, sub: `待取件 ${s.pending_pickup ?? 0} 件` },
    { label: '累计售出', value: s.total_sold ?? 0, sub: '已卖给回收商' },
    { label: '累计发积分', value: s.total_points_issued ?? 0, sub: `折合成本 ¥${Number(s.total_cost || 0).toFixed(2)}` },
    {
      label: '毛利',
      value: `¥${gross.toFixed(2)}`,
      sub: `收入 ¥${Number(s.total_revenue || 0).toFixed(2)}`,
      danger: true,
    },
  ]
})

const STATUS_META = [
  { status: 1, name: '待取件', color: '#f59e0b' },
  { status: 2, name: '已入库', color: '#3b82f6' },
  { status: 3, name: '已售出', color: '#16a34a' },
  { status: 4, name: '已取消', color: '#9ca3af' },
]

function renderPie() {
  if (!pieRef.value) return
  if (!pieChart) pieChart = echarts.init(pieRef.value)
  const data = (stats.value.status_distribution || []).map((d) => {
    const meta = STATUS_META.find((m) => m.status === Number(d.status)) || {}
    return { name: meta.name || d.status_label || String(d.status), value: d.count || 0, itemStyle: { color: meta.color } }
  })
  pieChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, icon: 'circle' },
    series: [
      {
        type: 'pie',
        radius: ['42%', '68%'],
        center: ['50%', '44%'],
        label: { show: true, formatter: '{b}\n{c}' },
        data,
      },
    ],
  })
}

async function load() {
  loading.value = true
  try {
    const res = await getRecycleStats()
    stats.value = res.data || {}
    await nextTick()
    renderPie()
  } finally {
    loading.value = false
  }
}

function onResize() {
  pieChart?.resize()
}

onMounted(() => {
  load()
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  pieChart?.dispose()
  pieChart = null
})
</script>

<style scoped>
.recycle-dashboard {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.page-title {
  margin: 0;
  font-size: 17px;
  color: #1f2937;
}

.metric-card {
  padding: 16px;
  background: #fff;
  border-radius: 10px;
}

.metric-label {
  font-size: 13px;
  color: #6b7280;
}

.metric-value {
  margin-top: 6px;
  font-size: 26px;
  font-weight: 700;
  color: #1f2937;
  font-variant-numeric: tabular-nums;
}

.metric-danger {
  color: #b45309;
}

.metric-sub {
  margin-top: 4px;
  font-size: 12px;
  color: #9ca3af;
}

.chart-row {
  margin-top: 0 !important;
}

.panel {
  padding: 16px;
  background: #fff;
  border-radius: 10px;
}

.panel-title {
  margin: 0 0 10px;
  font-size: 15px;
  color: #1f2937;
}

.pie-box {
  width: 100%;
  height: 300px;
}

.empty-hint {
  margin: 10px 0 0;
  font-size: 12.5px;
  color: #9ca3af;
}

.cost-note {
  margin: 0;
  font-size: 12px;
  color: #6b7280;
}
</style>
