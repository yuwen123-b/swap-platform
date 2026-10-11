<template>
  <section class="auth page">
    <div class="auth-box glass-card">
      <div class="eyebrow">{{ t('register.eyebrow') }}</div>
      <h1 class="auth-title">{{ t('register.title') }}</h1>

      <el-radio-group v-model="registerType" class="mode-switch">
        <el-radio-button label="phone">{{ t('register.phoneRegister') }}</el-radio-button>
        <el-radio-button label="email">{{ t('register.emailRegister') }}</el-radio-button>
      </el-radio-group>

      <el-form @submit.prevent="submit">
        <el-form-item>
          <el-input v-model="form.nickname" :placeholder="t('register.nickname')" />
        </el-form-item>

        <el-form-item v-if="registerType === 'phone'">
          <el-input v-model="form.phone" :placeholder="t('register.phone')" />
        </el-form-item>
        <el-form-item v-else>
          <el-input v-model="form.email" :placeholder="t('register.email')" />
        </el-form-item>

        <el-form-item>
          <el-input
            v-model="form.password"
            type="password"
            show-password
            :placeholder="t('register.passwordPlaceholder')"
          />
        </el-form-item>

        <el-form-item>
          <div class="code-row">
            <el-input v-model="form.code" :placeholder="t('register.codePlaceholder')" />
            <el-button class="code-btn" @click="send" :disabled="countdown > 0">
              {{ countdown ? t('register.resendIn', { seconds: countdown }) : t('register.getCode') }}
            </el-button>
          </div>
        </el-form-item>

        <el-button
          type="primary"
          native-type="submit"
          class="full"
          :loading="loading"
        >
          {{ t('register.submit') }}
        </el-button>
      </el-form>

      <p class="switch muted">
        {{ t('register.hasAccount') }}<RouterLink to="/login">{{ t('register.loginLink') }}</RouterLink>
      </p>
    </div>
  </section>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { sendCode, register } from '../api/auth'
import { useI18n } from '../i18n'

const { t } = useI18n()
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
      registerType.value === 'phone' ? t('register.invalidPhone') : t('register.invalidEmail'),
    )
  }
  try {
    const result = await sendCode({
      target: target.value,
      target_type: registerType.value,
      scene: 'register',
    })
    if (result?.debug_code) {
      ElMessage.success(t('register.debugCode', { code: result.debug_code }))
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
    return ElMessage.warning(t('register.fillAll'))
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
    ElMessage.success(t('register.registerOk'))
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
