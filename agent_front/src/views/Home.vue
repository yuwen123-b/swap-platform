<template>
  <div class="home-root">
    <!-- ============================================================
         一、全屏沉浸式 Hero
         底层：el-carousel 大图轮播（fade + Ken Burns）
         中层：深绿渐变遮罩
         顶层：左对齐文案 + CTA
         底部：缩略图导航
         ============================================================ -->
    <section class="hero">
      <el-carousel
        ref="carouselRef"
        height="100vh"
        :interval="7000"
        :pause-on-hover="true"
        arrow="never"
        indicator-position="none"
        @change="onChange"
      >
        <el-carousel-item v-for="slide in heroSlides" :key="slide.id">
          <!-- @error 兜底：底图不可达（Unsplash 国内常不可达）时隐藏破图，露出 .hero 品牌渐变 -->
          <img class="kb-img" :src="slide.image" :alt="themeText(slide.id)" draggable="false" @error="onHeroImgError" />
        </el-carousel-item>
      </el-carousel>

      <!-- 渐变遮罩：左深右透，保证文案可读；底部压暗托住缩略图 -->
      <div class="hero-mask"></div>

      <!-- 断网兜底：4 张底图全裂时显示纯 CSS 品牌底纹（绝不出现空白首屏） -->
      <div v-if="heroAllBroken" class="hero-fallback" aria-hidden="true">
        <div class="hero-fallback-inner">
          <span class="hero-fallback-mark">闲物焕新</span>
          <span class="hero-fallback-sub">让每件物品抵达下一段故事</span>
        </div>
      </div>

      <!-- 顶层文案 -->
      <div class="hero-content">
        <!-- 品牌标识层：品牌名放进首屏最大视觉权重处 + 随轮播切换的主题标签 -->
        <div class="hero-kicker">
          <span class="hero-eyebrow">闲物焕新 · 闲置物品循环平台</span>
          <span class="hero-theme" :key="activeIndex">{{ activeTheme }}</span>
        </div>
        <h1 class="hero-title">让闲置物品流动起来</h1>
        <p class="hero-sub">
          在邻里之间交换旧物，用一份信任连接彼此，让每一次分享都成为更轻盈、更温暖的生活选择。
        </p>
        <div class="hero-cta">
          <button class="cta cta-primary" type="button" @click="go('/items')">
            开始探索
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
          </button>
          <button class="cta cta-ghost" type="button" @click="go('/pricing')">让 AI 帮你估价</button>
        </div>
      </div>

      <!-- 底部缩略图导航 -->
      <div class="hero-thumbs">
        <button
          v-for="(slide, i) in heroSlides"
          :key="slide.id"
          type="button"
          class="thumb"
          :class="{ 'is-active': activeIndex === i }"
          :title="themeText(slide.id)"
          @click="goSlide(i)"
        >
          <img :src="slide.thumb" :alt="themeText(slide.id)" @error="onThumbImgError" />
        </button>
      </div>

      <!-- 滚动提示 -->
      <div class="scroll-hint" aria-hidden="true">
        <span class="mouse"><i></i></span>
      </div>
    </section>

    <!-- ============================================================
         二、Hero 下方衔接布局
         ============================================================ -->
    <div class="below">
      <!-- 1. AI 智能体悬浮玻璃卡 -->
      <section class="ai-bridge">
        <div class="ai-left">
          <span class="ai-emoji">🤖</span>
          <div>
            <div class="ai-title">AI 智能管家：一键识别与估价</div>
            <div class="ai-desc">拍一拍物品，AI 帮你识别信息、给出合理交换参考价</div>
          </div>
        </div>
        <div class="ai-actions">
          <el-button type="primary" @click="go('/pricing')">让 AI 帮你估价</el-button>
          <el-button plain @click="go('/recognition')">物品识别</el-button>
        </div>
      </section>

      <!-- 2. 低碳数据看板：UI 已下线（数据逻辑保留在 <script setup> 中，见 TODO 注释） -->

      <!-- 3. 物品分类快捷入口 -->
      <section class="cate-section">
        <div class="section-head">
          <span class="sec-eyebrow">快捷入口</span>
          <h2 class="sec-title">按分类，发现邻居的好物</h2>
        </div>
        <div class="cate-grid">
          <button
            v-for="c in categories"
            :key="c.id"
            type="button"
            class="cate-card"
            @click="go(`/items?category_id=${c.id}`)"
          >
            <span class="cate-icon">{{ c.icon }}</span>
            <span class="cate-name">{{ c.name }}</span>
          </button>
        </div>
      </section>

      <!-- 4. 闲置物品展示区（数据：src/mock/items.js） -->
      <section class="items-section">
        <div class="section-head items-head">
          <div>
            <span class="sec-eyebrow">社区流动中</span>
            <h2 class="sec-title">邻居们上传的温暖物品</h2>
          </div>
          <el-radio-group v-model="activeFilter" size="default" @change="onFilterChange">
            <el-radio-button
              v-for="f in itemFilters"
              :key="f.key"
              :value="f.key"
            >{{ f.label }}</el-radio-button>
          </el-radio-group>
        </div>

        <div v-loading="itemsLoading">
          <el-row v-if="items.length">
            <el-col
              v-for="item in items"
              :key="item.id"
              :xs="12"
              :sm="12"
              :md="8"
              :lg="6"
            >
              <article class="item-card" @click="go(`/items/${item.id}`)">
                <div class="item-img">
                  <img
                    :src="item.image"
                    :alt="item.title"
                    loading="lazy"
                    @error="onImgError"
                  />
                  <span class="tag-condition">{{ conditionText(item.conditionLevel) }}</span>
                  <span v-if="item.panoramaStatus === 'ready'" class="badge-360">360°</span>
                </div>
                <div class="item-body">
                  <h3 class="item-name">{{ item.title }}</h3>
                  <div class="item-tags">
                    <span class="tag-mode" :class="modeClass(item.modeCode)">
                      {{ modeText(item.modeCode) }}
                    </span>
                  </div>
                  <div class="item-meta">
                    <span class="meta">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 12-9 12s-9-5-9-12a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                      {{ item.distanceKm == null ? '本社区' : `距你 ${item.distanceKm}km` }}
                    </span>
                    <span class="meta carbon">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10z"/><path d="M2 21c0-3 1.85-5.36 5.08-6"/></svg>
                      减碳 {{ item.carbon }}kg
                    </span>
                  </div>
                </div>
              </article>
            </el-col>
          </el-row>

          <!-- 绿色空状态 -->
          <div v-else-if="!itemsLoading && !itemsError" class="green-empty">
            <span class="green-empty-icon">🌱</span>
            <p class="green-empty-text">还没有邻居上传物品哦～</p>
          </div>

          <!-- 接口错误：仅提示，不崩溃 -->
          <el-alert
            v-if="itemsError && !itemsLoading"
            class="items-tip"
            title="物品暂时加载失败，请稍后再试"
            type="warning"
            show-icon
            :closable="false"
          />
        </div>
      </section>

      <!-- 5. 公开需求墙：邻居们正在寻找的物品（只展示进行中，隐藏手机号） -->
      <section v-if="demandWall.length" class="demand-section">
        <div class="section-head demand-head">
          <div>
            <span class="sec-eyebrow">邻里互助</span>
            <h2 class="sec-title">邻居们正在找这些</h2>
          </div>
          <button type="button" class="demand-more" @click="go('/demands')">查看全部需求</button>
        </div>
        <div class="demand-grid">
          <button
            v-for="d in demandWall"
            :key="d.id"
            type="button"
            class="demand-card"
            @click="contactDemandOwner(d)"
          >
            <span class="demand-title">{{ d.title || '未命名需求' }}</span>
            <span class="demand-meta">
              <span v-if="d.category" class="demand-tag">{{ d.category }}</span>
              <span class="demand-who">
                {{ d.nickname || '社区邻居' }}<template v-if="d.building"> · {{ d.building }}</template>
              </span>
            </span>
          </button>
        </div>
      </section>

      <!-- 6. 邻里互换故事 -->
      <section class="story-section">
        <div class="section-head">
          <span class="sec-eyebrow">社区温情</span>
          <h2 class="sec-title">温暖的置换故事</h2>
        </div>
        <el-row :gutter="18">
          <el-col v-for="story in swapStories" :key="story.id" :xs="24" :sm="24" :md="8">
            <article class="story-card">
              <div class="story-top">
                <span class="story-avatar">{{ story.name.charAt(0) }}</span>
                <span class="story-name">{{ story.name }}</span>
              </div>
              <p class="story-text">“{{ story.text }}”</p>
            </article>
          </el-col>
        </el-row>
      </section>
    </div>

    <!-- 6. 底部 Footer -->
    <footer class="home-footer">
      <nav class="footer-links">
        <RouterLink to="/about">关于我们</RouterLink>
        <RouterLink to="/convention">社区公约</RouterLink>
        <RouterLink to="/help">帮助中心</RouterLink>
        <RouterLink to="/contact">联系客服</RouterLink>
      </nav>
      <div class="footer-divider"></div>
      <p class="footer-copy">© 2026 社区旧物互换智能体平台 版权所有</p>
    </footer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  categories as rawCategories,
  heroSlides,
  lowCarbonStats,
  swapStories as rawSwapStories,
} from '../mock/home'
import { mockItems as rawMockItems } from '../mock/items'
import { getItems } from '../api/item'
import { getDemandWall } from '../api/demand'
import { useUserStore } from '../store/user'

