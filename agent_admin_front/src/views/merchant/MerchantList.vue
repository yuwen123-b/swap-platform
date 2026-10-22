<template>
  <div class="page-card">
    <!-- Tab：全部 / 待审核 / 已通过 / 已拒绝。后端 status 参数直接用，不做前端过滤 -->
    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <el-tab-pane label="全部" name="all" />
      <el-tab-pane label="待审核" name="0" />
      <el-tab-pane label="已通过" name="1" />
      <el-tab-pane label="已拒绝" name="2" />
    </el-tabs>

    <div class="toolbar">
      <el-input
        v-model="query.keyword"
        placeholder="店铺名 / 联系人 / 地址"
        clearable
        style="width: 260px"
        @keyup.enter="reload"
      />
      <el-button type="primary" @click="reload">搜索</el-button>
      <el-button plain @click="load">刷新</el-button>
      <el-tag v-if="pendingCount > 0" type="warning" effect="light">
        待审核：{{ pendingCount }} 家
      </el-tag>
      <el-tag v-else-if="pendingCount === 0" type="success" effect="light">待审核已清空</el-tag>
    </div>

    <el-table v-loading="loading" :data="list" border :row-class-name="rowClass">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="店铺名" min-width="170" show-overflow-tooltip>
        <template #default="{ row }">{{ textOr(row.name, '未命名店铺') }}</template>
      </el-table-column>
      <el-table-column label="类型" width="110">
        <!-- 空值兜底：待审核申请常常没填类型（真实数据 id=13 即为 NULL） -->
        <template #default="{ row }">
          <el-tag v-if="row.category" size="small" effect="plain">{{ row.category }}</el-tag>
          <span v-else class="muted">未分类</span>
        </template>
      </el-table-column>
      <el-table-column label="联系人" width="140">
        <template #default="{ row }">{{ textOr(row.contact, '未填写') }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">
            {{ textOr(row.status_label, '未知状态') }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="申请时间" width="170">
        <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <!-- role=3（审核员）只读：写按钮整块不渲染，后端也会 403 兜底 -->
          <template v-if="canWrite && row.status === 0">
            <el-button size="small" type="success" @click="onApprove(row)">通过</el-button>
            <el-button size="small" type="danger" @click="openReject(row)">拒绝</el-button>
          </template>
          <el-button size="small" @click="openDetail(row)">详情</el-button>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="暂无商家" />
      </template>
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

    <!-- 审核 / 详情共用同一个弹窗，靠 mode 切换 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="560px">
      <el-descriptions v-if="target" :column="2" border>
        <el-descriptions-item label="店铺名">{{ textOr(target.name, '未命名店铺') }}</el-descriptions-item>
        <el-descriptions-item label="类型">{{ textOr(target.category, '未分类') }}</el-descriptions-item>
        <el-descriptions-item label="联系人">{{ textOr(target.contact, '未填写') }}</el-descriptions-item>
        <el-descriptions-item label="申请时间">{{ fmtTime(target.created_at) }}</el-descriptions-item>
        <el-descriptions-item label="地址" :span="2">{{ textOr(target.address, '未填写') }}</el-descriptions-item>
        <el-descriptions-item label="简介" :span="2">
          {{ textOr(target.description, '未填写') }}
        </el-descriptions-item>
        <el-descriptions-item label="佣金比例">
          {{ target.commission_rate === null || target.commission_rate === undefined
            ? '未设置'
            : `${target.commission_rate}%` }}
        </el-descriptions-item>
        <el-descriptions-item label="当前状态">
          {{ textOr(target.status_label, '未知状态') }}
        </el-descriptions-item>
        <el-descriptions-item v-if="target.audit_reason" label="审核意见" :span="2">
          {{ target.audit_reason }}
        </el-descriptions-item>
      </el-descriptions>

      <el-input
        v-if="dialogMode === 'reject'"
        v-model="rejectReason"
        class="reject-box"
        type="textarea"
        :rows="3"
        placeholder="请填写拒绝原因（商家能看到，请写清楚缺什么材料）"
        maxlength="255"
        show-word-limit
      />

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button
          v-if="dialogMode === 'reject'"
          type="danger"
          :loading="saving"
          @click="onReject"
        >
          确认拒绝
        </el-button>
        <el-button
          v-else-if="dialogMode === 'approve'"
          type="success"
          :loading="saving"
          @click="onApproveConfirm"
        >
          确认通过
        </el-button>
        <el-button v-else @click="dialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { auditMerchant, getMerchantList, getMerchantStats } from '@/api/merchant'
import { useAdminStore } from '@/store/admin'

const store = useAdminStore()
// 权限：role 1 超管 / 2 运营可写，role 3 审核员只读（与后端 write_roles=[1,2] 一致）
const canWrite = computed(() => store.role !== 3)

const list = ref([])
const total = ref(0)
const loading = ref(false)
const saving = ref(false)
const pendingCount = ref(null)

const activeTab = ref('all')
const query = reactive({ page: 1, size: 10, keyword: '', status: undefined })

const STATUS_TYPES = { 0: 'warning', 1: 'success', 2: 'danger', 3: 'info' }
function statusType(status) {
  return STATUS_TYPES[status] || 'info'
}

/** 空值兜底：null / undefined / 空串 → 兜底文案。绝不把 null 渲染到界面上。 */
function textOr(value, fallback) {
  if (value === null || value === undefined) return fallback
  const text = String(value).trim()
  return text === '' ? fallback : text
}

/** 后端 datetime → `YYYY-MM-DD HH:mm:ss`（去掉 ISO 的 T） */
function fmtTime(value) {
  if (!value) return '-'
  return String(value).replace('T', ' ').slice(0, 19)
}

/** 待审核排前面，其余按 id 倒序（新申请更容易被看见） */
function sortRows(rows) {
  return [...rows].sort((a, b) => {
    const pa = a.status === 0 ? 0 : 1
    const pb = b.status === 0 ? 0 : 1
    if (pa !== pb) return pa - pb
    return (b.id || 0) - (a.id || 0)
  })
}

function rowClass({ row }) {
  return row.status === 0 ? 'row-pending' : ''
}

async function load() {
  loading.value = true
  try {
    const res = await getMerchantList(query)
    list.value = sortRows(res.data.list || [])
    total.value = res.data.total || 0
  } finally {
    loading.value = false
  }
}

/** 侧边角标用的待审核总数（整个平台，不限于当前页） */
async function loadPendingCount() {
  try {
    const res = await getMerchantStats()
    pendingCount.value = res.data?.merchants?.pending ?? 0
  } catch {
    /* 角标不是关键路径，失败就不显示 */
  }
}

function reload() {
  query.page = 1
  load()
}

function onTabChange(name) {
  query.status = name === 'all' ? undefined : Number(name)
  reload()
}

// ---------------- 审核 ----------------
const dialogVisible = ref(false)
const dialogMode = ref('detail')
const target = ref(null)
const rejectReason = ref('')

const dialogTitle = computed(
  () => ({ approve: '通过入驻申请', reject: '拒绝入驻申请', detail: '商家详情' })[dialogMode.value],
)

function openDetail(row) {
  target.value = row
  dialogMode.value = 'detail'
  rejectReason.value = ''
  dialogVisible.value = true
}

function onApprove(row) {
  target.value = row
  dialogMode.value = 'approve'
  rejectReason.value = ''
  dialogVisible.value = true
}

function openReject(row) {
  target.value = row
  dialogMode.value = 'reject'
  rejectReason.value = ''
  dialogVisible.value = true
}

async function onApproveConfirm() {
  saving.value = true
  try {
    await auditMerchant(target.value.id, { approved: true })
    ElMessage.success('已通过，该商家现在可以对用户展示')
    dialogVisible.value = false
    await Promise.all([load(), loadPendingCount()])
  } finally {
    saving.value = false
  }
}

async function onReject() {
  const reason = rejectReason.value.trim()
  if (!reason) {
    // 前端先拦一道，后端也会 400（双保险）
    ElMessage.warning('请填写拒绝原因')
    return
  }
  saving.value = true
  try {
    await auditMerchant(target.value.id, { approved: false, reason })
    ElMessage.success('已拒绝该入驻申请')
    dialogVisible.value = false
    await Promise.all([load(), loadPendingCount()])
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  load()
  loadPendingCount()
})
</script>

<style scoped>
.muted {
  color: #9ca3af;
}

.reject-box {
  margin-top: 16px;
}

/* 待审核行加底色，方便管理员一眼找到 */
.page-card :deep(.row-pending) {
  background: #fffbf0;
}

.page-card :deep(.row-pending:hover > td.el-table__cell) {
  background: #fef6e6;
}
</style>
