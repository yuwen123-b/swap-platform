<template>
  <div>
    <!-- 统计卡 -->
    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="5">
        <div class="stat page-card">
          <div class="label">总反馈数</div>
          <div class="value">{{ stats.total ?? '-' }}</div>
        </div>
      </el-col>
      <el-col :span="5">
        <div class="stat page-card">
          <div class="label">良好</div>
          <div class="value tone-pos">{{ stats.positive ?? '-' }}</div>
        </div>
      </el-col>
      <el-col :span="5">
        <div class="stat page-card">
          <div class="label">中性</div>
          <div class="value tone-neu">{{ stats.neutral ?? '-' }}</div>
        </div>
      </el-col>
      <el-col :span="5">
        <div class="stat page-card">
          <div class="label">差</div>
          <div class="value tone-neg">{{ stats.negative ?? '-' }}</div>
        </div>
      </el-col>
      <el-col :span="4">
        <div class="stat page-card">
          <div class="label">平均评分</div>
          <div class="value">{{ stats.avg_rating ?? '-' }}</div>
        </div>
      </el-col>
    </el-row>

    <!-- 图表 -->
    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="10">
        <div class="page-card">
          <h3 class="card-title">情感分布</h3>
          <div ref="pieRef" class="chart chart-sm"></div>
        </div>
      </el-col>
      <el-col :span="14">
        <div class="page-card">
          <h3 class="card-title">近 7 日反馈情感趋势</h3>
          <div ref="trendRef" class="chart"></div>
        </div>
      </el-col>
    </el-row>

    <!-- 反馈列表 -->
    <div class="page-card">
      <div class="toolbar">
        <el-select v-model="query.sentiment" placeholder="情感分类" clearable style="width: 140px">
          <el-option value="positive" label="良好" />
          <el-option value="neutral" label="中性" />
          <el-option value="negative" label="差" />
        </el-select>
        <el-button type="primary" @click="load">查询</el-button>
      </div>

      <el-table v-loading="loading" :data="list" border>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="user_nickname" label="用户" width="130">
          <template #default="{ row }">{{ row.user_nickname || `用户${row.user_id}` }}</template>
        </el-table-column>
        <el-table-column label="评分" width="150">
          <template #default="{ row }">
            <el-rate :model-value="row.rating" disabled size="small" />
          </template>
        </el-table-column>
        <el-table-column prop="content" label="反馈内容" min-width="240" show-overflow-tooltip />
        <el-table-column label="情感判定" width="120">
          <template #default="{ row }">
            <el-tag :type="sentimentType(row.sentiment)" size="small">{{ sentimentText(row.sentiment) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="引擎" width="90">
          <template #default="{ row }">
            <el-tag :type="row.sentiment_engine === 'llm' ? 'warning' : 'info'" size="small" effect="plain">
              {{ row.sentiment_engine === 'llm' ? 'LLM' : '词典' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="sentiment_score" label="分值" width="90" />
        <el-table-column prop="created_at" label="时间" width="170" />
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.size"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="load"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import * as echarts from 'echarts'

import { getFeedbackList, getFeedbackStats } from '@/api/feedback'

const stats = ref({})
const list = ref([])
const total = ref(0)
const loading = ref(false)
const query = reactive({ page: 1, size: 10, sentiment: undefined })

const pieRef = ref()
const trendRef = ref()
let pieChart
let trendChart

const SENTIMENT_TEXT = { positive: '良好', neutral: '中性', negative: '差' }
const SENTIMENT_TYPE = { positive: 'success', neutral: 'info', negative: 'danger' }

function sentimentText(s) {
  return SENTIMENT_TEXT[s] || '中性'
}

function sentimentType(s) {
  return SENTIMENT_TYPE[s] || 'info'
}

function renderCharts() {
  if (pieChart) {
    pieChart.setOption({
      tooltip: { trigger: 'item' },
      legend: { bottom: 0 },
      series: [
        {
          name: '情感分布',
          type: 'pie',
          radius: ['40%', '66%'],
          center: ['50%', '44%'],
          itemStyle: { borderRadius: 6 },
          label: { formatter: '{b}: {c}' },
          data: [
            { name: '良好', value: stats.value.positive || 0, itemStyle: { color: '#2f855a' } },
            { name: '中性', value: stats.value.neutral || 0, itemStyle: { color: '#9ca3af' } },
            { name: '差', value: stats.value.negative || 0, itemStyle: { color: '#dc2626' } },
          ],
        },
      ],
    })
  }
  if (trendChart) {
    const trend = stats.value.trend || []
    trendChart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['良好', '中性', '差'] },
      grid: { left: 40, right: 20, top: 40, bottom: 30 },
      xAxis: { type: 'category', data: trend.map((t) => t.day) },
      yAxis: { type: 'value', minInterval: 1 },
      series: [
        { name: '良好', type: 'line', smooth: true, data: trend.map((t) => t.positive), itemStyle: { color: '#2f855a' }, areaStyle: { opacity: 0.15 } },
        { name: '中性', type: 'line', smooth: true, data: trend.map((t) => t.neutral), itemStyle: { color: '#9ca3af' } },
        { name: '差', type: 'line', smooth: true, data: trend.map((t) => t.negative), itemStyle: { color: '#dc2626' } },
      ],
    })
  }
}

async function load() {
  loading.value = true
  try {
    const res = await getFeedbackList(query)
    list.value = res.data.list
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  const res = await getFeedbackStats()
  stats.value = res.data || {}
  await nextTick()
  pieChart = echarts.init(pieRef.value)
  trendChart = echarts.init(trendRef.value)
  renderCharts()
  window.addEventListener('resize', onResize)
  load()
})

function onResize() {
  pieChart?.resize()
  trendChart?.resize()
}

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  pieChart?.dispose()
  trendChart?.dispose()
})
</script>

<style scoped>
.stat {
  text-align: center;
}

.label {
  font-size: 13px;
  color: #6b7280;
}

.value {
  font-size: 26px;
  font-weight: 700;
  color: #2f855a;
  margin-top: 6px;
}

.tone-pos { color: #2f855a; }
.tone-neu { color: #6b7280; }
.tone-neg { color: #dc2626; }

.card-title {
  font-size: 15px;
  color: #374151;
  margin-bottom: 12px;
}

.chart {
  width: 100%;
  height: 280px;
}

.chart-sm {
  height: 260px;
}

.toolbar {
  display: flex;
  gap: 10px;
  margin-bottom: 14px;
}

.pager {
  margin-top: 14px;
  display: flex;
  justify-content: flex-end;
}
</style>
