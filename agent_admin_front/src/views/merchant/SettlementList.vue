<template>
  <div class="page-card">
    <!-- 平台累计三卡：来源于 /merchant/stats（第三张是「已结算」口径） -->
    <div class="stat-row">
      <el-card shadow="never" class="stat-card">
        <div class="stat-label">累计核销单数</div>
        <div class="stat-value">{{ stats.redeemed }}</div>
        <div class="stat-hint">平台全部商家的已核销兑换单</div>
      </el-card>
      <el-card shadow="never" class="stat-card">
        <div class="stat-label">累计积分消耗</div>
        <div class="stat-value">{{ stats.points_consumed }}</div>
        <div class="stat-hint">已核销订单消耗的积分合计</div>
      </el-card>
      <el-card shadow="never" class="stat-card">
        <div class="stat-label">累计佣金（已结算）</div>
        <div class="stat-value">¥{{ money(stats.commission_total) }}</div>
        <div class="stat-hint">已完成结算的佣金合计，不含待结算</div>
      </el-card>
    </div>

    <div class="toolbar">
      <span class="period-label">结算周期</span>
      <el-date-picker
        v-model="period"
        type="month"
        value-format="YYYY-MM"
        placeholder="选择月份"
        :clearable="false"
        style="width: 150px"
        @change="loadPreview"
      />
      <el-button plain @click="loadAll">刷新</el-button>
      <el-tag v-if="preview.pending_merchants > 0" type="warning" effect="light">
        待结算：{{ preview.pending_merchants }} 家 / ¥{{ money(preview.pending_commission) }}
      </el-tag>
      <el-tag v-else type="success" effect="light">本期已全部结算</el-tag>
      <span v-if="!canWrite" class="muted">（审核员为只读角色，无结算权限）</span>
    </div>

    <!-- 商家结算列表：数字来自只读预览接口，口径与真实结算完全一致 -->
    <el-table v-loading="loading" :data="preview.list" border class="preview-table">
      <el-table-column label="店铺名" min-width="170" show-overflow-tooltip>
        <template #default="{ row }">{{ textOr(row.name, '未命名店铺') }}</template>
      </el-table-column>
      <el-table-column label="核销单数" width="110">
        <template #default="{ row }">{{ row.redemption_count }}</template>
      </el-table-column>
      <el-table-column label="积分总额" width="110">
        <template #default="{ row }">
          <span class="points">{{ row.points_total }}</span>
        </template>
      </el-table-column>
      <el-table-column label="佣金" width="110">
        <template #default="{ row }">
          <span class="money">¥{{ money(row.commission_amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="佣金比例" width="100">
        <template #default="{ row }">{{ row.commission_rate }}%</template>
      </el-table-column>
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="row.settled ? 'success' : 'warning'" size="small">
            {{ row.settled ? '本期已结算' : '待结算' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="结算时间" width="170">
        <template #default="{ row }">{{ row.settled ? fmtTime(row.settled_at) : '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="130" fixed="right">
        <template #default="{ row }">
          <!-- role=3 不渲染结算按钮；已结算 / 本期无单的也禁用 -->
          <el-button
            v-if="canWrite"
            size="small"
            type="primary"
            :disabled="row.settled || row.redemption_count === 0"
            :title="settleDisabledReason(row)"
            @click="openSettle(row)"
          >
            {{ row.settled ? '已结算' : '结算' }}
          </el-button>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="该周期没有已通过审核的商家" />
      </template>
    </el-table>

    <!-- 历史结算记录 -->
    <div class="section-title">
      历史结算记录
      <span class="muted-inline">共 {{ history.total }} 条</span>
    </div>
    <el-table v-loading="historyLoading" :data="history.list" border class="history-table">
      <el-table-column label="店铺名" min-width="170" show-overflow-tooltip>
        <template #default="{ row }">{{ textOr(row.merchant_name, '未命名店铺') }}</template>
      </el-table-column>
      <el-table-column prop="period" label="周期" width="110" />
      <el-table-column prop="redemption_count" label="核销单数" width="110" />
      <el-table-column prop="points_total" label="积分总额" width="110" />
      <el-table-column label="佣金" width="110">
        <template #default="{ row }">¥{{ money(row.commission_amount) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="row.status === 1 ? 'success' : 'warning'" size="small">
            {{ textOr(row.status_label, '未知状态') }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="结算时间" width="170">
        <template #default="{ row }">{{ fmtTime(row.settled_at) }}</template>
      </el-table-column>
      <template #empty>
        <el-empty description="还没有结算记录" />
      </template>
    </el-table>

    <div class="pager">
      <el-pagination
        v-model:current-page="historyQuery.page"
        v-model:page-size="historyQuery.size"
        :total="history.total"
        layout="total, prev, pager, next"
        @current-change="loadHistory"
      />
    </div>

    <!-- 二次确认：数字全部来自预览接口，与真实结算同口径 -->
    <el-dialog v-model="settleVisible" title="确认结算" width="520px">
      <el-alert
        class="tip"
        type="warning"
        :closable="false"
        show-icon
        title="结算不可撤销"
        description="确认后将写入结算记录，同一商家同一周期重复结算不会重复计账。"
      />
      <el-descriptions v-if="target" :column="1" border>
        <el-descriptions-item label="商家">{{ textOr(target.name, '未命名店铺') }}</el-descriptions-item>
        <el-descriptions-item label="结算周期">{{ preview.period }}</el-descriptions-item>
        <el-descriptions-item label="核销单数">{{ target.redemption_count }} 单</el-descriptions-item>
        <el-descriptions-item label="积分总额">{{ target.points_total }}</el-descriptions-item>
        <el-descriptions-item label="佣金比例">{{ target.commission_rate }}%</el-descriptions-item>
        <el-descriptions-item label="应付佣金">
          <span class="money big">¥{{ money(target.commission_amount) }}</span>
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="settleVisible = false">取消</el-button>
        <el-button type="primary" :loading="settling" @click="onSettle">确认结算</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  getMerchantStats,
  getSettlementPreview,
  getSettlements,
  triggerSettleOne,
} from '@/api/merchant'
import { useAdminStore } from '@/store/admin'

const store = useAdminStore()
// role 1 超管 / 2 运营可结算，role 3 审核员只读（与后端 write_roles=[1,2] 一致）
const canWrite = computed(() => store.role !== 3)

const loading = ref(false)
const settling = ref(false)
const historyLoading = ref(false)

const stats = reactive({ redeemed: 0, points_consumed: 0, commission_total: 0 })
const preview = reactive({
  period: '',
  pending_merchants: 0,
  pending_commission: 0,
  list: [],
})
const history = reactive({ total: 0, list: [] })
const historyQuery = reactive({ page: 1, size: 10 })

const period = ref(currentMonth())
const settleVisible = ref(false)
const target = ref(null)

function currentMonth() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

function textOr(value, fallback) {
  if (value === null || value === undefined) return fallback
  const text = String(value).trim()
  return text === '' ? fallback : text
}

function fmtTime(value) {
  if (!value) return '-'
  return String(value).replace('T', ' ').slice(0, 19)
}

function money(value) {
  return Number(value || 0).toFixed(2)
}

function settleDisabledReason(row) {
  if (row.settled) return '本期已结算'
  if (row.redemption_count === 0) return '本期没有需要结算的核销单'
  return ''
}

async function loadStats() {
  const res = await getMerchantStats()
  stats.redeemed = res.data?.redemptions?.redeemed ?? 0
  stats.points_consumed = res.data?.points_consumed ?? 0
  stats.commission_total = res.data?.commission_total ?? 0
}

async function loadPreview() {
  loading.value = true
  try {
    const res = await getSettlementPreview({ period: period.value })
    preview.period = res.data.period
    preview.pending_merchants = res.data.pending_merchants
    preview.pending_commission = res.data.pending_commission
    preview.list = res.data.list || []
  } finally {
    loading.value = false
  }
}

async function loadHistory() {
  historyLoading.value = true
  try {
    const res = await getSettlements(historyQuery)
    history.list = res.data.list || []
    history.total = res.data.total || 0
  } finally {
    historyLoading.value = false
  }
}

function loadAll() {
  loadStats()
  loadPreview()
  loadHistory()
}

function openSettle(row) {
  target.value = row
  settleVisible.value = true
}

async function onSettle() {
  settling.value = true
  try {
    const res = await triggerSettleOne(target.value.merchant_id, { period: preview.period })
    const already = res.data?.already_settled
    ElMessage.success(
      already
        ? `「${textOr(target.value.name, '该商家')}」本期此前已结算，未重复计账`
        : `已结算「${textOr(target.value.name, '该商家')}」${preview.period}：${res.data?.redemption_count ?? 0} 单 / ¥${money(res.data?.commission_amount)}`,
    )
    settleVisible.value = false
    historyQuery.page = 1
    loadStats()
    loadPreview()
    loadHistory()
  } finally {
    settling.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.stat-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 14px;
  margin-bottom: 18px;
}

.stat-card {
  border: 1px solid #e5e7eb;
  border-radius: 10px;
}

.stat-label {
  font-size: 13px;
  color: #6b7280;
}

.stat-value {
  font-size: 26px;
  font-weight: 700;
  color: var(--el-color-primary);
  margin: 6px 0 4px;
}

.stat-hint {
  font-size: 12px;
  color: #9ca3af;
}

.period-label {
  font-size: 14px;
  color: #4b5563;
}

.section-title {
  margin: 24px 0 12px;
  font-size: 15px;
  font-weight: 600;
  color: #374151;
}

.muted {
  color: #9ca3af;
  font-size: 13px;
}

.muted-inline {
  color: #9ca3af;
  font-size: 13px;
  font-weight: 400;
  margin-left: 6px;
}

.points {
  color: var(--el-color-primary);
  font-weight: 600;
}

.money {
  color: #d97706;
  font-weight: 600;
}

.money.big {
  font-size: 18px;
}

.tip {
  margin-bottom: 14px;
}
</style>
