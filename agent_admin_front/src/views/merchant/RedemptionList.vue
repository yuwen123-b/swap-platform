<template>
  <div class="page-card">
    <el-alert
      class="tip"
      type="info"
      :closable="false"
      show-icon
      title="这里是「商家兑换订单」（用户在商家处用积分兑换服务后的核销单）"
      description="与左侧「订单管理」里的物品交换订单不是一回事：那一边是用户之间的旧物交换。"
    />

    <div class="toolbar">
      <el-select v-model="query.status" placeholder="兑换状态" clearable style="width: 140px">
        <el-option v-for="(text, val) in STATUS_TEXT" :key="val" :value="Number(val)" :label="text" />
      </el-select>
      <el-select v-model="query.merchant_id" placeholder="商家" clearable filterable style="width: 180px">
        <el-option v-for="shop in shops" :key="shop.id" :value="shop.id" :label="shop.name" />
      </el-select>
      <el-input
        v-model="query.keyword"
        placeholder="订单号 / 核销码"
        clearable
        style="width: 200px"
        @keyup.enter="reload"
      />
      <el-button type="primary" @click="reload">搜索</el-button>
      <el-button plain @click="onReset">重置</el-button>
    </div>

    <el-table v-loading="loading" :data="list" border>
      <el-table-column prop="order_no" label="订单号" width="150" />
      <el-table-column label="核销码" width="110">
        <template #default="{ row }">
          <span class="code">{{ textOr(row.code, '-') }}</span>
        </template>
      </el-table-column>
      <el-table-column label="用户" width="110">
        <template #default="{ row }">{{ textOr(row.user_nickname, '未知用户') }}</template>
      </el-table-column>
      <el-table-column label="商家" min-width="140" show-overflow-tooltip>
        <template #default="{ row }">{{ textOr(row.merchant_name, '未知商家') }}</template>
      </el-table-column>
      <el-table-column label="商品" min-width="150" show-overflow-tooltip>
        <template #default="{ row }">{{ textOr(row.product_title, '商品已删除') }}</template>
      </el-table-column>
      <el-table-column label="积分" width="90">
        <template #default="{ row }">
          <span class="points">{{ row.points_cost === 0 ? '免费' : row.points_cost }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">
            {{ textOr(row.status_label, '未知状态') }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="兑换时间" width="170">
        <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="核销时间" width="170">
        <template #default="{ row }">{{ fmtTime(row.redeemed_at) }}</template>
      </el-table-column>
      <template #empty>
        <el-empty description="暂无兑换订单" />
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
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'

import { getMerchantList, getRedemptionOrders } from '@/api/merchant'

// 1待核销 2已核销 3已过期 4已取消（与后端 constants.REDEMPTION_STATUS_LABEL 一致）
const STATUS_TEXT = { 1: '待核销', 2: '已核销', 3: '已过期', 4: '已取消' }
const STATUS_TYPES = { 1: 'warning', 2: 'success', 3: 'info', 4: 'danger' }

const list = ref([])
const total = ref(0)
const loading = ref(false)
const shops = ref([])
const query = reactive({ page: 1, size: 10, keyword: '', status: undefined, merchant_id: undefined })

function statusType(status) {
  return STATUS_TYPES[status] || 'info'
}

/** 空值兜底：绝不把 null / undefined 渲染出来 */
function textOr(value, fallback) {
  if (value === null || value === undefined) return fallback
  const text = String(value).trim()
  return text === '' ? fallback : text
}

function fmtTime(value) {
  if (!value) return '-'
  return String(value).replace('T', ' ').slice(0, 19)
}

async function load() {
  loading.value = true
  try {
    const res = await getRedemptionOrders(query)
    list.value = res.data.list || []
    total.value = res.data.total || 0
  } finally {
    loading.value = false
  }
}

/** 商家下拉数据：一次拉够（平台商家量级很小），避免每行再查一次 */
async function loadShops() {
  const res = await getMerchantList({ page: 1, size: 100 })
  shops.value = res.data.list || []
}

function reload() {
  query.page = 1
  load()
}

function onReset() {
  query.status = undefined
  query.merchant_id = undefined
  query.keyword = ''
  reload()
}

onMounted(() => {
  load()
  loadShops()
})
</script>

<style scoped>
.tip {
  margin-bottom: 14px;
}

.code {
  font-family: 'Menlo', 'Consolas', monospace;
  letter-spacing: 1px;
  color: #374151;
}

.points {
  color: var(--el-color-primary);
  font-weight: 600;
}
</style>
