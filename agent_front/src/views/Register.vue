<template>
  <section class="auth page">
    <div class="auth-box glass-card">
      <div class="eyebrow">加入社区</div>
      <h1 class="auth-title">创建你的闲物焕新账号</h1>

      <el-radio-group v-model="registerType" class="mode-switch">
        <el-radio-button value="phone">手机号注册</el-radio-button>
        <el-radio-button value="email">邮箱注册</el-radio-button>
      </el-radio-group>

      <el-form @submit.prevent="submit">
        <el-form-item>
          <el-input v-model="form.nickname" placeholder="昵称" />
        </el-form-item>

        <el-form-item v-if="registerType === 'phone'">
          <el-input v-model="form.phone" placeholder="手机号" />
        </el-form-item>
        <el-form-item v-else>
          <el-input v-model="form.email" placeholder="邮箱" />
        </el-form-item>

        <el-form-item>
          <el-input
            v-model="form.password"
            type="password"
            show-password
            placeholder="设置密码（至少 6 位）"
          />
        </el-form-item>

        <el-form-item>
          <div class="code-row">
            <el-input v-model="form.code" placeholder="6 位验证码" />
            <el-button class="code-btn" @click="send" :disabled="countdown > 0">
              {{ countdown ? `${countdown}s 后重发` : '获取验证码' }}
            </el-button>
          </div>
        </el-form-item>

        <el-button
          type="primary"
          native-type="submit"
          class="full"
          :loading="loading"
        >
          创建账号
          </el-button>
      </el-form>

      <p class="switch muted">
        已有账号？<RouterLink to="/login">直接登录</RouterLink>
      </p>
    </div>
  </section>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { sendCode, register } from '../api/auth'

const registerType = ref('phone')
const form = reactive({
  nickname: '',
  email: '',
  phone: '',
  password: '',
  code: '',
})

const countdown = ref(0)
const loading = ref(false)
const router = useRouter()
let timer = null

const target = computed(() =>
  registerType.value === 'phone' ? form.phone : form.email,
)

function validTarget() {
  return registerType.value === 'phone'
    ? /^1\d{10}$/.test(target.value)
    : /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(target.value)
}

async function send() {
  if (!validTarget()) {
    return ElMessage.warning(
      registerType.value === 'phone' ? '请输入正确的手机号' : '请输入正确的邮箱',
    )
  }
  try {
    const result = await sendCode({
      target: target.value,
      target_type: registerType.value,
      scene: 'register',
    })
    if (result?.debug_code) {
      ElMessage.success(`开发验证码：${result.debug_code}`)
    }
    countdown.value = 60
    timer = setInterval(() => {
      countdown.value -= 1
      if (!countdown.value) {
        clearInterval(timer)
        timer = null
      }
    }, 1000)
  } catch {
    // 失败不启动倒计时
  }
}

async function submit() {
  if (
    !validTarget() ||
    !form.nickname ||
    form.password.length < 6 ||
    form.code.length !== 6
  ) {
    return ElMessage.warning('请完整填写注册信息')
  }
  loading.value = true
  try {
    await register({
      register_type: registerType.value,
      [registerType.value]: target.value,
      password: form.password,
      nickname: form.nickname,
      code: form.code,
    })
    ElMessage.success('注册成功，请登录')
    router.push('/login')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth {
  display: grid;
  place-items: center;
  min-height: 70vh;
}

.auth-box {
  width: min(480px, 100%);
  padding: 38px;
}

.auth-title {
  font-size: 30px;
  margin: 10px 0 22px;
}

.mode-switch {
  display: flex;
  width: 100%;
  margin-bottom: 22px;
}

.mode-switch .el-radio-button {
  flex: 1;
}

.mode-switch :deep(.el-radio-button__inner) {
  width: 100%;
}

.code-row {
  display: flex;
  gap: 8px;
  width: 100%;
}

.code-row .el-input {
  flex: 1;
}

.code-btn {
  white-space: nowrap;
  background: var(--green-soft);
  border: none;
  color: var(--green-active);
}

.code-btn:hover {
  background: var(--green-primary) !important;
  color: #fff !important;
}

.code-btn.is-disabled {
  background: var(--bg-disabled) !important;
  color: var(--text-placeholder) !important;
}

.full {
  width: 100%;
  margin-top: 6px;
}

.switch {
  text-align: center;
  font-size: 13px;
  margin-top: 26px;
}

.switch a {
  color: var(--green-primary);
  font-weight: 500;
}
</style>
