<template>
  <div class="page-card">
    <div class="toolbar">
      <el-input v-model="query.keyword" placeholder="标题 / 内容 / 作者" clearable style="width: 240px" @keyup.enter="load" />
      <el-button type="primary" @click="load">搜索</el-button>
    </div>

    <el-table v-loading="loading" :data="list" border>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
      <el-table-column prop="author" label="作者" width="110" />
      <el-table-column prop="like_count" label="点赞" width="80" />
      <el-table-column prop="comment_count" label="评论" width="80" />
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 1 ? 'success' : 'info'" size="small">{{ row.status === 1 ? '正常' : '隐藏' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="发布时间" width="170" />
      <el-table-column label="操作" width="240" fixed="right">
        <template #default="{ row }">
          <template v-if="canWrite">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" :type="row.status === 1 ? 'warning' : 'success'" @click="onToggle(row)">
              {{ row.status === 1 ? '隐藏' : '恢复' }}
            </el-button>
            <el-popconfirm title="确定删除该帖子及其评论？" @confirm="onDelete(row)">
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

    <el-dialog v-model="dialogVisible" title="编辑帖子" width="520px">
      <el-form :model="form" label-width="70px">
        <el-form-item label="标题">
          <el-input v-model="form.title" maxlength="100" />
        </el-form-item>
        <el-form-item label="内容">
          <el-input v-model="form.content" type="textarea" :rows="5" />
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

import { deletePost, getPosts, updatePost } from '@/api/community'
import { useAdminStore } from '@/store/admin'

const store = useAdminStore()
const canWrite = computed(() => [1, 2].includes(store.role))

const list = ref([])
const total = ref(0)
const loading = ref(false)
const saving = ref(false)
const query = reactive({ page: 1, size: 10, keyword: '' })

const dialogVisible = ref(false)
const form = reactive({ id: null, title: '', content: '' })

async function load() {
  loading.value = true
  try {
    const res = await getPosts(query)
    list.value = res.data.list
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

function openEdit(row) {
  Object.assign(form, { id: row.id, title: row.title, content: row.content })
  dialogVisible.value = true
}

async function onSave() {
  saving.value = true
  try {
    await updatePost(form.id, { title: form.title, content: form.content })
    ElMessage.success('已保存')
    dialogVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

async function onToggle(row) {
  await updatePost(row.id, { status: row.status === 1 ? 0 : 1 })
  ElMessage.success('已更新')
  load()
}

async function onDelete(row) {
  await deletePost(row.id)
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
