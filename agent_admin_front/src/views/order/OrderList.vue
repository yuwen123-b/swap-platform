<template>
  <div class="page-card">
    <div class="toolbar">
      <el-input v-model="query.keyword" placeholder="订单号 / 买卖双方昵称" clearable style="width: 240px" @keyup.enter="load" />
      <el-select v-model="query.status" placeholder="状态" clearable style="width: 130px">
        <el-option v-for="(text, val) in statusText" :key="val" :value="Number(val)" :label="text" />
      </el-select>
      <el-button type="primary" @click="load">搜索</el-button>
    </div>

    <el-table v-loading="loading" :data="list" border>
      <el-table-column prop="order_no" label="订单号" width="160" />
      <el-table-column prop="item_title" label="物品" min-width="160" show-overflow-tooltip />
      <el-table-column prop="buyer_name" label="买方" width="100" />
      <el-table-column prop="seller_name" label="卖方" width="100" />
      <el-table-column prop="price" label="金额(元)" width="100" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType[row.status]" size="small">{{ statusText[row.status] }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="170" />
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openDetail(row)">详情</el-button>
          <template v-if="canWrite">
            <el-button size="small" type="warning" @click="openStatus(row)">改状态</el-button>
            <el-popconfirm title="确定删除该订单？" @confirm="onDelete(row)">
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination v-model:current-page="query.page" v-model:page-size="query.size" :total="total" layout="total, prev, pager, next" @current-change="load" />
    </div>

    <el-drawer v-model="drawerVisible" title="订单详情" size="420px">
      <el-descriptions v-if="detail" :column="1" border>
        <el-descriptions-item label="订单号">{{ detail.order_no }}</el-descriptions-item>
        <el-descriptions-item label="物品">{{ detail.item_title }}</el-descriptions-item>
        <el-descriptions-item label="买方">{{ detail.buyer_name }}</el-descriptions-item>
        <el-descriptions-item label="卖方">{{ detail.seller_name }}</el-descriptions-item>
        <el-descriptions-item label="金额">{{ detail.price }} 元</el-descriptions-item>
        <el-descriptions-item label="状态">{{ statusText[detail.status] }}</el-descriptions-item>
        <el-descriptions-item label="交易地点">{{ detail.meet_location || '-' }}</el-descriptions-item>
        <el-descriptions-item label="约定时间">{{ detail.meet_time || '-' }}</el-descriptions-item>
        <el-descriptions-item label="完成时间">{{ detail.completed_at || '-' }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ detail.created_at }}</el-descriptions-item>
      </el-descriptions>
    </el-drawer>

    <el-dialog v-model="statusVisible" title="修改订单状态" width="380px">
      <el-select v-model="newStatus" style="width: 100%">
        <el-option v-for="(text, val) in statusText" :key="val" :value="Number(val)" :label="text" />
      </el-select>
      <template #footer>
        <el-button @click="statusVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSaveStatus">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { deleteOrder, getOrderDetail, getOrders, updateOrderStatus } from '@/api/order'
import { useAdminStore } from '@/store/admin'

const store = useAdminStore()
const canWrite = computed(() => [1, 2].includes(store.role))

// 1=待确认 2=交换中 3=已完成 4=已取消 5=争议中
const statusText = { 1: '待确认', 2: '交换中', 3: '已完成', 4: '已取消', 5: '争议中' }
const statusType = { 1: 'warning', 2: 'primary', 3: 'success', 4: 'info', 5: 'danger' }

const list = ref([])
const total = ref(0)
const loading = ref(false)
const saving = ref(false)
const query = reactive({ page: 1, size: 10, keyword: '', status: undefined })

const drawerVisible = ref(false)
const detail = ref(null)
const statusVisible = ref(false)
const statusTarget = ref(null)
const newStatus = ref(1)

async function load() {
  loading.value = true
  try {
    const res = await getOrders(query)
    list.value = res.data.list
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

async function openDetail(row) {
  const res = await getOrderDetail(row.id)
  detail.value = res.data
  drawerVisible.value = true
}

function openStatus(row) {
  statusTarget.value = row
  newStatus.value = row.status
  statusVisible.value = true
}

async function onSaveStatus() {
  saving.value = true
  try {
    await updateOrderStatus(statusTarget.value.id, newStatus.value)
    ElMessage.success('状态已更新')
    statusVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

async function onDelete(row) {
  await deleteOrder(row.id)
  ElMessage.success('已删除')
  load()
}

onMounted(load)
</script>
