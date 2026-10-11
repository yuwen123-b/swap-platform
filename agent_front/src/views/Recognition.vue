<template>
  <section class="page">
    <div class="eyebrow">{{ t('recognition.eyebrow') }}</div>
    <h1 class="page-title">
      {{ t('recognition.titleLead') }}<br />
      <span class="gradient-text">{{ t('recognition.titleHighlight') }}</span>
    </h1>

    <div class="rec-layout">
      <!-- 上传区 -->
      <el-card class="panel" shadow="never">
        <h2 class="panel-title">{{ t('recognition.uploadTitle') }}</h2>
        <el-upload
          drag
          accept="image/jpeg,image/png,image/webp,image/gif"
          :auto-upload="false"
          :show-file-list="false"
          :on-change="onFileChange"
        >
          <div v-if="previewUrl" class="preview-wrap">
            <img :src="previewUrl" :alt="t('recognition.previewAlt')" />
          </div>
          <div v-else class="upload-empty">
            <el-icon class="upload-icon"><UploadFilled /></el-icon>
            <div class="upload-tip">{{ t('recognition.uploadTip') }}<em>{{ t('recognition.uploadTipEm') }}</em></div>
            <div class="muted upload-sub">{{ t('recognition.uploadSub') }}</div>
          </div>
        </el-upload>

        <div class="upload-actions">
          <el-button
            type="primary"
            class="full"
            :loading="loading"
            :disabled="!file"
            @click="recognize"
          >
            {{ loading ? t('recognition.recognizing') : t('recognition.startRecognize') }}
          </el-button>
          <el-button v-if="file" class="full" plain @click="reset">{{ t('recognition.reselect') }}</el-button>
        </div>
      </el-card>

      <!-- 结果区 -->
      <el-card class="panel" shadow="never">
        <h2 class="panel-title">{{ t('recognition.resultTitle') }}</h2>

        <div v-if="loading" class="result-hint" v-loading="loading" :element-loading-text="t('recognition.loadingText')" />

        <template v-else-if="result">
          <div class="result-head">
            <strong class="result-name">{{ result.name }}</strong>
            <el-tag type="success" effect="plain">{{ categoryText(result.category) }}</el-tag>
          </div>
          <div class="result-row">
            <span class="muted">{{ t('recognition.conditionLabel') }}</span>
            <el-rate :model-value="result.condition_level" disabled />
          </div>
          <p class="result-desc">{{ result.description }}</p>
          <div class="result-tags">
            <span v-for="tag in result.tags" :key="tag" class="chip">{{ tag }}</span>
          </div>
          <div class="result-actions">
            <el-button type="primary" plain @click="$router.push('/items')">{{ t('recognition.browseOrPublish') }}</el-button>
            <el-button @click="reset">{{ t('recognition.recognizeAgain') }}</el-button>
          </div>
          <small v-if="result.engine === 'mock'" class="muted engine-tip">
            {{ t('recognition.mockTip') }}
          </small>
        </template>

        <el-empty v-else :description="t('recognition.emptyResult')" />
      </el-card>
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { recognitionImage } from '../api/ai'
import { useI18n } from '../i18n'

const { t } = useI18n()

const file = ref(null)
const previewUrl = ref('')
const loading = ref(false)
const result = ref(null)

const CATEGORY_KEY = {
  数码电子: 'recognition.catDigital',
  家居家电: 'recognition.catAppliance',
  图书文具: 'recognition.catBooks',
  服饰鞋包: 'recognition.catClothing',
  母婴用品: 'recognition.catBaby',
  运动户外: 'recognition.catSports',
  美妆个护: 'recognition.catBeauty',
  其他闲置: 'recognition.catOther',
}

function categoryText(category) {
  const key = CATEGORY_KEY[category]
  if (!key) return category
  const text = t(key)
  return text === key ? category : text
}

function onFileChange(uploadFile) {
  const raw = uploadFile.raw
  if (!raw) return
  if (!['image/jpeg', 'image/png', 'image/webp', 'image/gif'].includes(raw.type)) {
    return ElMessage.warning(t('recognition.formatWarning'))
  }
  if (raw.size > 5 * 1024 * 1024) {
    return ElMessage.warning(t('recognition.sizeWarning'))
  }
  file.value = raw
  previewUrl.value = URL.createObjectURL(raw)
  result.value = null
}

async function recognize() {
  if (!file.value) return
  loading.value = true
  try {
    const formData = new FormData()
    formData.append('image', file.value)
    result.value = await recognitionImage(formData)
    ElMessage.success(t('recognition.recognizeOk'))
  } catch {
    // 错误提示已由请求拦截器处理
  } finally {
    loading.value = false
  }
}

function reset() {
  file.value = null
  previewUrl.value = ''
  result.value = null
}
</script>

<style scoped>
.rec-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  margin-top: 36px;
}

.panel {
  border: 1px solid var(--border-soft);
  border-radius: var(--r-lg, 16px);
}

.panel-title {
  font-size: 19px;
  margin-bottom: 20px;
}

.upload-empty {
  padding: 34px 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.upload-icon {
  font-size: 40px;
  color: var(--green-primary);
  opacity: 0.7;
}

.upload-tip {
  font-size: 14px;
  color: var(--text-primary, #1f2937);
}

.upload-tip em {
  color: var(--green-primary);
  font-style: normal;
  font-weight: 600;
}

.upload-sub {
  font-size: 12px;
}

.preview-wrap {
  max-height: 300px;
  display: grid;
  place-items: center;
}

.preview-wrap img {
  max-width: 100%;
  max-height: 280px;
  border-radius: 12px;
  object-fit: contain;
}

.upload-actions {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.full {
  width: 100%;
}

.result-hint {
  min-height: 220px;
}

.result-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.result-name {
  font-size: 20px;
}

.result-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

.result-desc {
  font-size: 14px;
  line-height: 1.8;
  color: var(--text-secondary, #4b5563);
  margin: 0 0 16px;
}

.result-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 20px;
}

.chip {
  padding: 4px 12px;
  border-radius: 999px;
  background: var(--green-soft, #e6f4ea);
  color: var(--green-active, #276749);
  font-size: 12px;
}

.result-actions {
  display: flex;
  gap: 12px;
}

.engine-tip {
  display: block;
  margin-top: 14px;
}

@media (max-width: 900px) {
  .rec-layout {
    grid-template-columns: 1fr;
  }
}
</style>
