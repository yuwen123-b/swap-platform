<template>
  <section class="page" v-loading="loading">
    <!-- 顶部操作栏：左侧返回，右侧收藏（已收藏为实心心形） -->
    <div class="detail-topbar">
      <el-button link class="back" @click="$router.back()">← 返回物品列表</el-button>
      <button
        v-if="item"
        type="button"
        class="fav-btn"
        :class="{ active: favorited }"
        :aria-pressed="favorited"
        :aria-label="favorited ? '取消收藏该物品' : '收藏该物品'"
        :title="favorited ? '取消收藏' : '收藏'"
        :disabled="favLoading"
        @click="toggleFavorite"
      >
        <svg
          viewBox="0 0 24 24"
          aria-hidden="true"
          :fill="favorited ? 'currentColor' : 'none'"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.6l-1-1a5.5 5.5 0 1 0-7.8 7.8l1 1L12 21.2l7.8-7.8 1-1a5.5 5.5 0 0 0 0-7.8z" />
        </svg>
        <span>{{ favorited ? '已收藏' : '收藏' }}</span>
      </button>
    </div>

    <el-empty
      v-if="!loading && !item"
      class="not-found"
      description="物品不存在或已下架，看看邻居们的其他好物吧"
    >
      <el-button type="primary" @click="$router.push('/items')">去探索物品</el-button>
    </el-empty>

    <div v-if="item" class="detail">
      <div class="visual">
        <!-- 展示优先级：3D 模型 ready → 360° 四视图 ready → 生成中角标 → 静态图 -->
        <!-- 3D 已就绪：Three.js GLTF 查看器（key 变化触发重挂载，用于签名刷新重试） -->
        <ModelViewer
          v-if="modelReady"
          :key="modelViewerKey"
          :model-url="item.model_url"
          :original-image="firstImage"
          @error="onModelError"
        />
        <!-- 360° 已就绪：Three.js 查看器（key 变化触发重挂载，用于签名刷新重试） -->
        <PanoramaViewer
          v-else-if="panoReady"
          :key="panoViewerKey"
          :views="item.panorama_views"
          :original-image="firstImage"
          @error="onPanoError"
        />
        <!-- 生成中：原图 + 角标（3D 优先于 360° 提示，两者互不冲突） -->
        <div
          v-else-if="modelGenerating || item.panorama_status === 'generating'"
          class="image-wrapper"
        >
          <img v-if="firstImage" :src="firstImage" :alt="item.title" />
          <div class="badge-generating">
            {{ modelGenerating ? '3D 模型生成中' : '360° 生成中' }}
          </div>
        </div>
        <!-- 无 3D / 无 360° 或生成失败：静态图 -->
        <img v-else-if="firstImage" :src="firstImage" :alt="item.title" />
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 8V21H3V8"/>
          <path d="M1 3H23V8H1z"/>
          <path d="M10 12H14"/>
        </svg>
        <!-- 所有者的生成入口：3D / 360° 各自独立，均仅在「未生成 / 生成失败」时显示（D2 决策） -->
        <div v-if="canGenerateModel || canGeneratePanorama" class="generate-actions">
          <button
            v-if="canGenerateModel"
            type="button"
            class="pano-generate-btn"
            :disabled="modelSubmitting"
            @click="generateModel"
          >
            {{ item.model_status === 'failed' ? '重新生成 3D 模型' : '生成 3D 模型' }}
          </button>
          <button
            v-if="canGeneratePanorama"
            type="button"
            class="pano-generate-btn"
            :disabled="panoSubmitting"
            @click="generatePanorama"
          >
            {{ item.panorama_status === 'failed' ? '重新生成 360°' : '生成 360°' }}
          </button>
          <!-- 失败原因：仅 failed 且有原因时展示（原文可能在英文，见 modelFailText 的兜底翻译）。
               以前只把状态悄悄改回 failed、按钮变回「重新生成」，用户以为白点了 —— 这是
               「点击无反应」的主要来源。原文放 title，长文本两行截断。 -->
          <p
            v-if="item.model_status === 'failed' && modelFailHint"
            class="model-fail-hint"
            :title="item.model_error"
          >
            {{ modelFailHint }}
          </p>
        </div>

        <!-- 3D 生成中：**独立浮层**，刻意不参与上面的降级链 ——
             物品若已有 360°，降级链会优先渲染 360° 查看器，点击「生成 3D」后
             画面原本毫无变化（只有按钮消失 + 一个几秒后消失的 toast），
             用户视角就是「点了没反应」。这里无论当前展示哪个查看器都给出可见反馈。 -->
        <div v-if="modelGenerating" class="model-generating-tip" role="status" aria-live="polite">
          <span class="tip-spinner" aria-hidden="true"></span>
          <span>3D 模型生成中，约 2-4 分钟</span>
        </div>
      </div>

      <div class="info">
        <span class="chip chip-peach">{{ item.category_name || '社区好物' }}</span>
        <h1 class="title">{{ item.title }}</h1>
        <p class="description muted">{{ item.description || '发布者没有留下更多描述。' }}</p>

        <div class="facts">
          <span class="chip chip-teal">{{ conditionText }}</span>
          <span class="chip">{{ modeText }}</span>
          <span class="chip">↓ {{ item.carbon_value || 0 }} kg 减碳</span>
        </div>

        <!-- 低价转让：价格单独醒目展示（社区调性，不做成二手电商的「购买价」） -->
        <div v-if="isSellMode" class="price-banner">
          <span class="price-label">转让价</span>
          <span class="price-value">¥ {{ formatPrice(item.price) }}</span>
          <span class="price-hint">邻里价，图的是它继续被用下去</span>
        </div>

        <div class="publisher">
          <span class="publisher-avatar">{{ item.user_id || '邻' }}</span>
          <div>
            <div class="publisher-name">社区居民 #{{ item.user_id }}</div>
            <div class="muted publisher-sub">邻里之间，真诚交换</div>
          </div>
        </div>

        <div class="action-row">
          <!-- 自己的物品 / 非在售物品不显示行动按钮 -->
          <el-button
            v-if="canSwap"
            type="primary"
            size="large"
            class="swap-btn"
            @click="openSwap"
          >
            {{ actionMeta.label }}
          </el-button>
          <el-button type="primary" size="large" class="contact" @click="openContact">联系发布者</el-button>
        </div>
      </div>

      <!-- 发起意向弹窗：标题 / 文案按交易方式（免费送 / 交换 / 低价转让）切换 -->
      <el-dialog v-model="swapVisible" :title="actionMeta.dialogTitle" width="420px" append-to-body>
        <div class="swap-dialog">
          <div class="swap-item">
            <span class="swap-thumb">
              <img v-if="firstImage" :src="firstImage" :alt="item.title" />
              <span v-else aria-hidden="true">📦</span>
            </span>
            <span class="swap-item-info">
              <span class="swap-item-title">{{ item.title }}</span>
              <span class="muted swap-item-sub">
                {{ actionMeta.subText }}
                <template v-if="isSellMode"> · 转让价 ¥ {{ formatPrice(item.price) }}</template>
              </span>
            </span>
          </div>

          <el-input
            v-model="swapMessage"
            type="textarea"
            :rows="4"
            maxlength="200"
            show-word-limit
            resize="none"
            :placeholder="actionMeta.placeholder"
          />

          <div class="swap-tips">
            🌿 {{ actionMeta.tip }}
          </div>
        </div>
        <template #footer>
          <el-button @click="swapVisible = false">取消</el-button>
          <el-button type="primary" :loading="swapSubmitting" @click="submitSwap">
            确认发起
          </el-button>
        </template>
      </el-dialog>

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
import { addFavorite, checkFavorite, removeFavorite } from '../api/user'
import { createOrder } from '../api/order'
import { getPanorama, triggerPanorama } from '../api/panorama'
import { getModel, triggerModel } from '../api/model'
import { useUserStore } from '../store/user'
import PanoramaViewer from '../components/PanoramaViewer.vue'
import ModelViewer from '../components/ModelViewer.vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const item = ref(null)
const loading = ref(true)