const router = useRouter()
const go = (path) => router.push(path)
const userStore = useUserStore()

/* ---------- mock 数据按 id 映射文案 ---------- */
const THEME_TEXT = { 1: '绿色社区', 2: '旧物改造', 3: '二手书籍', 4: '邻里交换' }
function themeText(id) {
  return THEME_TEXT[id] || '绿色社区'
}

const CATEGORY_TEXT = {
  22: '家电', 23: '母婴', 9: '图书', 12: '家具',
  21: '数码', 13: '服饰', 14: '运动', 24: '其他',
}
const categories = computed(() =>
  rawCategories.map((c) => ({ ...c, name: CATEGORY_TEXT[c.id] || '其他' })),
)

const STORY_NAME = { 1: '林阿姨', 2: '阿杰', 3: '小满妈妈' }
const STORY_TEXT = {
  1: '把孙子小时候的绘本送给了楼下新搬来的年轻妈妈，她回赠我一盆绿萝。书有人读，花有人养，这就是邻里最好的样子。',
  2: '用闲置的咖啡机换到了同小区的公路车头盔，线上约好周末广场交接，比二手平台省心多了，还多认识了一个骑友。',
  3: '宝宝长得快，婴儿车、摇椅几乎没用几次。在社区里一件件流转出去，每次交接都觉得这些东西在替我们继续陪伴新的家庭。',
}
const swapStories = computed(() =>
  rawSwapStories.map((s) => ({
    ...s,
    name: STORY_NAME[s.id] || '',
    text: STORY_TEXT[s.id] || '',
  })),
)

