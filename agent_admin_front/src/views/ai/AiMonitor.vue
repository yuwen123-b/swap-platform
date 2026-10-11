<template>
  <div>
    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="6">
        <div class="stat page-card">
          <div class="label">累计调用</div>
          <div class="value">{{ stats.total ?? '-' }}</div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat page-card">
          <div class="label">成功率</div>
          <div class="value">{{ stats.success_rate != null ? (stats.success_rate * 100).toFixed(1) + '%' : '-' }}</div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat page-card">
          <div class="label">平均耗时</div>
          <div class="value">{{ stats.avg_duration_ms ?? '-' }} ms</div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat page-card">
          <div class="label">今日调用</div>
          <div class="value">{{ stats.today ?? '-' }}</div>
        </div>
      </el-col>
    </el-row>

    <div v-if="alerts.length" class="page-card" style="margin-bottom: 16px">
      <h3 class="title">
        <el-icon color="#dc2626"><WarningFilled /></el-icon>
        异常告警（最近 {{ alerts.length }} 条）
      </h3>
      <el-table :data="alerts" size="small" border>
        <el-table-column prop="api_name" label="接口" width="140" />
        <el-table-column prop="error_msg" label="错误信息" min-width="220" show-overflow-tooltip />
        <el-table-column prop="duration_ms" label="耗时(ms)" width="100" />
        <el-table-column prop="created_at" label="时间" width="170" />
      </el-table>
    </div>

    <div class="page-card">
      <div class="toolbar">
        <el-select v-model="query.api_name" placeholder="接口名称" clearable style="width: 160px">
          <el-option v-for="a in apiNames" :key="a" :value="a" :label="a" />
        </el-select>
        <el-select v-model="query.status" placeholder="状态" clearable style="width: 120px">
          <el-option :value="1" label="成功" />
          <el-option :value="0" label="失败" />
        </el-select>
        <el-button type="primary" @click="load">查询</el-button>
      </div>

      <el-table v-loading="loading" :data="list" border>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="api_name" label="接口" width="130" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 1 ? 'success' : 'danger'" size="small">{{ row.status === 1 ? '成功' : '失败' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="duration_ms" label="耗时(ms)" width="100" />
        <el-table-column prop="error_msg" label="错误" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.error_msg || '-' }}</template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" width="170" />
      </el-table>

      <div class="pager">
        <el-pagination v-model:current-page="query.page" v-model:page-size="query.size" :total="total" layout="total, prev, pager, next" @current-change="load" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { getAiAlerts, getAiLogs, getAiStats } from '@/api/ai'

const stats = ref({})
const alerts = ref([])
const list = ref([])
const total = ref(0)
const loading = ref(false)
const query = reactive({ page: 1, size: 10, api_name: undefined, status: undefined })

const apiNames = computed(() => (stats.value.by_api || []).map((a) => a.api_name))

async function load() {
  loading.value = true
  try {
    const res = await getAiLogs(query)
    list.value = res.data.list
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  const [s, a] = await Promise.all([getAiStats(), getAiAlerts({ limit: 10 })])
  stats.value = s.data || {}
  alerts.value = a.data || []
  load()
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

.title {
  font-size: 15px;
  color: #374151;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
}
</style>