/* ---------- 收藏 ---------- */
// 初始值由 check 接口决定：避免用户先看到「未收藏」、点击后才发现其实已收藏
const favorited = ref(false)
const favLoading = ref(false)

async function loadFavoriteState() {
  // 未登录不请求（接口需鉴权），保持空心即可
  if (!userStore.isLoggedIn || !route.params.id) return
  try {
    const data = await checkFavorite(route.params.id)
    favorited.value = Boolean(data?.favorited)
  } catch {
    // 查询失败保持「未收藏」默认值，不阻塞详情页展示
  }
}

async function toggleFavorite() {
  if (!item.value || favLoading.value) return
  if (!userStore.isLoggedIn) {
    ElMessage.warning('请先登录后再收藏')
    router.push({ path: '/login', query: { redirect: route.fullPath } })
    return
  }

  favLoading.value = true
  try {
    if (favorited.value) {
      await removeFavorite(item.value.id)
      favorited.value = false
      ElMessage.success('已取消收藏')
    } else {
      const data = await addFavorite(item.value.id)
      favorited.value = true
      // 后端幂等：重复收藏时 created=false，给出对应文案
      ElMessage.success(data?.created === false ? '你已收藏过该物品' : '收藏成功')
    }
  } catch {
    // 失败不改动本地状态，错误提示由请求拦截器统一处理
  } finally {
    favLoading.value = false
  }
}

