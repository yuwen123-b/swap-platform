<template>
  <ProfileSubLayout title="我的收藏" desc="你收藏的物品都在这里，方便随时回来看看">
    <section class="profile-card">
      <div class="card-head">
        <h2 class="card-title">收藏的物品</h2>
        <button type="button" class="more-link" :disabled="loading" @click="load">
          {{ loading ? '刷新中…' : '刷新' }}
        </button>
      </div>

      <p v-if="loading && !items.length" class="empty-text">加载中…</p>

      <template v-else-if="items.length">
        <div v-for="item in items" :key="item.favorite_id" class="fav-row">
          <!-- 整行主体可点击跳详情；「取消收藏」独立成按钮，避免嵌套按钮 -->
          <button type="button" class="row-main" @click="goDetail(item)">
            <span class="row-thumb">
              <img v-if="item.cover" :src="item.cover" :alt="`${item.title}的图片`" />
              <span v-else class="thumb-fallback" aria-hidden="true">📦</span>
            </span>
            <span class="row-info">
              <span class="row-title">{{ item.title || '未命名物品' }}</span>
              <span class="row-time">收藏于 {{ formatDate(item.favorited_at) }}</span>
            </span>
          </button>

          <span class="status-tag" :class="`s-${item.status}`">{{ item.status_label }}</span>

          <el-button
            link
            type="danger"
            :loading="removingId === item.id"
            @click="onRemove(item)"
          >
            取消收藏
          </el-button>
        </div>

        <div v-if="total > size" class="pager">
          <el-pagination
            layout="prev, pager, next"
            background
            :total="total"
            :page-size="size"
            :current-page="page"
            @current-change="onPageChange"
          />
        </div>
      </template>

      <template v-else>
        <p class="empty-text">还没有收藏任何物品，去「探索物品」看看邻居们的好物吧</p>
        <!-- 空态出口：避免死胡同 -->
        <button type="button" class="empty-cta" @click="router.push('/items')">
          去探索物品
        </button>
      </template>
    </section>
  </ProfileSubLayout>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import ProfileSubLayout from '../../layouts/ProfileSubLayout.vue'
import { getFavorites, removeFavorite } from '../../api/user'

const router = useRouter()

const PAGE_SIZE = 10

const items = ref([])
const total = ref(0)
const page = ref(1)
const size = ref(PAGE_SIZE)
const loading = ref(false)
const removingId = ref(null)

function formatDate(value) {
  if (!value) return '时间未知'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间未知'
  return date.toLocaleDateString('zh-CN')
}

