<template>
  <div class="page-card">
    <div class="toolbar">
      <el-select v-model="query.status" placeholder="状态" clearable style="width: 130px">
        <el-option :value="0" label="待处理" />
        <el-option :value="1" label="已处理" />
        <el-option :value="2" label="已驳回" />
      </el-select>
      <el-button type="primary" @click="load">查询</el-button>
    </div>

    <el-table v-loading="loading" :data="list" border>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="reporter_name" label="举报人" width="110" />
      <el-table-column label="举报对象" width="160">
        <template #default="{ row }">
          <el-tag size="small" effect="plain">{{ targetTypeText[row.target_type] }}</el-tag>
          <span style="margin-left: 6px">#{{ row.target_id }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="reason" label="举报理由" min-width="220" show-overflow-tooltip />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType[row.status]" size="small">{{ statusText[row.status] }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="handler_name" label="处理人" width="100">
        <template #default="{ row }">{{ row.handler_name || '-' }}</template>
      </el-table-column>
      <el-table-column prop="result" label="处理结果" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">{{ row.result || '-' }}</template>
      </el-table-column>
      <el-table-column prop="created_at" label="举报时间" width="170" />
      <el-table-column label="操作" width="170" fixed="right">
        <template #default="{ row }">
          <template v-if="row.status === 0">
            <el-button size="small" type="success" @click="openHandle(row, 'resolve')">处理</el-button>
            <el-button size="small" type="info" @click="openHandle(row, 'dismiss')">驳回</el-button>
          </template>
          <span v-else class="done">已办结</span>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination v-model:current-page="query.page" v-model:page-size="query.size" :total="total" layout="total, prev, pager, next" @current-change="load" />
    </div>

    <el-dialog v-model="dialogVisible" :title="action === 'resolve' ? '处理举报' : '驳回举报'" width="420px">
      <el-input v-model="result" type="textarea" :rows="3" placeholder="处理结果说明" maxlength="255" show-word-limit />
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button :type="action === 'resolve' ? 'success' : 'info'" :loading="saving" @click="onHandle">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { getReports, handleReport } from '@/api/community'

const targetTypeText = { 1: '物品', 2: '帖子', 3: '用户' }
const statusText = { 0: '待处理', 1: '已处理', 2: '已驳回' }
const statusType = { 0: 'warning', 1: 'success', 2: 'info' }

const list = ref([])
const total = ref(0)
const loading = ref(false)
const saving = ref(false)
const query = reactive({ page: 1, size: 10, status: undefined })

const dialogVisible = ref(false)
const action = ref('resolve')
const result = ref('')
const target = ref(null)

async function load() {
  loading.value = true
  try {
    const res = await getReports(query)
    list.value = res.data.list
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

function openHandle(row, act) {
  target.value = row
  action.value = act
  result.value = ''
  dialogVisible.value = true
}

async function onHandle() {
  saving.value = true
  try {
    await handleReport(target.value.id, { action: action.value, result: result.value.trim() })
    ElMessage.success(action.value === 'resolve' ? '已处理' : '已驳回')
    dialogVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.done {
  color: #9ca3af;
  font-size: 13px;
}
</style>