/* ---------- 我要换 / 我想要（发起意向） ---------- */
// 显示条件：物品存在、处于「在售」、且不是自己发布的
const currentUserId = computed(() => userStore.user?.id ?? null)
const isOwner = computed(
  () => Boolean(currentUserId.value && item.value?.user_id === currentUserId.value),
)
const canSwap = computed(
  () => Boolean(item.value) && Number(item.value.status) === 1 && !isOwner.value,
)

// 交易方式：与 item.exchange_mode 列注释同口径（1=免费送 2=交换 3=低价转让）
const isSellMode = computed(() => Number(item.value?.exchange_mode) === 3)

function formatPrice(value) {
  const num = Number(value)
  if (!Number.isFinite(num)) return '0.00'
  return num.toFixed(2)
}

// 按钮 / 弹窗文案按交易方式切换。
// 产品口径：不用「购买 / 下单 / 买家」，统一为「我想要 / 接手」这类邻里语感。
const actionMeta = computed(() => {
  const mode = Number(item.value?.exchange_mode ?? 2)
  if (mode === 1) {
    return {
      label: '我想要',
      dialogTitle: '我想要（免费送）',
      subText: '这件物品免费送，留句话让邻居知道是你',
      placeholder: '想说什么？（选填）例如：我住在 3 号楼，周末下午方便来取',
      tip: '温馨提示：对方确认后会进入「交换中」，请按约定时间完成交接',
    }
  }
  if (mode === 3) {
    return {
      label: '我想要',
      dialogTitle: '我想要（低价转让）',
      subText: '接手这件物品，留句话约好时间与地点',
      placeholder: '想说什么？（选填）例如：我住 5 号楼，今晚就可以过去接手',
      tip: '温馨提示：对方确认后会进入「交换中」，转让价由你们当面结清',
    }
  }
  return {
    label: '我要换',
    dialogTitle: '发起交换',
    subText: '给对方留句话，约好交换的时间与地点',
    placeholder: '想说什么？（选填）例如：我住在 3 号楼，周末下午方便面交',
    tip: '温馨提示：对方确认后会进入「交换中」，请按约定时间完成交接',
  }
})

const swapVisible = ref(false)
const swapSubmitting = ref(false)
const swapMessage = ref('')