/* ---------- Hero 轮播与缩略图联动 ---------- */
const carouselRef = ref()
const activeIndex = ref(0)

function onChange(index) {
  activeIndex.value = index
}

function goSlide(index) {
  // el-carousel 对外暴露的方法为 setActiveItem
  carouselRef.value?.setActiveItem(index)
}

/* 当前屏主题词：随轮播切换显示在标题上方（原先只藏在 alt/title 里，页面上看不到） */
const activeTheme = computed(() => heroSlides[activeIndex.value]?.theme || '绿色社区')

/* ---------- Hero 底图兜底 ----------
   Unsplash 在国内网络经常不可达，而 Hero 原先没有 @error 处理：
   4 张图全裂时首屏会只剩一块深绿空背景 + 白字。
   这里分两级兜底：
     ① 单张裂掉 → 隐藏该 <img>，露出 .hero 的品牌渐变（不显示浏览器破图图标）；
     ② 全部裂掉 → 额外浮出 .hero-fallback 品牌底纹层（大号品牌字 + 标语），
        让完全断网时首屏仍是一个「完整的品牌开屏」，而不是空白块。 */
const heroBrokenCount = ref(0)
const heroAllBroken = computed(() => heroSlides.length > 0 && heroBrokenCount.value >= heroSlides.length)

function onHeroImgError(event) {
  if (event?.target) event.target.style.display = 'none'
  heroBrokenCount.value += 1
}

/* 缩略图裂掉只隐藏自身（缩略图不参与「全裂兜底」计数，避免重复计算） */
function onThumbImgError(event) {
  if (event?.target) event.target.style.display = 'none'
}

/* ---------- 邻居上传物品：从后端真实接口获取 ---------- */
// 绿色默认占位图（内联 SVG，无需额外文件）
const FALLBACK_IMAGE =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='600' height='420'%3E%3Crect width='100%25' height='100%25' fill='%23E8F5E9'/%3E%3Cg fill='none' stroke='%234CAF50' stroke-width='6' stroke-linecap='round'%3E%3Cpath d='M300 250c-20-52-62-76-102-72-40 4-64 34-62 70 2 34 28 56 64 56h98c34 0 60-22 62-54 2-34-20-62-58-66-38-4-78 18-96 66'/%3E%3C/g%3E%3C/svg%3E"

const itemFilters = computed(() => [
  { key: 'latest', label: '最新发布' },
  { key: 'nearest', label: '离我最近' },
  { key: 'carbon', label: '碳减排最多' },
])
const activeFilter = ref('latest')

// 前端筛选 key -> 后端 sort_by 参数
const SORT_PARAM = {
  latest: 'created_at',
  nearest: 'distance',
  carbon: 'carbon_value',
}

const items = ref([])
const itemsLoading = ref(false)
const itemsError = ref(false)

const MODE_TEXT = { 1: '免费送出', 2: '物物交换', 3: '积分兑换' }
function modeText(code) {
  return MODE_TEXT[code] || '物物交换'
}
const CONDITION_TEXT = { 1: '成色一般', 2: '七成新', 3: '八成新', 4: '九成新', 5: '几乎全新' }
function conditionText(level) {
  return CONDITION_TEXT[level] || '状态良好'
}

function parseDistanceValue(distance) {
  const match = String(distance || '').match(/\d+(?:\.\d+)?/)
  return match ? Number(match[0]) : Number.MAX_SAFE_INTEGER
}

function normalizeFallbackItem(item) {
  const modeKey = String(item.exchange_mode || '')
  const modeCode =
    modeKey.includes('赠送') || modeKey.includes('免费送出') ? 1 :
    modeKey.includes('交换') || modeKey.includes('物物交换') ? 2 :
    modeKey.includes('积分') ? 3 :
    2

  const conditionTextValue = String(item.condition || '')
  const conditionLevel =
    conditionTextValue.includes('全新') ? 5 :
    conditionTextValue.includes('九成新') ? 4 :
    conditionTextValue.includes('八成新') ? 3 :
    conditionTextValue.includes('七成新') ? 2 :
    1

  return {
    id: item.id,
    title: item.title,
    image: item.image || FALLBACK_IMAGE,
    conditionLevel,
    modeCode,
    carbon: Number(item.carbon || 0),
    panoramaStatus: item.panorama_status || 'ready',
    distance: parseDistanceValue(item.distance),
  }
}

function getFallbackItems(sortKey = 'latest') {
  const list = rawMockItems.map(normalizeFallbackItem)
  if (sortKey === 'carbon') return [...list].sort((a, b) => Number(b.carbon) - Number(a.carbon))
  if (sortKey === 'nearest') return [...list].sort((a, b) => a.distance - b.distance)
  return list
}

