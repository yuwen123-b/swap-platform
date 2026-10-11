<template>
  <div class="page-card" v-loading="loading">
    <h3 class="title">平台参数</h3>
    <el-form label-width="140px" style="max-width: 640px">
      <el-form-item label="平台名称">
        <el-input v-model="form.platform_name" />
      </el-form-item>
      <el-form-item label="平台公告">
        <el-input v-model="form.announcement" type="textarea" :rows="3" />
      </el-form-item>
      <el-form-item label="客服联系方式">
        <el-input v-model="form.contact" />
      </el-form-item>
      <el-form-item label="物品发布审核">
        <el-switch v-model="auditEnabled" active-text="开启（发布需审核）" inactive-text="关闭" />
      </el-form-item>
    </el-form>

    <el-divider />
    <h3 class="title">积分规则</h3>
    <el-form label-width="140px" style="max-width: 640px">
      <el-form-item label="发布物品奖励">
        <el-input-number v-model="form.points_publish" :min="0" />
      </el-form-item>
      <el-form-item label="完成交换奖励">
        <el-input-number v-model="form.points_exchange" :min="0" />
      </el-form-item>
      <el-form-item label="举报成立扣分">
        <el-input-number v-model="form.points_report_deduct" :min="0" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="saving" round @click="onSave">保存配置</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { getSystemConfig, updateSystemConfig } from '@/api/system'

const loading = ref(false)
const saving = ref(false)
const form = reactive({
  platform_name: '',
  announcement: '',
  contact: '',
  audit_enabled: '1',
  points_publish: 10,
  points_exchange: 20,
  points_report_deduct: 50,
})

const auditEnabled = computed({
  get: () => form.audit_enabled === '1',
  set: (v) => (form.audit_enabled = v ? '1' : '0'),
})

async function load() {
  loading.value = true
  try {
    const res = await getSystemConfig()
    const d = res.data || {}
    form.platform_name = d.platform_name ?? ''
    form.announcement = d.announcement ?? ''
    form.contact = d.contact ?? ''
    form.audit_enabled = d.audit_enabled ?? '1'
    form.points_publish = Number(d.points_publish ?? 10)
    form.points_exchange = Number(d.points_exchange ?? 20)
    form.points_report_deduct = Number(d.points_report_deduct ?? 50)
  } finally {
    loading.value = false
  }
}

async function onSave() {
  saving.value = true
  try {
    await updateSystemConfig({
      platform_name: form.platform_name,
      announcement: form.announcement,
      contact: form.contact,
      audit_enabled: form.audit_enabled,
      points_publish: String(form.points_publish),
      points_exchange: String(form.points_exchange),
      points_report_deduct: String(form.points_report_deduct),
    })
    ElMessage.success('配置已保存')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.title {
  font-size: 15px;
  color: #374151;
  margin-bottom: 16px;
}
</style>