function openSwap() {
  if (!item.value) return
  if (!userStore.isLoggedIn) {
    ElMessage.warning('请先登录后再发起')
    router.push({ path: '/login', query: { redirect: route.fullPath } })
    return
  }
  swapMessage.value = ''
  swapVisible.value = true
}

// 后端业务错误走 { code, message } 外壳（HTTP 4xx），axios error 里取 response.data.message
function readErrorText(error) {
  return error?.response?.data?.message || error?.message || ''
}

// 在弹窗内按错误类型给具体中文提示。
// createOrder 已传 skipErrorToast，拦截器不会再弹一次，这里不会出现双弹。
function swapErrorText(error) {
  const text = readErrorText(error)
  const status = error?.response?.status
  if (text.includes('不能交换自己的物品')) return '不能交换自己的物品'
  if (text.includes('已下架') || text.includes('已被交换')) return '该物品已下架或已被交换'
  if (text.includes('发起过交换请求')) return '你已对该物品发起过交换请求'
  if (text.includes('物品不存在')) return '物品不存在或已被删除'
  if (text.includes('留言不能超过')) return text
  if (status === 401) return '登录状态已失效，请重新登录'
  if (status === 409) return text || '该交换的积分已发放过，请刷新后重试'
  return text || '发起交换失败，请稍后再试'
}

async function submitSwap() {
  if (!item.value || swapSubmitting.value) return
  swapSubmitting.value = true
  try {
    // skipErrorToast 由 api/order.js 内的 createOrder 统一带上
    await createOrder(item.value.id, swapMessage.value.trim())
    swapVisible.value = false
    swapMessage.value = ''
    ElMessage.success('请求已发送，等待邻居确认')
  } catch (error) {
    ElMessage.error(swapErrorText(error))
  } finally {
    swapSubmitting.value = false
  }
}

/* ---------- 360° 视图 ---------- */
let panoTimer = null
let panoPollCount = 0
// wanx 三张视角图约 45-60s，40 次 × 3s = 120s 上限；后端另有 10 分钟卡死兜底
const PANO_MAX_POLLS = 40
const panoViewerKey = ref(0)
let panoRetryCount = 0
const panoSubmitting = ref(false)

// 所有者的生成入口：仅未生成 / 生成失败时可见（生成中由角标表达）
const canGeneratePanorama = computed(
  () =>
    Boolean(item.value) &&
    isOwner.value &&
    ['none', 'failed'].includes(item.value.panorama_status || 'none'),
)

async function generatePanorama() {
  if (!item.value || panoSubmitting.value) return
  if (!userStore.isLoggedIn) {
    ElMessage.warning('请先登录后再生成 360° 视图')
    router.push({ path: '/login', query: { redirect: route.fullPath } })
    return
  }
  panoSubmitting.value = true
  try {
    await triggerPanorama(item.value.id)
    item.value.panorama_status = 'generating'
    item.value.panorama_views = null
    ElMessage.success('360° 视图开始生成，约 1 分钟后可查看')
    panoPollCount = 0
    panoTimer = setTimeout(loadPanorama, 3000)
  } catch {
    // 错误文案由请求拦截器统一提示；本地状态保持不变，按钮可重试
  } finally {
    panoSubmitting.value = false
  }
}

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
  // 生成中：3 秒后重查，最多 40 次（约 2 分钟）
  if (item.value?.panorama_status === 'generating') {
    if (panoPollCount >= PANO_MAX_POLLS) {
      ElMessage.info('360° 视图仍在生成中，稍后刷新页面即可查看')
      return
    }
    panoPollCount += 1
    panoTimer = setTimeout(loadPanorama, 3000)
  }
}

