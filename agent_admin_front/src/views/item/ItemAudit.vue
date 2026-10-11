<template>
  <div class="page-card">
    <div class="toolbar">
      <el-tag type="warning" effect="light">待审核物品：{{ total }} 件</el-tag>
      <el-button type="primary" plain @click="load">刷新</el-button>
    </div>

    <el-table v-loading="loading" :data="list" border>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="title" label="物品名称" min-width="180" show-overflow-tooltip />
      <el-table-column prop="category_name" label="分类" width="110" />
      <el-table-column prop="publisher" label="发布者" width="110" />
      <el-table-column prop="price" label="参考价(元)" width="110" />
      <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
      <el-table-column prop="created_at" label="提交时间" width="170" />
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="success" @click="onApprove(row)">通过</el-button>
          <el-button size="small" type="danger" @click="openReject(row)">拒绝</el-button>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="暂无待审核物品" />
      </template>
    </el-table>

    <div class="pager">
      <el-pagination v-model:current-page="query.page" v-model:page-size="query.size" :total="total" layout="total, prev, pager, next" @current-change="load" />
    </div>

    <el-dialog v-model="rejectVisible" title="拒绝上架" width="420px">
      <el-input v-model="rejectReason" type="textarea" :rows="3" placeholder="请填写拒绝理由（将展示给发布者）" maxlength="255" show-word-limit />
      <template #footer>
        <el-button @click="rejectVisible = false">取消</el-button>
        <el-button type="danger" :loading="saving" @click="onReject">确认拒绝</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { auditItem, getAuditItems } from '@/api/item'

const list = ref([])
const total = ref(0)
const loading = ref(false)
const saving = ref(false)
const query = reactive({ page: 1, size: 10 })

const rejectVisible = ref(false)
const rejectReason = ref('')
const rejectTarget = ref(null)

async function load() {
  loading.value = true
  try {
    const res = await getAuditItems(query)
    list.value = res.data.list
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

async function onApprove(row) {
  await ElMessageBox.confirm(`确认通过「${row.title}」的审核并上架？`, '审核确认', { type: 'success' })
  await auditItem(row.id, { approved: true })
  ElMessage.success('已通过并上架')
  load()
}

function openReject(row) {
  rejectTarget.value = row
  rejectReason.value = ''
  rejectVisible.value = true
}

async function onReject() {
  if (!rejectReason.value.trim()) {
    ElMessage.warning('请填写拒绝理由')
    return
  }
  saving.value = true
  try {
    await auditItem(rejectTarget.value.id, { approved: false, reason: rejectReason.value.trim() })
    ElMessage.success('已拒绝')
    rejectVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>