// images 可能是 JSON 字符串，也可能已被驱动解析成数组
function firstImage(item) {
  const raw = item.images
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) && parsed.length ? parsed[0] : ''
    } catch {
      return ''
    }
  }
  return Array.isArray(raw) && raw.length ? raw[0] : ''
}

function normalize(item) {
  return {
    id: item.id,
    title: item.title,
    image: firstImage(item) || FALLBACK_IMAGE,
    conditionLevel: item.condition_level,
    modeCode: item.exchange_mode,
    carbon: Number(item.carbon_value || 0),
    panoramaStatus: item.panorama_status,
    // 距离排序时后端才会返回 distance_km（未公开位置 / 无坐标的物品为 undefined）
    distanceKm: item.distance_km ?? null,
  }
}

/* 「离我最近」依赖用户位置：未设置时给出可操作的引导，而不是静默回滚筛选值 */
function guideToSetLocation() {
  const loggedIn = userStore.isLoggedIn
  ElMessageBox.confirm(
    loggedIn
      ? '设置位置后即可查看离你最近的物品。'
      : '登录并设置位置后即可查看离你最近的物品。',
    loggedIn ? '尚未设置位置' : '尚未登录',
    {
      confirmButtonText: loggedIn ? '去设置位置' : '去登录',
      cancelButtonText: '稍后再说',
      type: 'warning',
    },
  )
    .then(() => go(loggedIn ? '/profile/location' : '/login?redirect=/'))
    .catch(() => {})
}

async function loadItems(isRetry = false) {
  itemsLoading.value = true
  itemsError.value = false
  const requestedFilter = activeFilter.value
  const isNearest = requestedFilter === 'nearest'
  try {
    const data = await getItems(
      {
        page: 1,
        size: 8,
        sort_by: SORT_PARAM[requestedFilter],
      },
      // 后端离线时走本地 mock，静默降级，不弹红色错误 toast
      { skipErrorToast: true },
    )
    // 已登录但未设置位置：后端返回 need_location，明确引导并回退到「最新发布」
    if (isNearest && data?.need_location) {
      activeFilter.value = 'latest'
      if (!isRetry) await loadItems(true)
      guideToSetLocation()
      return
    }
    if (isNearest && data?.distance_sorted && !(data.nearby_count > 0)) {
      // 排序已生效，只是当前没有已公开位置的物品——明确告知，避免又被当成「点了没反应」
      ElMessage.info('附近暂无已公开位置的物品，已按默认顺序展示')
    }
    items.value = (data.items || []).map(normalize)
  } catch (error) {
    // 注意：FastAI 返回 {"detail": "..."}，需同时检查 message 和 detail
    const serverMsg = error?.response?.data?.message || error?.response?.data?.detail || error?.message || ''
    if (isNearest) {
      // 未登录（后端 400）或距离排序不可用：回退筛选并重新加载最新数据
      activeFilter.value = 'latest'
      if (!isRetry) await loadItems(true)
      if (serverMsg.includes('位置')) {
        // 需要用户去设置位置：给可操作的入口（不重复弹 toast）
        guideToSetLocation()
      } else {
        ElMessage.warning(serverMsg || '距离排序暂时不可用，已切换回最新发布')
      }
      return
    }
    items.value = getFallbackItems(requestedFilter)
    itemsError.value = false
  } finally {
    itemsLoading.value = false
  }
}

function onFilterChange() {
  loadItems()
}

function modeClass(code) {
  if (code === 3) return 'mode-points'
  if (code === 1) return 'mode-free'
  return 'mode-swap'
}

/* ---------- 公开需求墙（只展示进行中，后端已排除自己的需求） ---------- */
const demandWall = ref([])

async function loadDemands() {
  try {
    // 失败静默隐藏该区：首页不因需求墙不可用而出现错误提示或空白块
    const data = await getDemandWall({ limit: 6 }, { skipErrorToast: true })
    demandWall.value = data?.list || []
  } catch {
    demandWall.value = []
  }
}

// 点击一条需求 -> 打开与发布者的私信（Message.vue 支持 ?otherUserId= 直达会话）
function contactDemandOwner(demand) {
  if (!userStore.isLoggedIn) {
    ElMessageBox.confirm('登录后即可直接私信邻居，聊聊你们的需求。', '尚未登录', {
      confirmButtonText: '去登录',
      cancelButtonText: '稍后再说',
      type: 'info',
    })
      .then(() => go('/login?redirect=/'))
      .catch(() => {})
    return
  }
  // 后端已排除自己的需求，这里是防御性判断
  if (userStore.user?.id && demand.user_id === userStore.user.id) {
    ElMessage.info('这是你自己发布的需求')
    return
  }
  go(`/messages?otherUserId=${demand.user_id}`)
}

/* 图片加载失败：仅回填一次默认绿色占位图，避免死循环 */
function onImgError(event) {
  const img = event.target
  if (img.dataset.fb) return
  img.dataset.fb = '1'
  img.src = FALLBACK_IMAGE
}

onMounted(() => {
  loadItems()
  loadDemands()
})

