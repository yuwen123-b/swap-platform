<template>
  <section class="page" v-loading="loading">
    <el-button link class="back" @click="$router.back()">{{ t('itemDetail.back') }}</el-button>

    <el-empty
      v-if="!loading && !item"
      class="not-found"
      :description="t('itemDetail.notFoundTitle')"
    >
      <el-button type="primary" @click="$router.push('/items')">{{ t('itemDetail.notFoundBtn') }}</el-button>
    </el-empty>

    <div v-if="item" class="detail">
      <div class="visual">
        <!-- 360° 已就绪：嵌入可拖拽查看器 -->
        <PanoramaViewer
          v-if="panoStatus === 'ready' && panoViews.front"
          :views="panoViews"
          :original-image="firstImage"
        />
        <!-- 生成中：占位 + loading 动画，不阻塞页面其余部分 -->
        <div v-else-if="panoStatus === 'generating'" class="pano-pending">
          <div class="spinner" aria-hidden="true"></div>
          <p>{{ t('panorama.generating') }}</p>
        </div>
        <img v-else-if="firstImage" :src="firstImage" :alt="item.title" />
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 8V21H3V8"/>
          <path d="M1 3H23V8H1z"/>
          <path d="M10 12H14"/>
        </svg>
      </div>

      <div class="info">
        <span class="chip chip-peach">{{ item.category_name || t('itemDetail.defaultCategory') }}</span>
        <h1 class="title">{{ item.title }}</h1>
        <p class="description muted">{{ item.description || t('itemDetail.noDescription') }}</p>

        <div class="facts">
          <span class="chip chip-teal">{{ conditionText }}</span>
          <span class="chip">{{ modeText }}</span>
          <span class="chip">{{ t('itemDetail.carbonChip', { value: item.carbon_value || 0 }) }}</span>
          <span v-if="item.exchange_mode === 3" class="chip chip-peach">¥ {{ item.price }}</span>
        </div>

        <div class="publisher">
          <span class="publisher-avatar">{{ item.user_id || t('message.neighborShort') }}</span>
          <div>
            <div class="publisher-name">{{ t('itemDetail.publisherName', { id: item.user_id }) }}</div>
            <div class="muted publisher-sub">{{ t('itemDetail.publisherSub') }}</div>
          </div>
        </div>

        <el-button type="primary" size="large" class="contact" @click="openContact">{{ t('itemDetail.contactBtn') }}</el-button>
      </div>

      <!-- 联系发布者弹窗 -->
      <el-dialog v-model="contactVisible" :title="t('itemDetail.dialogTitle')" width="420px" append-to-body>
        <div class="contact-dialog">
          <div class="contact-publisher">
            <span class="contact-avatar">{{ item.user_id || t('message.neighborShort') }}</span>
            <div>
              <div class="contact-name">{{ t('itemDetail.publisherName', { id: item.user_id }) }}</div>
              <div class="muted">{{ t('itemDetail.publisherSub') }}</div>
            </div>
          </div>

          <template v-if="item.contact">
            <div class="contact-box">
              <span class="contact-label">{{ t('itemDetail.contactLabel') }}</span>
              <span class="contact-value">{{ item.contact }}</span>
            </div>
            <el-button type="primary" class="contact-action" @click="copyContact">{{ t('itemDetail.copyBtn') }}</el-button>
          </template>
          <template v-else>
            <div class="contact-empty">
              <span class="empty-emoji">📮</span>
              <p>{{ t('itemDetail.contactEmptyTitle') }}</p>
              <span>{{ t('itemDetail.contactEmptyTip') }}</span>
            </div>
            <el-button type="primary" class="contact-action" @click="goMessages">{{ t('itemDetail.goMessage') }}</el-button>
          </template>

          <div class="contact-tips">
            {{ t('itemDetail.tips') }}
          </div>
        </div>
      </el-dialog>
    </div>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getItem } from '../api/item'
import { getPanorama } from '../api/panorama'
import PanoramaViewer from '../components/PanoramaViewer.vue'
import { useI18n } from '../i18n'

const route = useRoute()
const router = useRouter()
const item = ref(null)
const loading = ref(true)
const { t } = useI18n()

/* ---------- 360° 视图 ---------- */
const panoStatus = ref('none')
const panoViews = ref({})
let panoTimer = null

async function loadPanorama() {
  try {
    const data = await getPanorama(route.params.id)
    panoStatus.value = data.status || 'none'
    panoViews.value = data.views || {}
    // 生成中：每 3 秒轮询一次，直到 ready / failed
    if (panoStatus.value === 'generating') {
      panoTimer = setInterval(loadPanorama, 3000)
    } else {
      clearInterval(panoTimer)
      panoTimer = null
    }
  } catch {
    panoStatus.value = 'none'
  }
}

onBeforeUnmount(() => clearInterval(panoTimer))

/* ---------- 联系发布者 ---------- */
const contactVisible = ref(false)

function openContact() {
  contactVisible.value = true
}

