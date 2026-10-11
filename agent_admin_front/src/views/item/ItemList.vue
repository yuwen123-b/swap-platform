<template>
  <div class="page-card">
    <div class="toolbar">
      <el-input v-model="query.keyword" placeholder="名称 / 描述关键词" clearable style="width: 200px" @keyup.enter="load" />
      <el-input v-model="query.publisher" placeholder="发布者昵称" clearable style="width: 150px" @keyup.enter="load" />
      <el-select v-model="query.status" placeholder="状态" clearable style="width: 120px">
        <el-option :value="4" label="待审核" />
        <el-option :value="1" label="已上架" />
        <el-option :value="2" label="已换出" />
        <el-option :value="3" label="已下架" />
      </el-select>
      <el-button type="primary" @click="load">搜索</el-button>
    </div>

    <el-table v-loading="loading" :data="list" border>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="title" label="物品名称" min-width="180" show-overflow-tooltip />
      <el-table-column prop="category_name" label="分类" width="110" />
      <el-table-column prop="publisher" label="发布者" width="110" />
      <el-table-column prop="price" label="参考价(元)" width="110" />
      <el-table-column prop="view_count" label="浏览" width="80" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType[row.status]" size="small">{{ statusText[row.status] }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="发布时间" width="170" />
      <el-table-column label="操作" width="250" fixed="right">
        <template #default="{ row }">
          <template v-if="canWrite">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="row.status === 1" size="small" type="warning" @click="onOffline(row)">下架</el-button>
            <el-popconfirm title="确定删除该物品？" @confirm="onDelete(row)">
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
          <span v-else class="readonly">只读</span>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination v-model:current-page="query.page" v-model:page-size="query.size" :total="total" layout="total, prev, pager, next" @current-change="load" />
    </div>

    <el-dialog v-model="dialogVisible" title="编辑物品" width="520px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="名称">
          <el-input v-model="form.title" maxlength="64" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="参考价">
          <el-input-number v-model="form.price" :min="0" :precision="2" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status" style="width: 100%">
            <el-option :value="4" label="待审核" />
            <el-option :value="1" label="已上架" />
            <el-option :value="2" label="已换出" />
            <el-option :value="3" label="已下架" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { deleteItem, getItems, updateItem } from '@/api/item'
import { useAdminStore } from '@/store/admin'

const store = useAdminStore()
const canWrite = computed(() => [1, 2].includes(store.role))

const statusText = { 4: '待审核', 1: '已上架', 2: '已换出', 3: '已下架' }
const statusType = { 4: 'warning', 1: 'success', 2: 'info', 3: 'danger' }

const list = ref([])
const total = ref(0)
const loading = ref(false)
const saving = ref(false)
const query = reactive({ page: 1, size: 10, keyword: '', publisher: '', status: undefined })

const dialogVisible = ref(false)
const form = reactive({ id: null, title: '', description: '', price: 0, status: 1 })

async function load() {
  loading.value = true
  try {
    const res = await getItems(query)
    list.value = res.data.list
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

function openEdit(row) {
  Object.assign(form, { id: row.id, title: row.title, description: row.description, price: row.price, status: row.status })
  dialogVisible.value = true
}

async function onSave() {
  saving.value = true
  try {
    await updateItem(form.id, { title: form.title, description: form.description, price: form.price, status: form.status })
    ElMessage.success('已保存')
    dialogVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

async function onOffline(row) {
  await updateItem(row.id, { status: 3 })
  ElMessage.success('已下架')
  load()
}

async function onDelete(row) {
  await deleteItem(row.id)
  ElMessage.success('已删除')
  load()
}

onMounted(load)
</script>

<style scoped>
.readonly {
  color: #9ca3af;
  font-size: 13px;
}
</style>
