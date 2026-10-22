<template>
  <ProfileSubLayout title="通知设置" desc="选择你希望接收的消息类型，设置会保存到账号">
    <section class="profile-card">
      <h2 class="card-title">消息通知</h2>

      <div class="setting-item">
        <div class="setting-text">
          <div class="setting-name">私信通知</div>
          <div class="setting-desc">有邻居给你发私信时提醒你</div>
        </div>
        <el-switch v-model="form.notify_message" size="large" aria-label="私信通知" />
      </div>

      <div class="setting-item">
        <div class="setting-text">
          <div class="setting-name">交换状态通知</div>
          <div class="setting-desc">交换申请、确认、完成等状态变化时提醒你</div>
        </div>
        <el-switch v-model="form.notify_exchange" size="large" aria-label="交换状态通知" />
      </div>

      <div class="setting-item">
        <div class="setting-text">
          <div class="setting-name">系统公告</div>
          <div class="setting-desc">平台公告、活动与功能更新提醒</div>
        </div>
        <el-switch v-model="form.notify_system" size="large" aria-label="系统公告" />
      </div>

      <el-button type="primary" class="save-btn" :loading="saving" @click="onSave">
        保存设置
      </el-button>
    </section>
  </ProfileSubLayout>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import ProfileSubLayout from '../../layouts/ProfileSubLayout.vue'
import { getNotifications, updateNotifications } from '../../api/user'

const saving = ref(false)
// 开关用布尔绑定，提交时转成 0/1
const form = reactive({
  notify_message: true,
  notify_exchange: true,
  notify_system: true,
})

function apply(data) {
  if (!data) return
  form.notify_message = Number(data.notify_message ?? 1) === 1
  form.notify_exchange = Number(data.notify_exchange ?? 1) === 1
  form.notify_system = Number(data.notify_system ?? 1) === 1
}

async function load() {
  try {
    apply(await getNotifications())
  } catch {
    // 错误提示由请求拦截器统一处理
  }
}

async function onSave() {
  saving.value = true
  try {
    apply(
      await updateNotifications({
        notify_message: form.notify_message ? 1 : 0,
        notify_exchange: form.notify_exchange ? 1 : 0,
        notify_system: form.notify_system ? 1 : 0,
      }),
    )
    ElMessage.success('通知设置已保存')
  } catch {
    ElMessage.error('保存失败，请稍后再试')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>