async function onPanoError() {
  // 已知场景：签名 URL 有效期 1 小时，页面久置后首次进入 360° 会全部 404。
  // 先重新拉详情刷新签名并重挂载一次；仍失败才降级为静态图。
  if (item.value && panoRetryCount < 1) {
    panoRetryCount += 1
    try {
      const fresh = await getItem(route.params.id)
      if (fresh?.panorama_status === 'ready' && fresh.panorama_views) {
        item.value.panorama_views = fresh.panorama_views
        panoViewerKey.value += 1
        return
      }
    } catch {
      // 拉取失败走降级
    }
  }
  // Three.js 初始化或贴图二次失败：静默降级为静态图
  if (item.value) {
    item.value.panorama_status = 'failed'
    item.value.panorama_views = null
  }
}

onBeforeUnmount(() => {
  clearTimeout(panoTimer)
  clearTimeout(modelTimer)
})

/* ---------- 3D 模型（多服务商：腾讯混元 3D / 百炼 Tripo） ---------- */
let modelTimer = null
let modelPollCount = 0
// 常规 1-3 分钟（混元极速版官方口径 ≤90s，Tripo 2-4 分钟）；
// 3s × 120 = 360s，**必须长于**后端 300s 的卡死兜底
// （原先 80 次 = 240s < 300s，会出现「前端已放弃、后端稍后才判 failed」的盲区，
//  且本地状态永远停在 generating → 按钮再也回不来，只剩刷新一条路）。
const MODEL_MAX_POLLS = 120
const modelViewerKey = ref(0)
let modelRetryCount = 0
const modelSubmitting = ref(false)

// 已知上游报错 → 可执行的中文提示（用户不该去读上游英文原文）
function modelFailText(raw) {
  const text = String(raw || '').trim()
  if (!text) return '3D 模型生成失败，可点击重试'
  // 后端已归一化的中文原因（混元分支会把并发/欠费/鉴权/风控翻译成中文并附原始信息）
  // → 原样展示，不再二次包装，避免丢掉可执行的细节
  if (/[\u4e00-\u9fa5]/.test(text)) return text
  // 百炼 Tripo（回退分支）
  if (/not activated/i.test(text)) {
    return '百炼 Tripo 服务未开通或未生效，请在阿里云百炼控制台确认开通状态后重试'
  }
  if (/invalid api-?key|unauthorized|authentication/i.test(text)) {
    return '百炼 API Key 无效或已过期，请检查 DASHSCOPE_API_KEY'
  }
  if (/download|fetch|image/i.test(text)) {
    return `源图未能被抓取，请确认公网地址（PUBLIC_BASE_URL）可用：${text}`
  }
  // 腾讯混元 3D（TokenHub 网关）：上游英文报错统一收敛成一句用户能懂的话
  if (/tokenhub|tencentmaas|hy-3d|hunyuan|混元/i.test(text)) {
    return `腾讯混元 3D 服务暂时不可用，请稍后重试（${text}）`
  }
  return `3D 模型生成失败：${text}`
}

// 页面刷新后仍能看到失败原因（不再只依赖那个一次性的 toast）
const modelFailHint = computed(() =>
  item.value?.model_status === 'failed' ? modelFailText(item.value?.model_error) : '',
)

// 3D 就绪：必须是 ready 且有可用（签名）地址，否则回落到 360° / 静态图
const modelReady = computed(
  () =>
    Boolean(item.value) &&
    item.value.model_status === 'ready' &&
    Boolean(item.value.model_url),
)
const modelGenerating = computed(() => item.value?.model_status === 'generating')

// 360° 就绪：抽成 computed 供降级链复用（原先是模板里的一行长表达式）
const panoReady = computed(
  () =>
    Boolean(item.value) &&
    item.value.panorama_status === 'ready' &&
    Boolean(item.value.panorama_views),
)

// 所有者的 3D 生成入口：开关由后端下发（model_3d_enabled），且仅在未生成 / 失败时可见
const canGenerateModel = computed(
  () =>
    Boolean(item.value) &&
    isOwner.value &&
    Boolean(item.value.model_3d_enabled) &&
    ['none', 'failed'].includes(item.value.model_status || 'none'),
)

