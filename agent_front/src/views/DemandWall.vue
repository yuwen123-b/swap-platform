<template>
  <section class="page wall-page">
    <div class="page-head">
      <div class="eyebrow">Community Wants</div>
      <h1 class="page-title">需求<span class="gradient-text">墙</span></h1>
      <p class="page-sub muted">邻居们正在寻找这些物品，也许你刚好有</p>
    </div>

    <!-- 筛选 + 发布入口 -->
    <div class="wall-bar">
      <el-input
        v-model="category"
        class="wall-search"
        clearable
        placeholder="按类别筛选，如：图书 / 运动"
        @keyup.enter="applyFilter"
        @clear="applyFilter"
      />
      <el-button type="primary" @click="applyFilter">筛选</el-button>
      <el-button plain @click="goPublish">发布我的需求</el-button>
    </div>

    <div v-loading="loading" class="wall-body">
      <div v-if="list.length" class="wall-grid">
        <button v-for="d in list" :key="d.id" type="button" class="wall-card" @click="contact(d)">
          <span class="wall-title">{{ d.title || '未命名需求' }}</span>
          <span class="wall-meta">
            <span v-if="d.category" class="wall-tag">{{ d.category }}</span>
            <span class="wall-who">
              {{ d.nickname || '社区邻居' }}<template v-if="d.building"> · {{ d.building }}</template>
            </span>
          </span>
          <span class="wall-time">发布于 {{ formatDate(d.created_at) }}</span>
        </button>
      </div>

      <div v-else-if="!loading" class="wall-empty">
        <span class="wall-empty-icon" aria-hidden="true">🌱</span>
        <p class="wall-empty-text">
          {{ category ? '该类别下暂时没有公开需求' : '暂时没有公开的需求，来发布第一条吧' }}
        </p>
        <button type="button" class="wall-empty-cta" @click="goPublish">发布我的需求</button>
      </div>
    </div>

    <p v-if="list.length" class="wall-foot muted">仅展示最近 {{ MAX_LIMIT }} 条进行中的需求</p>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getDemandWall } from '../api/demand'
import { useUserStore } from '../store/user'

// 后端 limit 上限为 20，这里一次取满；超出部分暂不支持翻页（接口按 limit 设计）
const MAX_LIMIT = 20

const router = useRouter()
const userStore = useUserStore()

const list = ref([])
const loading = ref(false)
const category = ref('')

const myId = () => userStore.user?.id

function formatDate(value) {
  if (!value) return '时间未知'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间未知'
  return date.toLocaleDateString('zh-CN')
}

async function load() {
  loading.value = true
  try {
    const params = { limit: MAX_LIMIT }
    const keyword = category.value.trim()
    if (keyword) params.category = keyword
    const data = await getDemandWall(params)
    list.value = data?.list || []
  } catch {
    // 错误提示由请求拦截器统一处理
    list.value = []
  } finally {
    loading.value = false
  }
}

function applyFilter() {
  load()
}

function goPublish() {
  router.push('/profile/demands')
}

function contact(demand) {
  if (!userStore.isLoggedIn) {
    ElMessageBox.confirm('登录后即可直接私信邻居，聊聊你们的需求。', '尚未登录', {
      confirmButtonText: '去登录',
      cancelButtonText: '稍后再说',
      type: 'info',
    })
      .then(() => router.push('/login?redirect=/demands'))
      .catch(() => {})
    return
  }
  // 后端已排除自己的需求，这里是防御性判断
  if (myId() && demand.user_id === myId()) {
    ElMessage.info('这是你自己发布的需求')
    return
  }
  // Message.vue 支持 ?otherUserId= 直达会话
  router.push(`/messages?otherUserId=${demand.user_id}`)
}

onMounted(load)
</script>

<style scoped>
.wall-page {
  --dw-card: #ffffff;
  --dw-border: rgba(76, 175, 80, 0.22);
  --dw-text: var(--text-primary);
  --dw-sub: var(--text-secondary);
  --dw-bg: #f4fbf6;
}

.page-sub {
  margin: 6px 0 0;
  font-size: 15px;
}

/* ---------- 筛选栏 ---------- */
.wall-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 26px;
}

.wall-search {
  max-width: 320px;
}

/* ---------- 网格 ---------- */
.wall-body {
  min-height: 180px;
}

.wall-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-top: 20px;
}

.wall-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 20px;
  text-align: left;
  font: inherit;
  color: inherit;
  background: var(--dw-card);
  border: 1px solid var(--dw-border);
  border-radius: 16px;
  cursor: pointer;
  transition: transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease;
}

.wall-card:hover {
  border-color: var(--green-primary);
  transform: translateY(-5px);
  box-shadow: 0 12px 26px rgba(46, 125, 50, 0.14);
}

.wall-card:focus-visible {
  outline: 3px solid var(--green-primary);
  outline-offset: 2px;
}

.wall-title {
  font-size: 16px;
  font-weight: 700;
  line-height: 1.6;
  color: var(--dw-text);
}

.wall-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.wall-tag {
  padding: 3px 10px;
  font-size: 12px;
  font-weight: 600;
  color: var(--green-active);
  background: var(--green-soft);
  border-radius: 999px;
}

.wall-who {
  font-size: 13px;
  color: var(--dw-sub);
}

.wall-time {
  font-size: 12.5px;
  color: var(--dw-sub);
}

/* ---------- 空态 ---------- */
.wall-empty {
  padding: 66px 20px;
  margin-top: 20px;
  text-align: center;
  background: var(--dw-card);
  border: 1px dashed var(--dw-border);
  border-radius: 16px;
}

.wall-empty-icon {
  font-size: 42px;
}

.wall-empty-text {
  margin: 12px 0 16px;
  font-size: 15px;
  font-weight: 600;
  color: var(--dw-text);
}

.wall-empty-cta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 40px;
  padding: 8px 22px;
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

.wall-empty-cta:hover {
  color: var(--green-primary);
  border-color: var(--green-primary);
  background: var(--dw-bg);
}

.wall-foot {
  margin-top: 22px;
  font-size: 13px;
  text-align: center;
}

@media (max-width: 900px) {
  .wall-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 560px) {
  .wall-grid {
    grid-template-columns: 1fr;
  }

  .wall-search {
    max-width: 100%;
  }
}
</style>

<!-- ============================================================
     高对比度 / 助老模式适配（必须非 scoped 才能命中 html 根级选择器）
     ============================================================ -->
<style>
html.theme-high-contrast .wall-page {
  --dw-card: #000000;
  --dw-border: #ffffff;
  --dw-bg: #000000;
}

html.theme-high-contrast .wall-page .wall-card,
html.theme-high-contrast .wall-page .wall-empty {
  background: #000000;
  border-color: #ffffff;
}

html.theme-high-contrast .wall-page .wall-tag {
  color: #000000;
  background: #4ade80;
}

html.mode-elderly .wall-page .wall-title {
  font-size: 20px;
}

html.mode-elderly .wall-page .wall-who,
html.mode-elderly .wall-page .wall-time,
html.mode-elderly .wall-page .wall-tag,
html.mode-elderly .wall-page .wall-empty-text,
html.mode-elderly .wall-page .wall-foot,
html.mode-elderly .wall-page .page-sub {
  font-size: 18px;
}

html.mode-elderly .wall-page .wall-card {
  padding: 24px;
}

html.mode-elderly .wall-page .wall-empty-cta {
  min-height: 60px;
  padding: 12px 28px;
  font-size: 20px;
}
</style>
