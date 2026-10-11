<template>
  <el-form @submit.prevent="$emit('submit')">
    <el-form-item>
      <el-input
        :model-value="target"
        @update:model-value="$emit('update:target', $event)"
        :placeholder="targetType === 'email' ? t('codeForm.email') : t('codeForm.phone')"
      />
    </el-form-item>

    <el-form-item>
      <div class="code-row">
        <el-input
          :model-value="code"
          @update:model-value="$emit('update:code', $event)"
          :placeholder="t('codeForm.codePlaceholder')"
        />
        <el-button class="code-btn" @click="send" :disabled="countdown > 0">
          {{ countdown ? t('codeForm.retryIn', { seconds: countdown }) : t('codeForm.sendCode') }}
        </el-button>
      </div>
    </el-form-item>

    <el-button type="primary" native-type="submit" class="full">{{ t('codeForm.login') }}</el-button>
  </el-form>
</template>

<script setup>
import { ref } from 'vue'
import { sendCode } from '../api/auth'
import { ElMessage } from 'element-plus'
import { useI18n } from '../i18n'

const { t } = useI18n()

const props = defineProps({
  target: String,
  targetType: String,
  code: String,
})
defineEmits(['update:target', 'update:code', 'submit'])

const countdown = ref(0)
let timer = null

async function send() {
  if (!props.target) {
    return ElMessage.warning(t('codeForm.fillAccount'))
  }
  try {
    const result = await sendCode({
      target: props.target,
      target_type: props.targetType,
      scene: 'login',
    })
    if (result?.debug_code) {
      ElMessage.success(t('codeForm.debugCode', { code: result.debug_code }))
    }
    countdown.value = 60
    timer = setInterval(() => {
      countdown.value--
      if (!countdown.value) {
        clearInterval(timer)
        timer = null
      }
    }, 1000)
  } catch {
    // 失败不启动倒计时
  }
}
</script>

<style scoped>
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
}
</style>