async function generateModel() {
  if (!item.value || modelSubmitting.value) return
  if (!userStore.isLoggedIn) {
    ElMessage.warning('请先登录后再生成 3D 模型')
    router.push({ path: '/login', query: { redirect: route.fullPath } })
    return
  }
  modelSubmitting.value = true
  try {
    await triggerModel(item.value.id)
    item.value.model_status = 'generating'
    item.value.model_url = null
    item.value.model_error = null
    ElMessage.success('3D 模型开始生成，约 2-4 分钟后可查看')
    modelPollCount = 0
    modelTimer = setTimeout(pollModel, 5000)
  } catch {
    // 错误文案由请求拦截器统一提示（开关关闭 / 无权 / 重复触发都会带 message）；
    // 本地状态保持不变，按钮可重试
  } finally {
    modelSubmitting.value = false
  }
}

async function pollModel() {
  const prevStatus = item.value?.model_status
  try {
    const data = await getModel(route.params.id)
    if (item.value) {
      item.value.model_status = data.model_status || 'none'
      // 签名 URL 每次读取都会刷新，不能缓存上一轮的地址
      item.value.model_url = data.model_url || null
      item.value.model_error = data.model_error || null
    }
    // 「生成中 → 失败」必须让用户看见：以前只是悄悄把状态改回 failed、按钮变回
    // 「重新生成」，没有任何提示，用户以为点了没反应。只在此转变时弹一次。
    if (prevStatus === 'generating' && item.value?.model_status === 'failed') {
      ElMessage.error({ message: modelFailText(item.value.model_error), duration: 6000 })
    }
  } catch {
    // 保持现有状态，不影响页面展示
  }
  if (item.value?.model_status === 'generating') {
    if (modelPollCount >= MODEL_MAX_POLLS) {
      // 到达上限：再同步一次真实状态，避免本地永久停在 generating（按钮再也回不来）
      try {
        const final = await getModel(route.params.id)
        if (item.value) {
          item.value.model_status = final.model_status || 'none'
          item.value.model_url = final.model_url || null
          item.value.model_error = final.model_error || null
        }
      } catch {
        // 同步失败就保持现状，刷新页面即可恢复
      }
      if (item.value?.model_status === 'generating') {
        ElMessage.info('3D 模型仍在生成中，稍后刷新页面即可查看')
      } else if (item.value?.model_status === 'failed') {
        ElMessage.error({ message: modelFailText(item.value.model_error), duration: 6000 })
      }
      return
    }
    modelPollCount += 1
    modelTimer = setTimeout(pollModel, 3000)
  }
}

async function onModelError() {
  // 与 360° 同样的已知场景：签名 URL 1 小时有效，页面久置后首次加载会 403/404。
  // 先重新拉详情刷新签名并重挂载一次；仍失败才降级为 360° / 静态图。
  if (item.value && modelRetryCount < 1) {
    modelRetryCount += 1
    try {
      const fresh = await getItem(route.params.id)
      if (fresh?.model_status === 'ready' && fresh.model_url) {
        item.value.model_url = fresh.model_url
        modelViewerKey.value += 1
        return
      }
    } catch {
      // 拉取失败走降级
    }
  }
  // 加载二次失败：标记 failed，模板自动回落到 360° 四视图（未就绪则静态图）
  if (item.value) {
    item.value.model_status = 'failed'
    item.value.model_url = null
  }
}

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

// 模式/成色：与 item.exchange_mode 列注释同口径（1=免费送 2=交换 3=低价转让 4=平台回收）
const MODE_TEXT = { 1: '免费送', 2: '交换', 3: '低价转让', 4: '平台回收' }
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
  modelPollCount = 0
  loadPanorama()
  // 3D 状态与 360° 互不依赖：并行查询（页面可能带着 generating 状态进来）
  pollModel()
  // 与详情/360° 互不依赖，并行查询收藏态
  loadFavoriteState()
})
</script>

