<template>
  <div class="page-card">
    <div class="toolbar">
      <el-input v-model="query.keyword" placeholder="昵称 / 手机号" clearable style="width: 220px" @keyup.enter="load" />
      <el-select v-model="query.status" placeholder="状态" clearable style="width: 120px">
        <el-option :value="1" label="正常" />
        <el-option :value="0" label="禁用" />
      </el-select>
      <el-button type="primary" @click="load">搜索</el-button>
    </div>

    <el-table v-loading="loading" :data="list" border>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="nickname" label="昵称" />
      <el-table-column prop="phone" label="手机号" width="130" />
      <el-table-column prop="credit_score" label="信用分" width="90" />
      <el-table-column prop="points" label="积分" width="90" />
      <el-table-column prop="exchange_count" label="交换次数" width="100" />
      <el-table-column label="实名" width="80">
        <template #default="{ row }">
          <el-tag v-if="row.is_verified" type="success" size="small">已实名</el-tag>
          <el-tag v-else type="info" size="small">未实名</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 1 ? 'success' : 'danger'" size="small">{{ row.status === 1 ? '正常' : '禁用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="注册时间" width="170" />
      <el-table-column label="操作" width="230" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openDetail(row)">详情</el-button>
          <template v-if="canWrite">
            <el-button size="small" :type="row.status === 1 ? 'warning' : 'success'" @click="onToggleStatus(row)">
              {{ row.status === 1 ? '禁用' : '启用' }}
            </el-button>
            <el-popconfirm title="确定删除该用户？" @confirm="onDelete(row)">
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

    <el-drawer v-model="drawerVisible" title="用户详情" size="420px">
      <el-descriptions v-if="detail" :column="1" border>
        <el-descriptions-item label="昵称">{{ detail.nickname }}</el-descriptions-item>
        <el-descriptions-item label="手机号">{{ detail.phone }}</el-descriptions-item>
        <el-descriptions-item label="姓名">{{ detail.real_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="邮箱">{{ detail.email || '-' }}</el-descriptions-item>
        <el-descriptions-item label="信用分">{{ detail.credit_score }}</el-descriptions-item>
        <el-descriptions-item label="积分">{{ detail.points }}</el-descriptions-item>
        <el-descriptions-item label="减碳量(kg)">{{ detail.carbon_total }}</el-descriptions-item>
        <el-descriptions-item label="发布物品数">{{ detail.item_count }}</el-descriptions-item>
        <el-descriptions-item label="交换记录数">{{ detail.order_count }}</el-descriptions-item>
        <el-descriptions-item label="最近登录">{{ detail.last_login_time || '-' }}</el-descriptions-item>
        <el-descriptions-item label="注册时间">{{ detail.created_at }}</el-descriptions-item>
      </el-descriptions>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { deleteUser, getUserDetail, getUsers, updateUserStatus } from '@/api/user'
import { useAdminStore } from '@/store/admin'

const store = useAdminStore()
const canWrite = computed(() => [1, 2].includes(store.role))

const list = ref([])
const total = ref(0)
const loading = ref(false)
const query = reactive({ page: 1, size: 10, keyword: '', status: undefined })

const drawerVisible = ref(false)
const detail = ref(null)

async function load() {
  loading.value = true
  try {
    const res = await getUsers(query)
    list.value = res.data.list
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

async function openDetail(row) {
  const res = await getUserDetail(row.id)
  detail.value = res.data
  drawerVisible.value = true
}

async function onToggleStatus(row) {
  const target = row.status === 1 ? 0 : 1
  await updateUserStatus(row.id, target)
  ElMessage.success(target === 1 ? '已启用' : '已禁用')
  load()
}

async function onDelete(row) {
  await deleteUser(row.id)
  ElMessage.success('已删除')
  load()
}

onMounted(load)
</script>
