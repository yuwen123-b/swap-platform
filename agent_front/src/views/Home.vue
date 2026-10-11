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
          <img class="kb-img" :src="slide.image" :alt="themeText(slide.id)" draggable="false" />
        </el-carousel-item>
      </el-carousel>

      <!-- 渐变遮罩：左深右透，保证文案可读；底部压暗托住缩略图 -->
      <div class="hero-mask"></div>

      <!-- 顶层文案 -->
      <div class="hero-content">
        <span class="hero-eyebrow">{{ t('home.heroEyebrow') }}</span>
        <h1 class="hero-title">{{ t('home.heroTitle') }}</h1>
        <p class="hero-sub">
          {{ t('home.heroSub') }}
        </p>
        <div class="hero-cta">
          <button class="cta cta-primary" type="button" @click="go('/items')">
            {{ t('home.ctaExplore') }}
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
          </button>
          <button class="cta cta-ghost" type="button" @click="go('/pricing')">{{ t('home.ctaPricing') }}</button>
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
          <img :src="slide.thumb" :alt="themeText(slide.id)" />
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
            <div class="ai-title">{{ t('home.aiTitle') }}</div>
            <div class="ai-desc">{{ t('home.aiDesc') }}</div>
          </div>
        </div>
        <div class="ai-actions">
          <el-button type="primary" @click="go('/pricing')">{{ t('home.ctaPricing') }}</el-button>
          <el-button plain @click="go('/recognition')">{{ t('nav.identify') }}</el-button>
        </div>
      </section>

      <!-- 2. 低碳数据看板：UI 已下线（数据逻辑保留在 <script setup> 中，见 TODO 注释） -->

      <!-- 3. 物品分类快捷入口 -->
      <section class="cate-section">
        <div class="section-head">
          <span class="sec-eyebrow">{{ t('home.quickEntry') }}</span>
          <h2 class="sec-title">{{ t('home.secCateTitle') }}</h2>
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
            <span class="sec-eyebrow">{{ t('home.communityFlowing') }}</span>
            <h2 class="sec-title">{{ t('home.secItemsTitle') }}</h2>
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
                      {{ t('home.distanceLocal') }}
                    </span>
                    <span class="meta carbon">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10z"/><path d="M2 21c0-3 1.85-5.36 5.08-6"/></svg>
                      {{ t('home.carbonLabel', { value: item.carbon }) }}
                    </span>
                  </div>
                </div>
              </article>
            </el-col>
          </el-row>

          <!-- 绿色空状态 -->
          <div v-else-if="!itemsLoading && !itemsError" class="green-empty">
            <span class="green-empty-icon">🌱</span>
            <p class="green-empty-text">{{ t('home.emptyItems') }}</p>
          </div>

          <!-- 距离排序等开发中提示 -->
          <el-alert
            v-if="showDistanceTip && !itemsLoading"
            class="items-tip"
            :title="t('home.distanceTip')"
            type="info"
            show-icon
            :closable="false"
          />

          <!-- 接口错误：仅提示，不崩溃 -->
          <el-alert
            v-if="itemsError && !itemsLoading"
            class="items-tip"
            :title="t('home.itemsLoadFailed')"
            type="warning"
            show-icon
            :closable="false"
          />
        </div>
      </section>

      <!-- 5. 邻里互换故事 -->
      <section class="story-section">
        <div class="section-head">
          <span class="sec-eyebrow">{{ t('home.communityWarmth') }}</span>
          <h2 class="sec-title">{{ t('home.storyTitle') }}</h2>
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
        <RouterLink to="/about">{{ t('home.footerAbout') }}</RouterLink>
        <RouterLink to="/convention">{{ t('home.footerConvention') }}</RouterLink>
        <RouterLink to="/help">{{ t('home.footerHelp') }}</RouterLink>
        <RouterLink to="/contact">{{ t('home.footerContact') }}</RouterLink>
      </nav>
      <div class="footer-divider"></div>
      <p class="footer-copy">{{ t('home.footerCopy') }}</p>
    </footer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  categories as rawCategories,
  heroSlides,
  lowCarbonStats,
  swapStories as rawSwapStories,
} from '../mock/home'
import { getItems } from '../api/item'
import { useI18n } from '../i18n'