<style scoped>
/* ---------- 顶部操作栏：左返回 / 右收藏 ---------- */
.detail-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 4px;
}

/* 收藏按钮：胶囊形。
   底色用 transparent（而非某个浅色令牌），这样在普通主题与高对比度主题下
   都不会出现「浅色块浮在纯黑底上」的割裂感，只需重映射文字/描边颜色。 */
.fav-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  min-height: 40px;
  padding: 0 16px;
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
  background: transparent;
  border: 1px solid var(--border-card);
  border-radius: 999px;
  cursor: pointer;
  transition: color 0.2s ease, border-color 0.2s ease;
}

.fav-btn svg {
  width: 20px;
  height: 20px;
}

.fav-btn:hover {
  color: var(--green-primary);
  border-color: var(--green-primary);
}

.fav-btn:focus-visible {
  outline: 3px solid var(--green-primary);
  outline-offset: 2px;
}

/* 已收藏：实心心形 + 玫红描边文字 */
.fav-btn.active {
  color: #e11d48;
  border-color: #e11d48;
}

.fav-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

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

/* 生成入口浮层：3D / 360° 两个按钮可能同时出现，用 flex 容器统一排布，
   避免各自绝对定位后互相压住 */
.generate-actions {
  position: absolute;
  left: 14px;
  /* 18px：比原先多 4px，给「失败原因」两行提示留出呼吸空间（overflow:hidden 会裁边） */
  bottom: 18px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  max-width: calc(100% - 28px);
}

/* 生成按钮：圆角胶囊，仅所有者可见（定位交给 .generate-actions） */
.pano-generate-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: 1px solid var(--green-primary);
  border-radius: 999px;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--green-primary);
  background: rgba(255, 255, 255, 0.92);
  cursor: pointer;
  transition: background 0.18s ease, color 0.18s ease, box-shadow 0.18s ease;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
}

.pano-generate-btn:hover:not(:disabled) {
  color: #fff;
  background: var(--green-primary);
  box-shadow: 0 4px 16px rgba(47, 133, 90, 0.28);
}

.pano-generate-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 3D 生成中浮层：右上角常驻，直到状态不再是 generating。
   指针事件关闭（pointer-events:none），避免挡住底下的 360° 拖拽操作。 */
.model-generating-tip {
  position: absolute;
  top: 14px;
  right: 14px;
  z-index: 3;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 7px 14px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  background: rgba(47, 133, 90, 0.94);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.16);
  pointer-events: none;
}

.tip-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: tip-spin 0.8s linear infinite;
}

@keyframes tip-spin {
  to {
    transform: rotate(360deg);
  }
}

