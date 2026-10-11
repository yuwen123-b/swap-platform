<template>
  <div>
    <div class="page-card">
      <div class="toolbar">
        <el-input v-model="query.keyword" placeholder="用户昵称 / 描述" clearable style="width: 220px" @keyup.enter="load" />
        <el-button type="primary" @click="load">搜索</el-button>
        <el-button v-if="canWrite" type="warning" plain @click="adjustVisible = true">手动调整积分</el-button>
      </div>

      <el-table v-loading="loading" :data="list" border>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="nickname" label="用户" width="120" />
        <el-table-column label="变动" width="100">
          <template #default="{ row }">
            <span :style="{ color: row.points >= 0 ? '#2f855a' : '#dc2626', fontWeight: 600 }">
              {{ row.points >= 0 ? '+' : '' }}{{ row.points }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="130">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ sourceText[row.source] || '其他' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="说明" min-width="200" show-overflow-tooltip />
        <el-table-column prop="created_at" label="时间" width="170" />
      </el-table>

      <div class="pager">
        <el-pagination v-model:current-page="query.page" v-model:page-size="query.size" :total="total" layout="total, prev, pager, next" @current-change="load" />
      </div>
    </div>

    <div class="page-card" style="margin-top: 16px">
      <h3 class="title">积分规则</h3>
      <el-form v-if="store.role === 1" inline>
        <el-form-item label="发布物品奖励">
          <el-input-number v-model="rules.points_publish" :min="0" />
        </el-form-item>
        <el-form-item label="完成交换奖励">
          <el-input-number v-model="rules.points_exchange" :min="0" />
        </el-form-item>
        <el-form-item label="举报成立扣分">
          <el-input-number v-model="rules.points_report_deduct" :min="0" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="savingRules" @click="onSaveRules">保存规则</el-button>
        </el-form-item>
      </el-form>
      <el-descriptions v-else :column="3" border>
        <el-descriptions-item label="发布物品奖励">{{ rules.points_publish }} 分</el-descriptions-item>
        <el-descriptions-item label="完成交换奖励">{{ rules.points_exchange }} 分</el-descriptions-item>
        <el-descriptions-item label="举报成立扣分">{{ rules.points_report_deduct }} 分</el-descriptions-item>
      </el-descriptions>
    </div>

    <el-dialog v-model="adjustVisible" title="手动调整积分" width="420px">
      <el-form label-width="80px">
        <el-form-item label="用户 ID">
          <el-input-number v-model="adjustForm.user_id" :min="1" />
        </el-form-item>
        <el-form-item label="积分数">
          <el-input-number v-model="adjustForm.points" placeholder="正数加分，负数扣分" />
        </el-form-item>
        <el-form-item label="调整原因">
          <el-input v-model="adjustForm.reason" type="textarea" :rows="2" maxlength="100" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="adjustVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onAdjust">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { adjustPoints, getPointsLogs, getPointsRules, updatePointsRules } from '@/api/points'
import { useAdminStore } from '@/store/admin'

const store = useAdminStore()
const canWrite = computed(() => [1, 2].includes(store.role))

const sourceText = { 1: '发布奖励', 2: '交换奖励', 3: '签到', 4: '管理员调整' }

const list = ref([])
const total = ref(0)
const loading = ref(false)
const query = reactive({ page: 1, size: 10, keyword: '' })

const rules = reactive({ points_publish: 0, points_exchange: 0, points_report_deduct: 0 })
const savingRules = ref(false)

const adjustVisible = ref(false)
const saving = ref(false)
const adjustForm = reactive({ user_id: null, points: 0, reason: '' })

async function load() {
  loading.value = true
  try {
    const res = await getPointsLogs(query)
    list.value = res.data.list
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

async function loadRules() {
  const res = await getPointsRules()
  const d = res.data || {}
  rules.points_publish = Number(d.points_publish ?? 0)
  rules.points_exchange = Number(d.points_exchange ?? 0)
  rules.points_report_deduct = Number(d.points_report_deduct ?? 0)
}

async function onSaveRules() {
  savingRules.value = true
  try {
    await updatePointsRules({
      points_publish: String(rules.points_publish),
      points_exchange: String(rules.points_exchange),
      points_report_deduct: String(rules.points_report_deduct),
    })
    ElMessage.success('规则已保存')
  } finally {
    savingRules.value = false
  }
}

async function onAdjust() {
  if (!adjustForm.user_id || !adjustForm.points || !adjustForm.reason.trim()) {
    ElMessage.warning('请完整填写用户、积分与原因')
    return
  }
  saving.value = true
  try {
    await adjustPoints({ user_id: adjustForm.user_id, points: adjustForm.points, reason: adjustForm.reason.trim() })
    ElMessage.success('调整成功')
    adjustVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  load()
  loadRules()
})
</script>

<style scoped>
.title {
  font-size: 15px;
  color: #374151;
  margin-bottom: 16px;
}
</style>