function goMessages() {
  contactVisible.value = false
  router.push({
    path: '/messages',
    query: {
      otherUserId: String(item.value?.user_id),
      ...(item.value?.id ? { itemId: String(item.value.id) } : {}),
    },
  })
}

async function copyContact() {
  const text = item.value?.contact
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success(t('itemDetail.copyOk'))
  } catch {
    // 非安全上下文（http）下 clipboard API 不可用时的兜底
    const input = document.createElement('textarea')
    input.value = text
    input.style.position = 'fixed'
    input.style.opacity = '0'
    document.body.appendChild(input)
    input.select()
    try {
      document.execCommand('copy')
      ElMessage.success(t('itemDetail.copyOk'))
    } catch {
      ElMessage.warning(t('itemDetail.copyFail'))
    }
    document.body.removeChild(input)
  }
}

// 模式/成色：渲染时走 i18n，语言切换即时更新
const MODE_KEY = { 1: 'modeGift', 2: 'modeSwap', 3: 'modeLowPrice' }
const modeText = computed(() =>
  t(`itemList.${MODE_KEY[item.value?.exchange_mode] || 'modeSwap'}`),
)
const conditionText = computed(() => {
  const key = `home.condition${item.value?.condition_level}`
  const text = t(key)
  return text === key ? t('home.conditionGood') : text
})

const firstImage = computed(() => {
  const raw = item.value?.images
  if (!raw) return ''
  if (Array.isArray(raw)) return raw[0] || ''
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) && parsed.length ? parsed[0] : ''
  } catch {
    return ''
  }
})

onMounted(async () => {
  try {
    item.value = await getItem(route.params.id)
  } catch {
    // 物品不存在（如首页示例卡片）或网络异常时，展示「物品不存在」占位
    item.value = null
  } finally {
    loading.value = false
  }
  loadPanorama()
})
</script>

<style scoped>
.back {
  color: var(--text-secondary);
}

.not-found {
  margin-top: 60px;
}

.detail {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 60px;
  align-items: center;
  margin-top: 28px;
}

.visual {
  height: 430px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, var(--green-softer), var(--teal-soft));
  border-radius: 12px;
  overflow: hidden;
}

.visual svg {
  width: 90px;
  height: 90px;
  color: var(--green-primary);
  opacity: 0.5;
}

/* 360° 生成中占位：loading 动画 + 提示，不阻塞页面 */
.pano-pending {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  color: var(--green-primary);
  font-size: 15px;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid rgba(47, 133, 90, 0.2);
  border-top-color: var(--green-primary);
  border-radius: 50%;
  animation: pano-spin 0.9s linear infinite;
}

@keyframes pano-spin {
  to { transform: rotate(360deg); }
}

.visual .pano-viewer {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 8px;
  box-sizing: border-box;
}

.visual img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.title {
  font-size: 34px;
  margin: 16px 0 14px;
  line-height: 1.25;
}

.description {
  font-size: 16px;
  line-height: 1.85;
}

.facts {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin: 26px 0;
}

.publisher {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  background: var(--green-softer);
  border-radius: var(--r-md);
  margin-bottom: 26px;
}

.publisher-avatar {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--green-primary), var(--teal));
  color: #fff;
  font-weight: 600;
}

.publisher-name {
  font-weight: 600;
  font-size: 14px;
}

.publisher-sub {
  font-size: 12px;
  margin-top: 2px;
}

.contact {
  box-shadow: var(--shadow-btn);
}

/* ---------- 联系发布者弹窗 ---------- */
.contact-dialog {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.contact-publisher {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  background: var(--green-softer, #f1f9f3);
  border-radius: var(--r-md, 12px);
}

.contact-avatar {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: linear-gradient(135deg, #4caf50, #2e7d32);
  color: #fff;
  font-weight: 700;
}

.contact-name {
  font-weight: 700;
  font-size: 15px;
  color: #1b3a26;
}

.contact-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 18px 16px;
  border: 1px solid rgba(76, 175, 80, 0.3);
  border-radius: var(--r-md, 12px);
  background: #fff;
}

.contact-label {
  font-size: 12px;
  color: #63786d;
}

.contact-value {
  font-size: 20px;
  font-weight: 700;
  color: #2e7d32;
  letter-spacing: 0.5px;
}

.contact-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 22px 16px;
  border: 1px dashed rgba(76, 175, 80, 0.4);
  border-radius: var(--r-md, 12px);
  text-align: center;
}

.empty-emoji {
  font-size: 34px;
}

.contact-empty p {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: #1b3a26;
}

.contact-empty span {
  font-size: 13px;
  line-height: 1.7;
  color: #63786d;
}

.contact-action {
  width: 100%;
}

.contact-tips {
  font-size: 12.5px;
  color: #63786d;
  text-align: center;
  line-height: 1.7;
}

@media (max-width: 700px) {
  .detail {
    grid-template-columns: 1fr;
    gap: 30px;
  }

  .visual {
    height: 280px;
  }
}
</style>
