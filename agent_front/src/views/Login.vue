<template>
  <section class="auth page">
    <div class="auth-box glass-card">
      <div class="eyebrow">{{ t('login.eyebrow') }}</div>
      <h1 class="auth-title">{{ t('login.title') }}</h1>

      <el-tabs v-model="mode" stretch>
        <!-- 验证码登录 -->
        <el-tab-pane :label="t('login.tabCode')" name="code">
          <el-radio-group v-model="codeType" class="mode-switch">
            <el-radio-button label="phone">{{ t('login.phone') }}</el-radio-button>
            <el-radio-button label="email">{{ t('login.email') }}</el-radio-button>
          </el-radio-group>

          <el-form @submit.prevent="loginCode">
            <el-form-item>
              <el-input
                v-model="codeTarget"
                :placeholder="codeType === 'phone' ? t('login.phone') : t('login.email')"
              />
            </el-form-item>
            <el-form-item>
              <div class="code-row">
                <el-input v-model="code" :placeholder="t('login.codePlaceholder')" />
                <el-button class="code-btn" @click="send" :disabled="countdown > 0">
                  {{ countdown ? t('login.resendIn', { seconds: countdown }) : t('login.getCode') }}
                </el-button>
              </div>
            </el-form-item>
            <el-button
              type="primary"
              native-type="submit"
              class="full"
              :loading="loading"
            >
              {{ t('login.login') }}
            </el-button>
          </el-form>
        </el-tab-pane>

        <!-- 密码登录 -->
        <el-tab-pane :label="t('login.tabPassword')" name="password">
          <el-form @submit.prevent="loginPasswordForm">
            <el-form-item>
              <el-input v-model="email" :placeholder="t('login.email')" />
            </el-form-item>
            <el-form-item>
              <el-input
                v-model="password"
                type="password"
                show-password
                :placeholder="t('login.password')"
              />
            </el-form-item>
            <el-button
              type="primary"
              native-type="submit"
              class="full"
              :loading="loading"
            >
              {{ t('login.login') }}
            </el-button>
          </el-form>
        </el-tab-pane>
      </el-tabs>

      <p class="switch muted">
        {{ t('login.noAccount') }}<RouterLink to="/register">{{ t('login.registerLink') }}</RouterLink>
      </p>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  loginEmailCode,
  loginPhoneCode,
  loginPassword,
  sendCode,
} from '../api/auth'
import { useUserStore } from '../store/user'
import { useI18n } from '../i18n'

const { t } = useI18n()
const mode = ref('code')
const codeType = ref('phone')
const codeTarget = ref('')
const code = ref('')
const email = ref('')
const password = ref('')
const countdown = ref(0)
const loading = ref(false)

const router = useRouter()
const route = useRoute()
const store = useUserStore()

const validTarget = computed(() =>
  codeType.value === 'phone'
    ? /^1\d{10}$/.test(codeTarget.value)
    : /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(codeTarget.value),
)

let timer = null

async function send() {
  if (!validTarget.value) {
    return ElMessage.warning(t('login.invalidAccount'))
  }
  try {
    const result = await sendCode({
      target: codeTarget.value,
      target_type: codeType.value,
      scene: 'login',
    })
    if (result?.debug_code) {
      ElMessage.success(t('login.debugCode', { code: result.debug_code }))
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

async function finish(data) {
  store.setSession(data)
  router.replace(route.query.redirect || '/')
}

async function loginCode() {
  if (!validTarget.value || code.value.length !== 6) {
    return ElMessage.warning(t('login.invalidCodeLogin'))
  }
  loading.value = true
  try {
    if (codeType.value === 'phone') {
      await finish(await loginPhoneCode({ phone: codeTarget.value, code: code.value }))
    } else {
      await finish(await loginEmailCode({ email: codeTarget.value, code: code.value }))
    }
  } finally {
    loading.value = false
  }
}

async function loginPasswordForm() {
  if (!email.value || !password.value) {
    return ElMessage.warning(t('login.invalidPasswordLogin'))
  }
  loading.value = true
  try {
    await finish(await loginPassword({ email: email.value, password: password.value }))
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