/* ---------- 低碳数据（数据看板 UI 已下线，逻辑保留） ---------- */
// TODO: 后续接入低碳数据接口
// 当前数据来自 src/mock/home.js 的 lowCarbonStats；接入真实接口时替换为 await getLowCarbonStats()。
// 恢复看板 UI 步骤：1) 把 stats-board 的 <section> 加回模板（v-for 遍历 shownStats）；
// 2) 在 onMounted 中用 IntersectionObserver 监听该 section，进入视口时调用 runCountUp()。
const shownStats = reactive(
  lowCarbonStats.map((s) => ({ ...s, shown: 0 })),
)

// 数字增长动效（恢复 UI 后直接复用，无需重写）
function runCountUp() {
  const duration = 1600
  const start = performance.now()
  const easeOut = (t) => 1 - Math.pow(1 - t, 3)

  function tick(now) {
    const progress = Math.min((now - start) / duration, 1)
    const eased = easeOut(progress)
    shownStats.forEach((s) => {
      s.shown = Math.round(s.value * eased)
    })
    if (progress < 1) requestAnimationFrame(tick)
  }
  requestAnimationFrame(tick)
}
</script>

<style scoped>
.home-root {
  /* 用户指定配色 */
  --c-main: #4caf50;
  --c-deep: #2e7d32;
  --c-light: #81c784;
  --c-mint: #a5d6a7;
  --c-bg: #f4fbf6;
}

/* ================= Hero ================= */
.hero {
  position: relative;
  height: 100vh;
  /* 突破 main 的限宽容器，全屏铺满 */
  width: 100vw;
  margin-left: calc(50% - 50vw);
  overflow: hidden;
  /* 兜底底色：底图不可达时展示品牌渐变 —— 既不是空白，也不是一块死绿 */
  background:
    radial-gradient(120% 90% at 12% 16%, rgba(76, 175, 80, 0.52) 0%, rgba(46, 125, 50, 0) 62%),
    radial-gradient(110% 84% at 88% 84%, rgba(15, 118, 110, 0.48) 0%, rgba(15, 118, 110, 0) 64%),
    linear-gradient(135deg, #1f5c33 0%, var(--c-deep) 46%, #14524f 100%);
}

/* el-carousel 淡入淡出覆写（替换默认横向滑动） */
.hero :deep(.el-carousel),
.hero :deep(.el-carousel__container) {
  height: 100vh !important;
}

.hero :deep(.el-carousel__item) {
  transform: none !important;
  opacity: 0;
  transition: opacity 1.1s ease !important;
}

.hero :deep(.el-carousel__item.is-active) {
  opacity: 1;
  z-index: 2;
}

/* Ken Burns 缓慢缩放：仅当前帧播放 */
.kb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.hero :deep(.el-carousel__item.is-active) .kb-img {
  animation: slowZoom 12s ease-in-out infinite alternate;
}

@keyframes slowZoom {
  from {
    transform: scale(1);
  }
  to {
    transform: scale(1.12);
  }
}

/* 渐变遮罩 */
.hero-mask {
  position: absolute;
  inset: 0;
  z-index: 3;
  background:
    linear-gradient(
      100deg,
      rgba(18, 58, 30, 0.86) 0%,
      rgba(18, 58, 30, 0.58) 36%,
      rgba(18, 58, 30, 0.14) 68%,
      rgba(18, 58, 30, 0) 100%
    ),
    linear-gradient(0deg, rgba(12, 38, 20, 0.62) 0%, rgba(12, 38, 20, 0) 26%);
  pointer-events: none;
}

/* 顶层文案 */
.hero-content {
  position: absolute;
  z-index: 5;
  top: 0;
  bottom: 0;
  left: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  max-width: 780px;
  padding: 0 8vw;
}

/* 断网兜底层：位于底图之上、遮罩之下（z-index:2 < mask 3 < content 5）。
   仅当 4 张底图全部加载失败时渲染，用大号品牌字把空首屏兜成「品牌开屏」。 */
.hero-fallback {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: grid;
  place-items: center;
  pointer-events: none;
}

.hero-fallback-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  /* 轻微右移，避免与左侧文案重叠 */
  transform: translateX(14vw);
}

.hero-fallback-mark {
  color: rgba(255, 255, 255, 0.15);
  font-size: clamp(64px, 11vw, 170px);
  font-weight: 800;
  letter-spacing: 12px;
  line-height: 1;
  white-space: nowrap;
}

.hero-fallback-sub {
  color: rgba(200, 230, 201, 0.34);
  font-size: clamp(13px, 1.3vw, 19px);
  letter-spacing: 6px;
}

/* 品牌标识层：品牌名 + 随轮播切换的主题标签 */
.hero-kicker {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.hero-kicker .hero-eyebrow {
  align-self: center;
}

.hero-theme {
  padding: 7px 16px;
  border: 1px solid rgba(255, 255, 255, 0.34);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.16);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 2px;
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  /* 每次切屏重新挂载（:key="activeIndex"）触发一次淡入 */
  animation: themeIn 0.5s ease both;
}