async function load() {
  loading.value = true
  try {
    const data = await getFavorites({ page: page.value, size: size.value })
    items.value = data?.list || []
    total.value = Number(data?.total || 0)
  } catch {
    // 错误提示由请求拦截器统一处理
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function onPageChange(next) {
  page.value = next
  load()
}

function goDetail(item) {
  // 物品已被删除时没有可跳转的详情
  if (!item.id) return
  router.push(`/items/${item.id}`)
}

async function onRemove(item) {
  try {
    await ElMessageBox.confirm(
      `确定要取消收藏「${item.title || '该物品'}」吗？`,
      '取消收藏',
      { confirmButtonText: '取消收藏', cancelButtonText: '再想想', type: 'warning' },
    )
  } catch {
    return // 用户放弃
  }

  removingId.value = item.id
  try {
    await removeFavorite(item.id)
    ElMessage.success('已取消收藏')
    // 当前页删空且不是第一页时回退一页，避免出现空白页
    if (items.value.length === 1 && page.value > 1) page.value -= 1
    await load()
  } catch {
    ElMessage.error('取消收藏失败，请稍后再试')
  } finally {
    removingId.value = null
  }
}

onMounted(load)
</script>

<style scoped>
/* ---------- 卡片头：标题 + 右侧刷新 ---------- */
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

/* 复用子页版式的 .card-title，但头部行内不再需要下外边距 */
.card-head .card-title {
  margin-bottom: 0;
}

.more-link {
  flex-shrink: 0;
  padding: 4px 8px;
  font: inherit;
  font-size: 13px;
  color: var(--pc-text-sub);
  background: none;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: color 0.2s ease, background 0.2s ease;
}

.more-link:hover:not(:disabled) {
  color: var(--pc-green);
  background: var(--pc-bg);
}

.more-link:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.more-link:focus-visible {
  outline: 3px solid var(--pc-green);
  outline-offset: 2px;
}

/* ---------- 收藏行 ---------- */
.fav-row {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 48px;
  padding: 12px;
  margin: 0 -12px;
  border-top: 1px solid var(--pc-border);
  border-radius: 8px;
  transition: background 0.2s ease;
}

/* 首行紧跟卡片头，不再画分隔线 */
.card-head + .fav-row {
  border-top: none;
}

.fav-row:hover {
  background: var(--pc-bg);
}

/* 行主体：占据剩余宽度，内部左图右文 */
.row-main {
  display: flex;
  align-items: center;
  gap: 14px;
  flex: 1;
  min-width: 0;
  padding: 0;
  font: inherit;
  text-align: left;
  color: inherit;
  background: none;
  border: none;
  cursor: pointer;
}

.row-main:focus-visible {
  outline: 3px solid var(--pc-green);
  outline-offset: 2px;
  border-radius: 10px;
}

.row-thumb {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 56px;
  height: 56px;
  overflow: hidden;
  background: var(--pc-bg);
  border: 1px solid var(--pc-border);
  border-radius: 10px;
}

.row-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb-fallback {
  font-size: 24px;
  opacity: 0.6;
}

.row-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.row-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--pc-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 320px;
}

.row-time {
  margin-top: 4px;
  font-size: 13px;
  color: var(--pc-text-sub);
}

/* ---------- 状态标签 ---------- */
.status-tag {
  flex-shrink: 0;
  padding: 2px 10px;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  border-radius: 999px;
}

.s-0 {
  background: #8a8a8a;
}

.s-1 {
  background: var(--pc-green);
}

.s-2 {
  background: #8a8a8a;
}

.s-3 {
  background: #dc2626;
}

.s-4 {
  background: #3b82f6;
}

/* ---------- 分页 / 空态出口 ---------- */
.pager {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}

.empty-cta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 40px;
  padding: 8px 20px;
  margin-top: 4px;
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  color: var(--pc-text);
  background: var(--pc-card);
  border: 1px solid var(--pc-border);
  border-radius: 999px;
  cursor: pointer;
  transition: color 0.2s ease, border-color 0.2s ease, background 0.2s ease;
}

.empty-cta:hover {
  color: var(--pc-green);
  border-color: var(--pc-green);
  background: var(--pc-bg);
}

.empty-cta:focus-visible {
  outline: 3px solid var(--pc-green);
  outline-offset: 2px;
}

/* ---------- 响应式 ---------- */
@media (max-width: 480px) {
  .row-title {
    max-width: 130px;
  }

  .row-thumb {
    width: 48px;
    height: 48px;
  }
}
</style>

<!-- ============================================================
     高对比度 / 助老模式适配（必须非 scoped 才能命中 html 根级选择器）
     ============================================================ -->
<style>
/* 黑底上把状态标签改为浅底深字，保证对比度 */
html.theme-high-contrast .sub-page .status-tag {
  color: #000000;
}

html.theme-high-contrast .sub-page .s-0,
html.theme-high-contrast .sub-page .s-2 {
  background: #e5e5e5;
}

html.theme-high-contrast .sub-page .s-1 {
  background: #4ade80;
}

html.theme-high-contrast .sub-page .s-3 {
  background: #fca5a5;
}

html.theme-high-contrast .sub-page .s-4 {
  background: #93c5fd;
}

/* 助老模式：放大文字与点击目标 */
html.mode-elderly .sub-page .row-title {
  font-size: 20px;
  max-width: 100%;
}

html.mode-elderly .sub-page .row-time,
html.mode-elderly .sub-page .status-tag,
html.mode-elderly .sub-page .more-link {
  font-size: 18px;
}

html.mode-elderly .sub-page .fav-row {
  min-height: 72px;
}

html.mode-elderly .sub-page .row-thumb {
  width: 72px;
  height: 72px;
}

html.mode-elderly .sub-page .empty-cta {
  min-height: 60px;
  padding: 12px 28px;
  font-size: 20px;
}
</style>
