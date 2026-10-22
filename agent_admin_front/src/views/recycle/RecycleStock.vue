<template>
  <div class="page-card">
    <div class="page-head">
      <div>
        <h2 class="page-title">平台库存</h2>
        <p class="page-desc">已入库待售的回收物品；勾选后可批量卖给回收商（默认不跨页保留勾选）</p>
      </div>
      <el-button type="primary" :disabled="!selection.length" @click="openSell">
        批量卖给回收商（{{ selection.length }}）
      </el-button>
    </div>

    <el-table
      ref="tableRef"
      v-loading="loading"
      :data="rows"
      border
      stripe
      @selection-change="onSelectionChange"
    >
      <el-table-column type="selection" width="46" />
      <el-table-column prop="recycle_no" label="回收单号" width="190" />
      <el-table-column prop="item_title" label="物品" min-width="140" show-overflow-tooltip />
      <el-table-column prop="user_nickname" label="提交用户" width="110" />
      <el-table-column prop="points_reward" label="收购积分" width="90" align="center" />
      <el-table-column prop="received_at" label="入库时间" width="170">
        <template #default="{ row }">{{ formatTime(row.received_at) }}</template>
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

    <!-- 批量销售：选回收商 + 填金额；确认前展示合计提示，避免运营填错量级 -->
    <el-dialog v-model="sellVisible" title="批量卖给回收商" width="460px">
      <el-form label-width="90px">
        <el-form-item label="已选物品">
          <span>共 <strong>{{ selection.length }}</strong> 件</span>
        </el-form-item>
        <el-form-item label="回收商" required>
          <el-select v-model="sellForm.recycler_id" placeholder="选择回收商" style="width: 100%">
            <el-option
              v-for="r in recyclers"
              :key="r.id"
              :label="`${r.name}（${r.address || '地址未填'}）`"
              :value="r.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="销售金额" required>
          <el-input-number
            v-model="sellForm.total_amount"
            :min="0"
            :precision="2"
            :step="10"
            controls-position="right"
            style="width: 100%"
          />
          <p class="field-tip">元；回收成本按 100 积分 = 1 元折算，注意别低于成本</p>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="sellVisible = false">取消</el-button>
        <el-button type="primary" :loading="selling" @click="confirmSell">确认成交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { getRecyclers, getRecycleList, sellToRecycler } from '@/api/recycle'

// 「平台库存」= 已入库（status=2），复用回收单列表接口，不新增后端端点
const STATUS_STOCKED = 2

const tableRef = ref(null)
const rows = ref([])
const total = ref(0)
const page = ref(1)
const size = 10
const loading = ref(false)

const selection = ref([])
const recyclers = ref([])
const sellVisible = ref(false)
const selling = ref(false)
const sellForm = ref({ recycler_id: null, total_amount: 0 })

function formatTime(value) {
  if (!value) return '—'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString('zh-CN')
}

async function load() {
  loading.value = true
  try {
    const res = await getRecycleList({ status: STATUS_STOCKED, page: page.value, size })
    rows.value = res.data?.list || []
    total.value = res.data?.total || 0
  } finally {
    loading.value = false
  }
}

function onSelectionChange(list) {
  selection.value = list
}

function onPageChange(next) {
  // 刻意不跨页保留勾选：避免翻页后误把上百条一起提交（后端上限 100 兜底）
  page.value = next
  load()
}

async function openSell() {
  if (!recyclers.value.length) {
    try {
      const res = await getRecyclers()
      recyclers.value = res.data || []
    } catch {
      recyclers.value = []
    }
  }
  if (!recyclers.value.length) {
    ElMessage.warning('暂无可用回收商（需「类型为回收且已通过审核」的商家），请先在商家管理中配置')
    return
  }
  sellForm.value = { recycler_id: recyclers.value[0]?.id ?? null, total_amount: 0 }
  sellVisible.value = true
}

async function confirmSell() {
  const { recycler_id, total_amount } = sellForm.value
  if (!recycler_id) {
    ElMessage.warning('请选择回收商')
    return
  }
  if (!total_amount || total_amount <= 0) {
    ElMessage.warning('销售金额必须大于 0')
    return
  }
  const names = selection.value.map((r) => r.item_title).join('、')
  try {
    await ElMessageBox.confirm(
      `共 ${selection.value.length} 件（${names.slice(0, 60)}${names.length > 60 ? '…' : ''}），合计 ${Number(total_amount).toFixed(2)} 元，确认成交？`,
      '确认成交',
      { type: 'warning' },
    )
  } catch {
    return
  }
  selling.value = true
  try {
    const res = await sellToRecycler({
      recycler_id,
      recycle_ids: selection.value.map((r) => r.id),
      total_amount,
    })
    ElMessage.success(`成交：${res.data?.sale_no || ''}，共 ${res.data?.item_count ?? selection.value.length} 件`)
    sellVisible.value = false
    selection.value = []
    load()
  } finally {
    selling.value = false
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
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.page-title {
  margin: 0;
  font-size: 17px;
  color: #1f2937;
}

.page-desc {
  margin: 4px 0 0;
  font-size: 12.5px;
  color: #6b7280;
}

.field-tip {
  margin: 4px 0 0;
  font-size: 12px;
  color: #6b7280;
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
