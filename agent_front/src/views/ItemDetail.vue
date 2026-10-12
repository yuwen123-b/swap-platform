<template>
  <section class="page" v-loading="loading">
    <el-button link class="back" @click="$router.back()">← 返回物品列表</el-button>

    <el-empty
      v-if="!loading && !item"
      class="not-found"
      description="物品不存在或已下架，看看邻居们的其他好物吧"
    >
      <el-button type="primary" @click="$router.push('/items')">去探索物品</el-button>
    </el-empty>

    <div v-if="item" class="detail">
      <div class="visual">
        <!-- 360° 已就绪：Three.js 查看器 -->
        <PanoramaViewer
          v-if="item.panorama_status === 'ready' && item.panorama_views"
          :views="item.panorama_views"
          :original-image="firstImage"
          @error="onPanoError"
        />
        <!-- 生成中：原图 + 角标 -->
        <div v-else-if="item.panorama_status === 'generating'" class="image-wrapper">
          <img v-if="firstImage" :src="firstImage" :alt="item.title" />
          <div class="badge-generating">360° 生成中</div>
        </div>
        <!-- 无 360° 或生成失败：静态图 -->
        <img v-else-if="firstImage" :src="firstImage" :alt="item.title" />
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 8V21H3V8"/>
          <path d="M1 3H23V8H1z"/>
          <path d="M10 12H14"/>
        </svg>
      </div>

      <div class="info">
        <span class="chip chip-peach">{{ item.category_name || '社区好物' }}</span>
        <h1 class="title">{{ item.title }}</h1>
        <p class="description muted">{{ item.description || '发布者没有留下更多描述。' }}</p>

        <div class="facts">
          <span class="chip chip-teal">{{ conditionText }}</span>
          <span class="chip">{{ modeText }}</span>
          <span class="chip">↓ {{ item.carbon_value || 0 }} kg 减碳</span>
          <span v-if="item.exchange_mode === 3" class="chip chip-peach">¥ {{ item.price }}</span>
        </div>

        <div class="publisher">
          <span class="publisher-avatar">{{ item.user_id || '邻' }}</span>
          <div>
            <div class="publisher-name">社区居民 #{{ item.user_id }}</div>
            <div class="muted publisher-sub">邻里之间，真诚交换</div>
          </div>
        </div>

        <el-button type="primary" size="large" class="contact" @click="openContact">联系发布者</el-button>
      </div>

      <!-- 联系发布者弹窗 -->
      <el-dialog v-model="contactVisible" title="联系发布者" width="420px" append-to-body>
        <div class="contact-dialog">
          <div class="contact-publisher">
            <span class="contact-avatar">{{ item.user_id || '邻' }}</span>
            <div>
              <div class="contact-name">社区居民 #{{ item.user_id }}</div>
              <div class="muted">邻里之间，真诚交换</div>
            </div>
          </div>

          <template v-if="item.contact">
            <div class="contact-box">
              <span class="contact-label">发布者留下的联系方式</span>
              <span class="contact-value">{{ item.contact }}</span>
            </div>
            <el-button type="primary" class="contact-action" @click="copyContact">复制联系方式</el-button>
          </template>
          <template v-else>
            <div class="contact-empty">
              <span class="empty-emoji">📮</span>
              <p>发布者暂未公开联系方式</p>
              <span>可以给邻居发私信留言，约好在社区广场当面交换</span>
            </div>
            <el-button type="primary" class="contact-action" @click="goMessages">去留言沟通</el-button>
          </template>

          <div class="contact-tips">
            🌿 温馨提示：礼貌沟通、当面验货、注意保护个人隐私
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

const route = useRoute()
const router = useRouter()
const item = ref(null)
const loading = ref(true)

/* ---------- 360° 视图 ---------- */
let panoTimer = null
let panoPollCount = 0
const PANO_MAX_POLLS = 20

async function loadPanorama() {
  try {
    const data = await getPanorama(route.params.id)
    if (item.value) {
      item.value.panorama_status = data.panorama_status || 'none'
      item.value.panorama_views = data.panorama_views || null
    }
  } catch {
    // 保持现有状态，不影响页面展示
  }
  // 生成中：3 秒后重查，最多 20 次（约 1 分钟）
  if (item.value?.panorama_status === 'generating') {
    if (panoPollCount >= PANO_MAX_POLLS) return
    panoPollCount += 1
    panoTimer = setTimeout(loadPanorama, 3000)
  }
}

function onPanoError() {
  // Three.js 初始化或贴图全部失败：静默降级为静态图
  if (item.value) {
    item.value.panorama_status = 'failed'
    item.value.panorama_views = null
  }
}

onBeforeUnmount(() => clearTimeout(panoTimer))

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
    ElMessage.success('联系方式已复制')
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
      ElMessage.success('联系方式已复制')
    } catch {
      ElMessage.warning('复制失败，请手动记录联系方式')
    }
    document.body.removeChild(input)
  }
}

// 模式/成色
const MODE_TEXT = { 1: '赠送', 2: '交换', 3: '低价转让' }
const modeText = computed(() =>
  MODE_TEXT[item.value?.exchange_mode] || '交换',
)
const CONDITION_TEXT = { 1: '成色一般', 2: '七成新', 3: '八成新', 4: '九成新', 5: '几乎全新' }
const conditionText = computed(() => {
  const level = item.value?.condition_level
  return CONDITION_TEXT[level] || '状态良好'
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
  panoPollCount = 0
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
  position: relative;
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

/* 360° 生成中：原图 + 角标 */
.image-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
}

.image-wrapper img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.badge-generating {
  position: absolute;
  top: 12px;
  right: 12px;
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  background: rgba(47, 133, 90, 0.7);
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
