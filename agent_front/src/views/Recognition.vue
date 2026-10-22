<template>
  <section class="page">
    <div class="eyebrow">AI 能力</div>
    <h1 class="page-title">
      拍一张照片，<br />
      <span class="gradient-text">AI 帮你认出这件旧物。</span>
    </h1>

    <div class="rec-layout">
      <!-- 上传区 -->
      <el-card class="panel" shadow="never">
        <h2 class="panel-title">上传物品照片</h2>

        <!-- 公共上传组件：mode=identify 时保留拖拽落区，并补充「图片上传 / 拍照上传」两个按钮 -->
        <ImageUploader
          v-model="file"
          mode="identify"
          preview-alt="待识别图片"
          :max-size="MAX_IMAGE_SIZE"
        />

        <div class="upload-actions">
          <el-button
            type="primary"
            class="full"
            :loading="loading"
            :disabled="!file"
            @click="recognize"
          >
            {{ loading ? '识别中…' : '开始识别' }}
          </el-button>
          <el-button v-if="file" class="full" plain @click="reset">重新选择</el-button>
        </div>
      </el-card>

      <!-- 结果区 -->
      <el-card class="panel" shadow="never">
        <h2 class="panel-title">识别结果</h2>

        <div v-if="loading" class="result-hint" v-loading="loading" element-loading-text="AI 正在辨认这件物品…" />

        <template v-else-if="result">
          <div class="result-head">
            <strong class="result-name">{{ result.name }}</strong>
            <el-tag type="success" effect="plain">{{ categoryText(result.category) }}</el-tag>
          </div>
          <div class="result-row">
            <span class="muted">成色估计</span>
            <el-rate :model-value="result.condition_level" disabled />
          </div>
          <p class="result-desc">{{ result.description }}</p>
          <div class="result-tags">
            <span v-for="tag in result.tags" :key="tag" class="chip">{{ tag }}</span>
          </div>
          <div class="result-actions">
            <el-button type="primary" plain @click="$router.push('/items')">去发布 / 逛逛物品</el-button>
            <el-button @click="reset">再识别一件</el-button>
          </div>
          <small v-if="result.engine === 'mock'" class="muted engine-tip">
            演示模式结果：后端未配置多模态模型（LLM_VL_MODEL），配置后即可真实识别。
          </small>
        </template>

        <el-empty v-else description="上传一张物品照片，识别结果会显示在这里" />
      </el-card>
    </div>
  </section>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import ImageUploader from '../components/ImageUploader.vue'
import { recognitionImage } from '../api/ai'

// 与后端 app/api/v1/ai.py 的 MAX_IMAGE_SIZE 保持一致
const MAX_IMAGE_SIZE = 5 * 1024 * 1024

const file = ref(null)
const loading = ref(false)
const result = ref(null)

const CATEGORY_KEY = {
  数码电子: '数码电子',
  家居家电: '家居家电',
  图书文具: '图书文具',
  服饰鞋包: '服饰鞋包',
  母婴用品: '母婴用品',
  运动户外: '运动户外',
  美妆个护: '美妆个护',
  其他闲置: '其他闲置',
}

function categoryText(category) {
  return CATEGORY_KEY[category] || category
}

// 换图后清空上一件物品的结果，避免「新图配旧结果」
watch(file, () => {
  result.value = null
})

async function recognize() {
  if (!file.value) return
  loading.value = true
  try {
    const formData = new FormData()
    formData.append('image', file.value)
    result.value = await recognitionImage(formData)
    ElMessage.success('识别完成')
  } catch {
    // 错误提示已由请求拦截器处理
  } finally {
    loading.value = false
  }
}

function reset() {
  file.value = null
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
