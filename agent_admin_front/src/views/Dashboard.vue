<template>
  <div>
    <el-row :gutter="16" class="stat-row">
      <el-col v-for="card in cards" :key="card.label" :span="4">
        <div class="stat-card page-card">
          <div class="stat-label">{{ card.label }}</div>
          <div class="stat-value">{{ card.value }}</div>
          <div v-if="card.sub" class="stat-sub">{{ card.sub }}</div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="14">
        <div class="page-card">
          <h3 class="card-title">近 7 天发布与订单趋势</h3>
          <div ref="trendRef" class="chart"></div>
        </div>
      </el-col>
      <el-col :span="10">
        <div class="page-card">
          <h3 class="card-title">热门分类 TOP</h3>
          <div ref="categoryRef" class="chart"></div>
        </div>
      </el-col>
    </el-row>

    <div class="page-card" style="margin-top: 16px">
      <h3 class="card-title">活跃用户 TOP 5</h3>
      <el-table :data="activeUsers" size="small">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="nickname" label="昵称" />
        <el-table-column prop="exchange_count" label="交换次数" width="120" />
        <el-table-column prop="points" label="积分" width="120" />
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts'

import { getOverview, getTrends } from '@/api/dashboard'

const overview = ref({})
const trends = ref({ days: [], item_trend: [], order_trend: [], hot_categories: [], active_users: [] })
const trendRef = ref()
const categoryRef = ref()
let trendChart
let categoryChart

const cards = computed(() => [
  { label: '用户总数', value: overview.value.user_total ?? '-', sub: `今日新增 ${overview.value.today_users ?? 0}` },
  { label: '物品总数', value: overview.value.item_total ?? '-', sub: `今日新增 ${overview.value.today_items ?? 0}` },
  { label: '订单总数', value: overview.value.order_total ?? '-', sub: `今日新增 ${overview.value.today_orders ?? 0}` },
  { label: '帖子总数', value: overview.value.post_total ?? '-' },
  { label: '待审核物品', value: overview.value.pending_items ?? '-' },
  { label: '待处理举报', value: overview.value.pending_reports ?? '-' },
])

const activeUsers = computed(() => trends.value.active_users || [])

function renderCharts() {
  if (trendChart) {
    trendChart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['物品发布', '订单'] },
      grid: { left: 40, right: 20, top: 40, bottom: 30 },
      xAxis: { type: 'category', data: trends.value.days.map((d) => d.slice(5)) },
      yAxis: { type: 'value', minInterval: 1 },
      series: [
        { name: '物品发布', type: 'line', smooth: true, data: trends.value.item_trend, itemStyle: { color: '#2f855a' }, areaStyle: { opacity: 0.15 } },
        { name: '订单', type: 'line', smooth: true, data: trends.value.order_trend, itemStyle: { color: '#f59e0b' }, areaStyle: { opacity: 0.15 } },
      ],
    })
  }
  if (categoryChart) {
    const cats = trends.value.hot_categories || []
    categoryChart.setOption({
      tooltip: {},
      grid: { left: 80, right: 20, top: 20, bottom: 30 },
      xAxis: { type: 'value', minInterval: 1 },
      yAxis: { type: 'category', data: cats.map((c) => c.name).reverse() },
      series: [{ type: 'bar', data: cats.map((c) => c.c).reverse(), itemStyle: { color: '#2f855a', borderRadius: [0, 6, 6, 0] }, barWidth: 18 }],
    })
  }
}

onMounted(async () => {
  trendChart = echarts.init(trendRef.value)
  categoryChart = echarts.init(categoryRef.value)
  const [ov, tr] = await Promise.all([getOverview(), getTrends()])
  overview.value = ov.data || {}
  trends.value = tr.data || trends.value
  renderCharts()
  window.addEventListener('resize', renderCharts)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', renderCharts)
  trendChart?.dispose()
  categoryChart?.dispose()
})
</script>

<style scoped>
.stat-row {
  margin-bottom: 16px;
}

.stat-card {
  text-align: center;
  transition: transform 0.2s, box-shadow 0.2s;
}

.stat-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 6px 20px rgba(47, 133, 90, 0.15);
}

.stat-label {
  font-size: 13px;
  color: #6b7280;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #2f855a;
  margin: 6px 0;
}

.stat-sub {
  font-size: 12px;
  color: #9ca3af;
}

.card-title {
  font-size: 15px;
  color: #374151;
  margin-bottom: 12px;
}

.chart {
  height: 300px;
}
</style>
