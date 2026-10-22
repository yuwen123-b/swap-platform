<template>
  <div class="page-card">
    <div class="page-head">
      <h2 class="page-title">回收单管理</h2>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </div>

    <el-form inline class="filter-bar">
      <el-form-item label="状态">
        <el-select v-model="status" placeholder="全部状态" clearable style="width: 160px" @change="onFilterChange">
          <el-option label="待取件" :value="1" />
          <el-option label="已入库" :value="2" />
          <el-option label="已售出" :value="3" />
          <el-option label="已取消" :value="4" />
        </el-select>
      </el-form-item>
    </el-form>

    <el-table v-loading="loading" :data="rows" border stripe>
      <el-table-column prop="recycle_no" label="回收单号" width="190" />
      <el-table-column prop="item_title" label="物品" min-width="140" show-overflow-tooltip />
      <el-table-column prop="user_nickname" label="提交用户" width="110" />
      <el-table-column prop="points_reward" label="发放积分" width="90" align="center" />
      <el-table-column label="取件方式" width="150">
        <template #default="{ row }">
          {{ row.pickup_method_label }}
          <div v-if="row.pickup_address" class="sub-text">{{ row.pickup_address }}</div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">{{ row.status_label }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="提交时间" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="110" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="Number(row.status) === 1"
            type="primary"
            size="small"
            :loading="receivingId === row.id"
            @click="onReceive(row)"
          >
            标记入库
          </el-button>
          <span v-else class="sub-text">—</span>
        </template>
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
import { ElMessage, ElMessageBox } from 'element-plus'

import { getRecycleList, receiveRecycle } from '@/api/recycle'

const rows = ref([])
const total = ref(0)
const page = ref(1)
const size = 10
const status = ref(null)
const loading = ref(false)
const receivingId = ref(null)

function statusTagType(status) {
  return { 1: 'warning', 2: 'primary', 3: 'success', 4: 'info' }[Number(status)] || 'info'
}

function formatTime(value) {
  if (!value) return '—'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString('zh-CN')
}

async function load() {
  loading.value = true
  try {
    const params = { page: page.value, size }
    if (status.value) params.status = status.value
    const res = await getRecycleList(params)
    rows.value = res.data?.list || []
    total.value = res.data?.total || 0
  } finally {
    loading.value = false
  }
}

function onFilterChange() {
  page.value = 1
  load()
}

function onPageChange(next) {
  page.value = next
  load()
}

async function onReceive(row) {
  await ElMessageBox.confirm(
    `确认已收到「${row.item_title || row.recycle_no}」的物品并入库？`,
    '标记入库',
    { type: 'warning' },
  )
  receivingId.value = row.id
  try {
    await receiveRecycle(row.id)
    ElMessage.success('已标记入库')
    load()
  } finally {
    receivingId.value = null
  }
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

.filter-bar {
  margin-bottom: 4px;
}

.sub-text {
  font-size: 12px;
  color: #6b7280;
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