const { t } = useI18n()
const router = useRouter()
const go = (path) => router.push(path)

/* ---------- mock 数据按 id 映射当前语言文案 ---------- */
const THEME_KEY = { 1: 'themeGreen', 2: 'themeReuse', 3: 'themeBooks', 4: 'themeNeighbor' }
function themeText(id) {
  return t(`home.${THEME_KEY[id] || 'themeGreen'}`)
}

const CATEGORY_KEY = {
  22: 'catAppliance', 23: 'catBaby', 9: 'catBooks', 12: 'catFurniture',
  21: 'catDigital', 13: 'catClothing', 14: 'catSports', 24: 'catOther',
}
const categories = computed(() =>
  rawCategories.map((c) => ({ ...c, name: t(`home.${CATEGORY_KEY[c.id] || 'catOther'}`) })),
)

const swapStories = computed(() =>
  rawSwapStories.map((s) => ({
    ...s,
    name: t(`home.story${s.id}Name`),
    text: t(`home.story${s.id}Text`),
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

/* ---------- 邻居上传物品：从后端真实接口获取 ---------- */
// 绿色默认占位图（内联 SVG，无需额外文件）
const FALLBACK_IMAGE =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='600' height='420'%3E%3Crect width='100%25' height='100%25' fill='%23E8F5E9'/%3E%3Cg fill='none' stroke='%234CAF50' stroke-width='6' stroke-linecap='round'%3E%3Cpath d='M300 250c-20-52-62-76-102-72-40 4-64 34-62 70 2 34 28 56 64 56h98c34 0 60-22 62-54 2-34-20-62-58-66-38-4-78 18-96 66'/%3E%3C/g%3E%3C/svg%3E"

const itemFilters = computed(() => [
  { key: 'latest', label: t('home.filterLatest') },
  { key: 'nearest', label: t('home.filterNearest') },
  { key: 'carbon', label: t('home.filterCarbon') },
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
const showDistanceTip = ref(false)

const MODE_KEY = { 1: 'modeFree', 2: 'modeSwap', 3: 'modePoints' }
function modeText(code) {
  return t(`home.${MODE_KEY[code] || 'modeSwap'}`)
}
function conditionText(level) {
  const key = `home.condition${level}`
  const text = t(key)
  return text === key ? t('home.conditionGood') : text
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
  }
}

async function loadItems() {
  itemsLoading.value = true
  itemsError.value = false
  showDistanceTip.value = false
  try {
    const data = await getItems(
      {
        page: 1,
        size: 8,
        sort_by: SORT_PARAM[activeFilter.value],
      },
      // 距离排序会 400，改为页面内“开发中”提示，不弹红色错误 toast
      { skipErrorToast: activeFilter.value === 'nearest' },
    )
    items.value = (data.items || []).map(normalize)
  } catch (error) {
    // 注意：HTTP 4xx 走 axios 错误拦截器，后端提示在 response.data.message
    const serverMsg = error?.response?.data?.message || error?.message || ''
    // 距离排序后端明确返回“开发中”：回退筛选并重新加载最新数据
    if (serverMsg.includes('距离排序')) {
      showDistanceTip.value = true
      activeFilter.value = 'latest'
      try {
        const data = await getItems({ page: 1, size: 8, sort_by: 'created_at' })
        items.value = (data.items || []).map(normalize)
      } catch {
        items.value = []
        itemsError.value = true
      }
    } else {
      items.value = []
      itemsError.value = true
    }
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

/* 图片加载失败：仅回填一次默认绿色占位图，避免死循环 */
function onImgError(event) {
  const img = event.target
  if (img.dataset.fb) return
  img.dataset.fb = '1'
  img.src = FALLBACK_IMAGE
}

onMounted(() => {
  loadItems()
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
  background: var(--c-deep);
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

.hero-eyebrow {
  align-self: flex-start;
  padding: 7px 16px;
  border: 1px solid rgba(165, 214, 167, 0.55);
  border-radius: 999px;
  background: rgba(76, 175, 80, 0.16);
  color: var(--c-mint);
  font-size: 13px;
  letter-spacing: 3px;
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
}
</style>