/* 失败原因：换行独占一行贴在按钮下方，长文本两行截断（完整原文在 title 提示里） */
.model-fail-hint {
  flex-basis: 100%;
  margin: 2px 0 0;
  max-width: 100%;
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 12.5px;
  line-height: 1.5;
  color: #b42318;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid rgba(180, 35, 24, 0.28);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.visual .pano-viewer,
.visual .model-viewer {
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

/* ---------- 低价转让：醒目的转让价条 ---------- */
.price-banner {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
  padding: 14px 18px;
  margin: -12px 0 26px;
  background: linear-gradient(120deg, var(--teal-soft), var(--green-softer));
  border: 1px solid rgba(76, 175, 80, 0.28);
  border-radius: var(--r-md);
}

.price-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

.price-value {
  font-size: 30px;
  font-weight: 700;
  color: var(--teal-deep);
  line-height: 1.1;
}

.price-hint {
  font-size: 12.5px;
  color: var(--text-secondary);
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

/* ---------- 操作行：我要换 / 联系发布者 并排 ---------- */
.action-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.action-row .el-button {
  flex: 1 1 0;
  min-width: 0;
}

.swap-btn {
  box-shadow: var(--shadow-btn);
}

/* ---------- 我要换弹窗 ---------- */
.swap-dialog {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.swap-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--green-softer, #f1f9f3);
  border-radius: var(--r-md, 12px);
}

.swap-thumb {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 56px;
  height: 56px;
  overflow: hidden;
  font-size: 24px;
  background: #fff;
  border: 1px solid rgba(76, 175, 80, 0.3);
  border-radius: 10px;
}

.swap-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.swap-item-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 4px;
}

.swap-item-title {
  font-size: 15px;
  font-weight: 700;
  color: #1b3a26;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 280px;
}

.swap-item-sub {
  font-size: 12.5px;
}

.swap-tips {
  font-size: 12.5px;
  color: #63786d;
  text-align: center;
  line-height: 1.7;
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

/* ============================================================
   移动端（≤767px）
   详情页已经是 ≤700px 单列，这里只补三点：
   ① 3D/全景区高度按屏宽自适应（固定 280px 在 430px 宽屏上偏矮）；
   ② 操作按钮触控高度 44px；
   ③ 长描述行距放宽，手机上更易读。
   ============================================================ */
@media (max-width: 767px) {
  .detail {
    margin-top: 16px;
    gap: 22px;
  }

  .visual {
    height: clamp(260px, 70vw, 340px);
  }

  .action-row {
    gap: 10px;
  }

  .action-row .el-button {
    min-height: 44px;
  }

  .detail-topbar {
    margin-bottom: 10px;
  }
}
</style>

<!-- ============================================================
     收藏按钮：助老模式 / 高对比度适配
     必须非 scoped——需要命中 html 根级选择器（html.mode-elderly /
     html.theme-high-contrast），scoped 的 data 属性选择器命中不到根元素。
     ============================================================ -->
<style>
html.mode-elderly .detail-topbar .fav-btn {
  min-height: 60px;
  padding: 0 24px;
  font-size: 20px;
}

html.mode-elderly .detail-topbar .fav-btn svg {
  width: 26px;
  height: 26px;
}

/* 高对比度：黑底上用纯白描边文字，已收藏改为浅玫红保证可读 */
html.theme-high-contrast .detail-topbar .fav-btn {
  color: #ffffff;
  border-color: #ffffff;
}

html.theme-high-contrast .detail-topbar .fav-btn.active {
  color: #fca5a5;
  border-color: #fca5a5;
}

/* 助老模式：操作行按钮同样放大点击目标 */
html.mode-elderly .action-row .el-button {
  min-height: 60px;
  font-size: 20px;
}

/* 助老模式：360° 生成按钮放大点击目标 */
html.mode-elderly .pano-generate-btn {
  min-height: 56px;
  padding: 0 24px;
  font-size: 19px;
}

/* 助老模式：生成中提示与失败原因同步放大 */
html.mode-elderly .model-generating-tip {
  font-size: 17px;
  padding: 10px 18px;
}

html.mode-elderly .tip-spinner {
  width: 18px;
  height: 18px;
}

html.mode-elderly .model-fail-hint {
  font-size: 16px;
  line-height: 1.6;
  -webkit-line-clamp: 4;
}

/* 高对比度：浅色底 + 红色小字在纯黑主题下不成立，改为黑底白字白描边 */
html.theme-high-contrast .model-generating-tip {
  color: #000000;
  background: #ffffff;
  border: 1px solid #ffffff;
}

html.theme-high-contrast .tip-spinner {
  border-color: rgba(0, 0, 0, 0.35);
  border-top-color: #000000;
}

html.theme-high-contrast .model-fail-hint {
  color: #ffffff;
  background: #000000;
  border-color: #ffffff;
}

/* 高对比度：360° 生成按钮黑底白描边 */
html.theme-high-contrast .pano-generate-btn {
  color: #ffffff;
  background: #000000;
  border-color: #ffffff;
}

html.theme-high-contrast .pano-generate-btn:hover:not(:disabled) {
  color: #000000;
  background: #ffffff;
}
</style>