@keyframes themeIn {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

.hero-eyebrow {
  align-self: flex-start;
  padding: 7px 16px;
  border: 1px solid rgba(165, 214, 167, 0.55);
  border-radius: 999px;
  background: rgba(76, 175, 80, 0.16);
  color: var(--c-mint);
  font-size: 13px;
  /* 文案已改为品牌全称（比原来的「社区 · 循环 · 智能」长），字距收到 2px */
  letter-spacing: 2px;
}

.hero-title {
  margin: 24px 0 18px;
  color: #fff;
  font-size: clamp(40px, 5.8vw, 74px);
  font-weight: 800;
  line-height: 1.12;
  letter-spacing: 2px;
  text-shadow: 0 0 34px rgba(129, 199, 132, 0.55), 0 4px 24px rgba(0, 0, 0, 0.35);
}

.hero-sub {
  margin: 0;
  max-width: 560px;
  color: #e8f5e9;
  font-size: clamp(15px, 1.3vw, 18px);
  line-height: 1.9;
  letter-spacing: 0.5px;
}

.hero-cta {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-top: 38px;
}

.cta {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 52px;
  padding: 0 30px;
  border-radius: 999px;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 1px;
  cursor: pointer;
  transition: transform 0.25s, box-shadow 0.25s, background 0.25s;
}

.cta svg {
  width: 18px;
  height: 18px;
  transition: transform 0.25s;
}

.cta-primary {
  border: none;
  background: linear-gradient(135deg, var(--c-main), var(--c-deep));
  color: #fff;
  box-shadow: 0 10px 26px rgba(46, 125, 50, 0.45);
}

.cta-primary:hover {
  transform: translateY(-3px);
  box-shadow: 0 14px 32px rgba(46, 125, 50, 0.55);
}

.cta-primary:hover svg {
  transform: translateX(4px);
}

.cta-ghost {
  border: 1.5px solid rgba(255, 255, 255, 0.7);
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
  backdrop-filter: blur(6px);
}

.cta-ghost:hover {
  background: rgba(255, 255, 255, 0.22);
  transform: translateY(-3px);
}

/* 缩略图导航 */
.hero-thumbs {
  position: absolute;
  z-index: 6;
  bottom: 34px;
  left: 50%;
  display: flex;
  gap: 14px;
  transform: translateX(-50%);
}

.thumb {
  width: 82px;
  height: 58px;
  padding: 0;
  border: 2px solid transparent;
  border-radius: 10px;
  overflow: hidden;
  opacity: 0.6;
  cursor: pointer;
  /* 缩略图裂掉（隐藏 <img>）时露出品牌渐变，不留透明空洞 */
  background: linear-gradient(135deg, var(--c-main), var(--c-deep));
  transition: transform 0.3s, opacity 0.3s, border-color 0.3s, box-shadow 0.3s;
}

.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb:hover {
  opacity: 0.9;
}

.thumb.is-active {
  border-color: #fff;
  opacity: 1;
  transform: scale(1.14);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.4);
}

/* 滚动提示 */
.scroll-hint {
  position: absolute;
  z-index: 6;
  right: 8vw;
  bottom: 38px;
}

.mouse {
  display: block;
  width: 22px;
  height: 36px;
  border: 2px solid rgba(255, 255, 255, 0.6);
  border-radius: 12px;
}

.mouse i {
  display: block;
  width: 3px;
  height: 8px;
  margin: 6px auto 0;
  border-radius: 3px;
  background: #fff;
  animation: wheelDown 1.6s infinite;
}

@keyframes wheelDown {
  0% {
    opacity: 0;
    transform: translateY(0);
  }
  40% {
    opacity: 1;
  }
  100% {
    opacity: 0;
    transform: translateY(10px);
  }
}

/* ================= 下方衔接 ================= */
.below {
  background: var(--c-bg);
  padding-bottom: 20px;
}

/* AI 悬浮玻璃卡 */
.ai-bridge {
  position: relative;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  max-width: 1060px;
  margin: -48px auto 0;
  padding: 22px 28px;
  border: 1px solid rgba(76, 175, 80, 0.35);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  box-shadow: 0 18px 44px rgba(46, 125, 50, 0.18);
}

.ai-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.ai-emoji {
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  border-radius: 16px;
  background: var(--green-soft, #e8f5e9);
  font-size: 26px;
}

.ai-title {
  color: var(--text-primary, #1b3a26);
  font-size: 17px;
  font-weight: 700;
}

.ai-desc {
  margin-top: 4px;
  color: var(--text-secondary, #63786d);
  font-size: 13px;
}

.ai-actions {
  display: flex;
  gap: 12px;
  flex-shrink: 0;
}

/* 低碳数据看板样式：随 UI 一并下线，恢复看板时从 git 历史取回 */

/* 通用 Section 头部 */
.cate-section,
.items-section,
.demand-section,
.story-section {
  max-width: 1060px;
  margin: 64px auto 0;
}

.section-head {
  margin-bottom: 24px;
}

.sec-eyebrow {
  display: block;
  color: var(--c-main);
  font-size: 12px;
  letter-spacing: 3px;
  font-weight: 600;
}

.sec-title {
  margin-top: 8px;
  color: var(--c-deep);
  font-size: clamp(22px, 2.2vw, 28px);
  font-weight: 700;
}

/* 分类入口 */
.cate-grid {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 14px;
}

.cate-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 20px 8px;
  border: 1px solid rgba(76, 175, 80, 0.2);
  border-radius: 16px;
  background: #fff;
  cursor: pointer;
  transition: transform 0.25s, box-shadow 0.25s, border-color 0.25s;
}

.cate-card:hover {
  border-color: var(--c-main);
  transform: translateY(-5px);
  box-shadow: 0 12px 26px rgba(46, 125, 50, 0.14);
}

.cate-icon {
  display: grid;
  place-items: center;
  width: 48px;
  height: 48px;
  border-radius: 14px;
  background: var(--c-bg);
  font-size: 24px;
}

.cate-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #1b3a26);
}

/* 物品展示：头部布局 + 筛选按钮 */
.items-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.items-section :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: var(--c-main);
  border-color: var(--c-main);
  box-shadow: -1px 0 0 0 var(--c-main);
}

