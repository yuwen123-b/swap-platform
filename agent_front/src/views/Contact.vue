<template>
  <section class="page contact-page">
    <div class="page-head">
      <div class="eyebrow">Contact Us</div>
      <h1 class="page-title">{{ t('contact.titleLead') }}<span class="gradient-text">{{ t('contact.titleHighlight') }}</span></h1>
      <p class="page-sub muted">{{ t('contact.subtitle') }}</p>
    </div>

    <!-- 客服信息 -->
    <div class="info-grid">
      <div class="panel info-card">
        <span class="info-icon">✉️</span>
        <h2 class="info-title">{{ t('contact.emailTitle') }}</h2>
        <p class="info-value">support@xianwu-huanxin.com</p>
        <p class="info-note">{{ t('contact.emailNote') }}</p>
      </div>
      <div class="panel info-card">
        <span class="info-icon">📞</span>
        <h2 class="info-title">{{ t('contact.phoneTitle') }}</h2>
        <p class="info-value">400-880-2026</p>
        <p class="info-note">{{ t('contact.phoneNote') }}</p>
      </div>
      <div class="panel info-card">
        <span class="info-icon">💬</span>
        <h2 class="info-title">{{ t('contact.wechatTitle') }}</h2>
        <p class="info-value">xianwu-helper</p>
        <p class="info-note">{{ t('contact.wechatNote') }}</p>
      </div>
    </div>

    <!-- 留言反馈 -->
    <div class="panel form-panel">
      <h2 class="form-title">{{ t('contact.formTitle') }}</h2>
      <p class="form-sub muted">{{ t('contact.formSub') }}</p>

      <el-form label-position="top" @submit.prevent="submitFeedback">
        <div class="form-row">
          <el-form-item :label="t('contact.nameLabel')" required>
            <el-input v-model="form.name" :placeholder="t('contact.namePlaceholder')" maxlength="20" />
          </el-form-item>
          <el-form-item :label="t('contact.contactLabel')" required>
            <el-input
              v-model="form.contact"
              :placeholder="t('contact.contactPlaceholder')"
              maxlength="50"
            />
          </el-form-item>
        </div>
        <el-form-item :label="t('contact.messageLabel')" required>
          <el-input
            v-model="form.message"
            type="textarea"
            :rows="5"
            maxlength="300"
            show-word-limit
            :placeholder="t('contact.messagePlaceholder')"
          />
        </el-form-item>
        <div class="form-actions">
          <el-button type="primary" native-type="submit" :loading="submitting">
            {{ t('contact.submit') }}
          </el-button>
        </div>
      </el-form>
    </div>
  </section>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from '../i18n'

const { t } = useI18n()

const form = reactive({
  name: '',
  contact: '',
  message: '',
})

const submitting = ref(false)

async function submitFeedback() {
  if (!form.name.trim() || !form.contact.trim() || !form.message.trim()) {
    ElMessage.warning(t('contact.validateIncomplete'))
    return
  }

  // TODO: 后续接入留言反馈接口（POST /api/v1/feedback），当前先做前端提交反馈
  submitting.value = true
  try {
    await new Promise((resolve) => setTimeout(resolve, 600))
    ElMessage.success(t('contact.submitSuccess'))
    Object.assign(form, { name: '', contact: '', message: '' })
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.page-head {
  text-align: center;
}

.page-sub {
  margin: 6px 0 0;
  font-size: 15px;
}

/* ---------- 通用绿色卡片：白底 / 16px 圆角 / 浅绿边框 ---------- */
.panel {
  padding: 28px 26px;
  background: #fff;
  border: 1px solid rgba(76, 175, 80, 0.22);
  border-radius: 16px;
  transition: transform 0.25s ease, box-shadow 0.25s ease;
}

.panel:hover {
  transform: translateY(-3px);
  box-shadow: 0 14px 30px rgba(46, 125, 50, 0.12);
}

/* ---------- 客服信息 ---------- */
.info-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 18px;
  margin-top: 34px;
}

.info-card {
  text-align: center;
}

.info-icon {
  font-size: 32px;
}

.info-title {
  margin: 12px 0 8px;
  font-size: 16px;
  color: #2e7d32;
}

.info-value {
  margin: 0;
  font-size: 16.5px;
  font-weight: 700;
  color: #1b3a26;
  word-break: break-all;
}

.info-note {
  margin: 8px 0 0;
  font-size: 12.5px;
  color: #63786d;
}

/* ---------- 留言反馈 ---------- */
.form-panel {
  margin-top: 20px;
}

.form-title {
  margin: 0;
  font-size: 19px;
  color: #2e7d32;
}

.form-sub {
  margin: 6px 0 18px;
  font-size: 13.5px;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 800px) {
  .info-grid {
    grid-template-columns: 1fr;
  }

  .form-row {
    grid-template-columns: 1fr;
    gap: 0;
  }
}
</style>
