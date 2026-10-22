<template>
  <div class="page-card">
    <div class="page-head">
      <h2 class="page-title">销售记录</h2>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </div>

    <el-table v-loading="loading" :data="rows" border stripe>
      <el-table-column type="expand">
        <template #default="{ row }">
          <div class="expand-box">
            <el-table :data="row.items || []" size="small" border>
              <el-table-column prop="recycle_no" label="回收单号" width="190" />
              <el-table-column prop="item_title" label="物品" min-width="140" />
              <el-table-column prop="points_reward" label="收购积分" width="90" align="center" />
            </el-table>
            <p v-if="!(row.items || []).length" class="sub-text">无明细快照</p>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="sale_no" label="销售单号" width="190" />
      <el-table-column prop="recycler_name" label="回收商" width="150" />
      <el-table-column prop="total_amount" label="销售金额（元）" width="130" align="center">
        <template #default="{ row }">{{ Number(row.total_amount || 0).toFixed(2) }}</template>
      </el-table-column>
      <el-table-column prop="item_count" label="物品数" width="80" align="center" />
      <el-table-column prop="created_at" label="成交时间" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination
        background
        layout="total, prev, pager, next"
        :total="total"
        :page-size="size"
        :current-page="page"
        @current-change="onPageChange"
      />
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'

import { getSaleList } from '@/api/recycle'

const rows = ref([])
const total = ref(0)
const page = ref(1)
const size = 10
const loading = ref(false)

function formatTime(value) {
  if (!value) return '—'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString('zh-CN')
}

async function load() {
  loading.value = true
  try {
    const res = await getSaleList({ page: page.value, size })
    rows.value = res.data?.list || []
    total.value = res.data?.total || 0
  } finally {
    loading.value = false
  }
}

function onPageChange(next) {
  page.value = next
  load()
}

onMounted(load)
</script>

<style scoped>
.page-card {
  padding: 16px 20px;
  background: #fff;
  border-radius: 10px;
}

.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.page-title {
  margin: 0;
  font-size: 17px;
  color: #1f2937;
}

.expand-box {
  padding: 8px 12px;
}

.sub-text {
  margin: 8px 0 0;
  font-size: 12px;
  color: #6b7280;
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