/* 物品卡片：白底 / 16px 圆角 / 浅绿边框 / 悬浮上浮 */
.item-card {
  margin-bottom: 18px;
  border: 1px solid rgba(76, 175, 80, 0.22);
  border-radius: 16px;
  background: #fff;
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.28s ease, box-shadow 0.28s ease, border-color 0.28s ease;
}

.item-card:hover {
  border-color: var(--c-main);
  transform: translateY(-6px);
  box-shadow: 0 16px 34px rgba(46, 125, 50, 0.16);
}

.item-img {
  position: relative;
  height: 168px;
  overflow: hidden;
  background: var(--c-bg);
}

.item-img img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.5s ease;
}

.item-card:hover .item-img img {
  transform: scale(1.06);
}

.tag-condition {
  position: absolute;
  top: 10px;
  left: 10px;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.92);
  color: var(--c-deep);
  font-size: 12px;
  font-weight: 600;
}

.badge-360 {
  position: absolute;
  bottom: 10px;
  right: 10px;
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  background: rgba(47, 133, 90, 0.75);
}

.item-body {
  padding: 14px 16px 16px;
}

.item-name {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary, #1b3a26);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-tags {
  margin: 10px 0 12px;
}

.tag-mode {
  display: inline-flex;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
}

.mode-swap {
  background: #e8f5e9;
  color: var(--c-deep);
}

.mode-points {
  background: #fff8e1;
  color: #b7791f;
}

.mode-free {
  background: #e0f2f1;
  color: #00695c;
}

.item-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.meta {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--text-secondary, #63786d);
  font-size: 12.5px;
}

.meta svg {
  width: 14px;
  height: 14px;
}

.meta.carbon {
  color: var(--c-main);
}

/* 绿色空状态 */
.green-empty {
  padding: 66px 20px;
  text-align: center;
  background: #fff;
  border: 1px dashed rgba(76, 175, 80, 0.4);
  border-radius: 16px;
}

.green-empty-icon {
  font-size: 42px;
}

.green-empty-text {
  margin: 12px 0 0;
  color: var(--c-deep);
  font-size: 15px;
  font-weight: 600;
}

.items-tip {
  margin-top: 18px;
}

/* ================= 公开需求墙 ================= */
.demand-section {
  /* 局部令牌：高对比度主题下由文件末尾的非 scoped 块改写 */
  --dw-card: #ffffff;
  --dw-border: rgba(76, 175, 80, 0.22);
  --dw-text: var(--text-primary, #1b3a26);
  --dw-sub: var(--text-secondary, #63786d);
}

.demand-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

/* 「查看全部需求」：描边胶囊按钮，与首页既有 CTA 风格一致 */
.demand-more {
  flex-shrink: 0;
  min-height: 38px;
  padding: 8px 20px;
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  color: var(--dw-text);
  background: transparent;
  border: 1px solid var(--dw-border);
  border-radius: 999px;
  cursor: pointer;
  transition: color 0.2s ease, border-color 0.2s ease, background 0.2s ease;
}

.demand-more:hover {
  color: var(--c-deep);
  border-color: var(--c-main);
  background: rgba(76, 175, 80, 0.08);
}

.demand-more:focus-visible {
  outline: 3px solid var(--c-main);
  outline-offset: 2px;
}

.demand-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-top: 20px;
}

.demand-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 20px;
  text-align: left;
  font: inherit;
  background: var(--dw-card);
  border: 1px solid var(--dw-border);
  border-radius: 16px;
  cursor: pointer;
  transition: transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease;
}

.demand-card:hover {
  border-color: var(--c-main);
  transform: translateY(-5px);
  box-shadow: 0 12px 26px rgba(46, 125, 50, 0.14);
}

.demand-card:focus-visible {
  outline: 3px solid var(--c-main);
  outline-offset: 2px;
}

.demand-title {
  font-size: 16px;
  font-weight: 700;
  line-height: 1.6;
  color: var(--dw-text);
}

.demand-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.demand-tag {
  padding: 3px 10px;
  font-size: 12px;
  font-weight: 600;
  color: var(--c-deep);
  background: #e8f5e9;
  border-radius: 999px;
}

.demand-who {
  font-size: 13px;
  color: var(--dw-sub);
}

/* 邻里故事 */
.story-card {
  height: calc(100% - 18px);
  padding: 26px 24px;
  border: 1px solid rgba(76, 175, 80, 0.2);
  border-radius: 18px;
  background: linear-gradient(160deg, #ffffff 0%, #f1f9f3 100%);
  box-shadow: 0 6px 20px rgba(46, 125, 50, 0.07);
}

.story-top {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.story-avatar {
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--c-main), var(--c-deep));
  color: #fff;
  font-size: 18px;
  font-weight: 700;
  box-shadow: 0 4px 10px rgba(46, 125, 50, 0.3);
}

