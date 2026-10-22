<template>
  <el-dialog
    v-model="visible"
    title="换绑邮箱"
    width="440px"
    :close-on-click-modal="false"
    @closed="resetForm"
  >
    <el-form label-position="top" @submit.prevent>
      <el-form-item label="新邮箱">
        <el-input
          v-model="form.newEmail"
          maxlength="128"
          placeholder="请输入新的邮箱地址"
        />
      </el-form-item>
      <el-form-item label="验证码">
        <div class="code-row">
          <el-input
            v-model="form.code"
            maxlength="6"
            placeholder="请输入 6 位验证码"
            @keyup.enter="onSubmit"
          />
          <el-button :disabled="countdown > 0" :loading="sending" @click="onSendCode">
            {{ countdown > 0 ? `${countdown} 秒后重发` : '发送验证码' }}
          </el-button>
        </div>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="loading" @click="onSubmit">确认换绑</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { onUnmounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { rebindEmail, sendEmailCode } from '../../api/user'

const emit = defineEmits(['success'])

const visible = defineModel({ type: Boolean, default: false })

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/
const COUNTDOWN_SECONDS = 60

const loading = ref(false)
const sending = ref(false)
const countdown = ref(0)
let timer = null

const form = reactive({ newEmail: '', code: '' })

function stopTimer() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

function resetForm() {
  stopTimer()
  countdown.value = 0
  form.newEmail = ''
  form.code = ''
}

function startCountdown() {
  stopTimer()
  countdown.value = COUNTDOWN_SECONDS
  timer = setInterval(() => {
    countdown.value -= 1
    if (countdown.value <= 0) stopTimer()
  }, 1000)
}

async function onSendCode() {
  const email = form.newEmail.trim()
  if (!EMAIL_PATTERN.test(email)) {
    ElMessage.warning('请输入正确的邮箱地址')
    return
  }
  sending.value = true
  try {
    await sendEmailCode({ new_email: email })
    ElMessage.success('验证码已发送')
    startCountdown()
  } catch {
    // 错误提示由请求拦截器统一处理
  } finally {
    sending.value = false
  }
}

async function onSubmit() {
  const email = form.newEmail.trim()
  if (!EMAIL_PATTERN.test(email)) {
    ElMessage.warning('请输入正确的邮箱地址')
    return
  }
  if (!form.code.trim()) {
    ElMessage.warning('请输入验证码')
    return
  }
  loading.value = true
  try {
    const data = await rebindEmail({ new_email: email, code: form.code.trim() })
    visible.value = false
    ElMessage.success(`邮箱已更新为 ${data.email}`)
    emit('success')
  } catch {
    // 错误提示由请求拦截器统一处理
  } finally {
    loading.value = false
  }
}

onUnmounted(stopTimer)
</script>

<style scoped>
.code-row {
  display: flex;
  gap: 12px;
  width: 100%;
}

.code-row :deep(.el-input) {
  flex: 1;
}

@media (max-width: 480px) {
  .code-row {
    flex-direction: column;
  }
}
</style>
