<template>
  <div class="page-card">
    <div class="toolbar">
      <el-input v-model="query.keyword" placeholder="用户名 / 姓名" clearable style="width: 220px" @keyup.enter="load" />
      <el-button type="primary" @click="load">搜索</el-button>
      <el-button type="primary" plain @click="openCreate">新增管理员</el-button>
    </div>

    <el-table v-loading="loading" :data="list" border>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="username" label="用户名" />
      <el-table-column prop="real_name" label="姓名" />
      <el-table-column label="角色" width="120">
        <template #default="{ row }">
          <el-tag :type="{ 1: 'danger', 2: 'warning', 3: 'success' }[row.role]">
            {{ { 1: '超级管理员', 2: '运营专员', 3: '审核员' }[row.role] }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 1 ? 'success' : 'info'">{{ row.status === 1 ? '启用' : '禁用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="170" />
      <el-table-column label="操作" width="280" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="warning" @click="openReset(row)">重置密码</el-button>
          <el-popconfirm title="确定删除该管理员？" @confirm="onDelete(row)">
            <template #reference>
              <el-button size="small" type="danger" :disabled="row.id === store.adminInfo?.admin_id">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination v-model:current-page="query.page" v-model:page-size="query.size" :total="total" layout="total, prev, pager, next" @current-change="load" />
    </div>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑管理员' : '新增管理员'" width="420px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="用户名">
          <el-input v-model="form.username" :disabled="editing" placeholder="登录用户名" />
        </el-form-item>
        <el-form-item v-if="!editing" label="初始密码">
          <el-input v-model="form.password" type="password" show-password placeholder="至少 6 位" />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="form.real_name" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role" style="width: 100%">
            <el-option :value="1" label="超级管理员" />
            <el-option :value="2" label="运营专员" />
            <el-option :value="3" label="审核员" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="editing" label="状态">
          <el-switch v-model="form.status" :active-value="1" :inactive-value="0" active-text="启用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="resetVisible" title="重置密码" width="380px">
      <el-input v-model="resetPwd" type="password" show-password placeholder="新密码（至少 6 位）" />
      <template #footer>
        <el-button @click="resetVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onReset">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { createAccount, deleteAccount, getAccounts, resetPassword, updateAccount } from '@/api/admin'
import { useAdminStore } from '@/store/admin'

const store = useAdminStore()
const list = ref([])
const total = ref(0)
const loading = ref(false)
const saving = ref(false)
const query = reactive({ page: 1, size: 10, keyword: '' })

const dialogVisible = ref(false)
const editing = ref(false)
const form = reactive({ id: null, username: '', password: '', real_name: '', role: 3, status: 1 })

const resetVisible = ref(false)
const resetPwd = ref('')
const resetTarget = ref(null)

async function load() {
  loading.value = true
  try {
    const res = await getAccounts(query)
    list.value = res.data.list
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = false
  Object.assign(form, { id: null, username: '', password: '', real_name: '', role: 3, status: 1 })
  dialogVisible.value = true
}

function openEdit(row) {
  editing.value = true
  Object.assign(form, { id: row.id, username: row.username, password: '', real_name: row.real_name, role: row.role, status: row.status })
  dialogVisible.value = true
}

async function onSave() {
  saving.value = true
  try {
    if (editing.value) {
      await updateAccount(form.id, { real_name: form.real_name, role: form.role, status: form.status })
    } else {
      await createAccount({ username: form.username, password: form.password, real_name: form.real_name, role: form.role })
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

function openReset(row) {
  resetTarget.value = row
  resetPwd.value = ''
  resetVisible.value = true
}

async function onReset() {
  if (resetPwd.value.length < 6) {
    ElMessage.warning('密码至少 6 位')
    return
  }
  saving.value = true
  try {
    await resetPassword(resetTarget.value.id, resetPwd.value)
    ElMessage.success('密码已重置')
    resetVisible.value = false
  } finally {
    saving.value = false
  }
}

async function onDelete(row) {
  await deleteAccount(row.id)
  ElMessage.success('已删除')
  load()
}

onMounted(load)
</script>