.story-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--c-deep);
}

.story-text {
  margin: 0;
  color: var(--text-secondary, #516b59);
  font-size: 14px;
  line-height: 1.9;
}

/* ================= Footer ================= */
.home-footer {
  background: linear-gradient(160deg, var(--c-deep), #1b5e20);
  padding: 46px 8vw 34px;
  text-align: center;
  /* 与 Hero 一致，全屏铺满 */
  width: 100vw;
  margin-left: calc(50% - 50vw);
}

.footer-links {
  display: flex;
  justify-content: center;
  gap: 38px;
  flex-wrap: wrap;
}

.footer-links a {
  color: rgba(255, 255, 255, 0.88);
  font-size: 14px;
  text-decoration: none;
  transition: color 0.2s;
}

.footer-links a:hover {
  color: #81c784;
  text-decoration: underline;
}

.footer-divider {
  width: 220px;
  height: 1px;
  margin: 26px auto 18px;
  background: rgba(255, 255, 255, 0.25);
}

.footer-copy {
  margin: 0;
  color: rgba(255, 255, 255, 0.7);
  font-size: 13px;
}

/* ================= 响应式 ================= */
@media (max-width: 900px) {
  .cate-grid {
    grid-template-columns: repeat(4, 1fr);
  }

  .demand-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .ai-bridge {
    flex-direction: column;
    align-items: stretch;
    text-align: left;
  }

  .ai-actions {
    justify-content: flex-end;
  }
}

@media (max-width: 560px) {
  .hero-content {
    padding: 0 7vw;
  }

  .hero-cta {
    flex-direction: column;
    align-items: stretch;
  }

  .cta {
    justify-content: center;
  }

  .hero-thumbs {
    gap: 8px;
    bottom: 26px;
  }

  .thumb {
    width: 58px;
    height: 42px;
  }

  .scroll-hint {
    display: none;
  }

  .cate-grid {
    grid-template-columns: repeat(3, 1fr);
  }

  .demand-grid {
    grid-template-columns: 1fr;
  }
}

/* ============================================================
   手机端（≤767px）：AI 智能管家卡片竖向友好布局
   ------------------------------------------------------------
   实测 375px 下的问题（CDP 盒模型取证）：
   ① .ai-emoji 被 .ai-left 的 flex 压扁成 39×52（应为 52×52）；
   ② 900px 断点的 .ai-actions{justify-content:flex-end} 让两个
      按钮右对齐，左侧留出一截突兀的空白；
   ③ 28px 左右内边距在手机上偏大。
   本块源码顺序在 900/560 断点之后，同优先级下后者生效，
   可直接覆盖上面两条，无需改动它们。
   ============================================================ */
@media (max-width: 767px) {
  .ai-bridge {
    margin-top: -40px;
    padding: 18px 16px;
    border-radius: 18px;
  }

  /* 修①：emoji 底座禁止被压缩 */
  .ai-emoji {
    flex-shrink: 0;
  }

  .ai-left {
    gap: 12px;
  }

  .ai-title {
    font-size: 16px;
    line-height: 1.35;
  }

  .ai-desc {
    margin-top: 3px;
    font-size: 12.5px;
    line-height: 1.55;
  }

  /* 修②：两个按钮等宽并排、占满整行（替代右对齐） */
  .ai-actions {
    justify-content: stretch;
    gap: 10px;
  }

  .ai-actions .el-button {
    flex: 1 1 0;
    /* 关键：flex 的默认 min-width 是 min-content，"让 AI 帮你估价"更长时
       会撑住不肯缩，两个按钮就不等宽了。配合收紧的 padding 与 14px 字号，
       min-content 才小于 1/2 行宽，flex 才能真正均分。 */
    min-width: 0;
    min-height: 44px;
    padding: 0 6px;
    font-size: 14px;
    white-space: nowrap;
    /* Element Plus 相邻按钮默认 margin-left:12px，flex 布局下用 gap 已足够 */
    margin-left: 0;
  }

  .ai-actions .el-button + .el-button {
    margin-left: 0;
  }
}
</style>

<!-- ============================================================
     需求墙的高对比度 / 助老模式适配
     必须非 scoped 才能命中 html 根级选择器
     ============================================================ -->
<style>
html.theme-high-contrast .demand-section {
  --dw-card: #000000;
  --dw-border: #ffffff;
}

html.theme-high-contrast .demand-section .demand-card {
  background: #000000;
  border-color: #ffffff;
}

html.theme-high-contrast .demand-section .demand-tag {
  color: #000000;
  background: #4ade80;
}

html.theme-high-contrast .demand-section .demand-more {
  color: #ffffff;
  border-color: #ffffff;
}

/* 助老模式：文字与点击目标放大 */
html.mode-elderly .demand-section .demand-title {
  font-size: 20px;
}

html.mode-elderly .demand-section .demand-who,
html.mode-elderly .demand-section .demand-tag {
  font-size: 18px;
}

html.mode-elderly .demand-section .demand-card {
  padding: 24px;
}

html.mode-elderly .demand-section .demand-more {
  min-height: 60px;
  padding: 12px 26px;
  font-size: 18px;
}
</style>
