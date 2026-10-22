<template>
  <ProfileSubLayout title="我的物品" desc="这里是你发布的全部物品，可下架不再参与交换的物品">
    <section class="profile-card">
      <h2 class="card-title">我发布的物品</h2>

      <!-- 状态筛选：全部 / 在售 / 审核中 / 已下架 -->
      <div class="tab-bar" role="tablist" aria-label="按状态筛选">
        <button
          v-for="tab in TABS"
          :key="String(tab.key)"
          type="button"
          role="tab"
          class="tab"
          :class="{ active: activeTab === tab.key }"
          :aria-selected="activeTab === tab.key"
          @click="switchTab(tab.key)"
        >
          {{ tab.label }}
        </button>
      </div>

      <p v-if="loading" class="empty-text">加载中…</p>

      <template v-else-if="items.length">
        <div v-for="item in items" :key="item.id" class="item-row">
          <div class="item-thumb">
            <img v-if="item.cover" :src="item.cover" :alt="`${item.title}的图片`" />
            <span v-else class="thumb-fallback" aria-hidden="true">📦</span>
          </div>

          <div class="item-main">
            <div class="item-title-line">
              <span class="item-title">{{ item.title || '未命名物品' }}</span>
              <span class="status-tag" :class="`s-${item.status}`">{{ item.status_label }}</span>
            </div>
            <div class="item-time">发布于 {{ formatDate(item.created_at) }}</div>
          </div>

          <div class="item-actions">
            <el-button link type="primary" @click="goDetail(item.id)">查看</el-button>
            <el-button
              v-if="canRemove(item)"
              link
              type="danger"
              :loading="removingId === item.id"
              @click="onRemove(item)"
            >
              下架
            </el-button>
          </div>
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

      <p v-else class="empty-text">{{ emptyText }}</p>
    </section>
  </ProfileSubLayout>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import ProfileSubLayout from '../../layouts/ProfileSubLayout.vue'
import { getMyItems, removeMyItem } from '../../api/user'

const router = useRouter()

// null 表示不筛选
const TABS = [
  { key: null, label: '全部', empty: '你还没有发布过物品，去「探索物品」页发布第一件吧' },
  { key: 1, label: '在售', empty: '暂无在售物品' },
  { key: 4, label: '审核中', empty: '暂无审核中的物品' },
  { key: 2, label: '已下架', empty: '暂无已下架物品' },
]

const PAGE_SIZE = 10
// 只有「在售(1)」与「审核中(4)」可下架，与后端 REMOVABLE_STATUSES 保持一致
const REMOVABLE_STATUSES = [1, 4]

const activeTab = ref(null)
const page = ref(1)
const size = ref(PAGE_SIZE)
const total = ref(0)
const items = ref([])
const loading = ref(false)
const removingId = ref(null)

const emptyText = computed(
  () => TABS.find((tab) => tab.key === activeTab.value)?.empty || '暂无数据',
)

function canRemove(item) {
  return REMOVABLE_STATUSES.includes(item.status)
}

function formatDate(value) {
  if (!value) return '时间未知'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间未知'
  return date.toLocaleDateString('zh-CN')
}

async function load() {
  loading.value = true
  try {
    const params = { page: page.value, size: size.value }
    if (activeTab.value !== null) params.status = activeTab.value
    const data = await getMyItems(params)
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

function switchTab(key) {
  if (activeTab.value === key) return
  activeTab.value = key
  page.value = 1
  load()
}

function onPageChange(next) {
  page.value = next
  load()
}

function goDetail(id) {
  router.push(`/items/${id}`)
}

async function onRemove(item) {
  try {
    await ElMessageBox.confirm(
      `确定要下架「${item.title || '该物品'}」吗？下架后其他邻居将无法再看到它。`,
      '下架物品',
      { confirmButtonText: '下架', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return // 用户取消
  }

  removingId.value = item.id
  try {
    await removeMyItem(item.id)
    ElMessage.success('物品已下架')
    // 下架后当前筛选可能不再包含该条：在「全部」页就地更新，否则重新拉取
    if (activeTab.value === null) {
      item.status = 2
      item.status_label = '已下架'
    } else {
      await load()
    }
  } catch {
    ElMessage.error('下架失败，请稍后再试')
  } finally {
    removingId.value = null
  }
}

onMounted(load)
</script>

<style scoped>
/* ---------- 状态筛选 Tab ---------- */
.tab-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.tab {
  padding: 8px 16px;
  font: inherit;
  font-size: 14px;
  color: var(--pc-text-sub);
  background: var(--pc-bg);
  border: 1px solid var(--pc-border);
  border-radius: 999px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.tab:hover {
  border-color: var(--pc-green);
  color: var(--pc-green);
}

.tab.active {
  color: #fff;
  background: var(--pc-green);
  border-color: var(--pc-green);
}

.tab:focus-visible {
  outline: 3px solid var(--pc-green);
  outline-offset: 2px;
}

/* ---------- 物品行 ---------- */
.item-row {
  display: flex;
  align-items: center;
  gap: 14px;
  min-height: 48px;
  padding: 12px;
  margin: 0 -12px;
  border-top: 1px solid var(--pc-border);
  border-radius: 8px;
  transition: background 0.2s ease;
}

/* 首行紧跟筛选栏，不再画分隔线（用相邻选择器而非 :first-of-type，
   因为卡片内第一个 div 是 .tab-bar，:first-of-type 命中不到列表首行） */
.tab-bar + .item-row {
  border-top: none;
}

.item-row:hover {
  background: var(--pc-bg);
}

.item-thumb {
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

.item-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb-fallback {
  font-size: 24px;
  opacity: 0.6;
}

.item-main {
  flex: 1;
  min-width: 0;
}

.item-title-line {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}

.item-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--pc-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 320px;
}

.item-time {
  font-size: 13px;
  color: var(--pc-text-sub);
}

.item-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

/* ---------- 状态标签 ---------- */
.status-tag {
  flex-shrink: 0;
  padding: 2px 10px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 999px;
  color: #fff;
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

.pager {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}

/* ---------- 响应式 ---------- */
@media (max-width: 480px) {
  .item-title {
    max-width: 160px;
  }

  .item-thumb {
    width: 48px;
    height: 48px;
  }
}
</style>

<style>
/* 助老模式下放大列表文字（需命中 html 根级选择器，故非 scoped） */
html.mode-elderly .sub-page .item-title {
  font-size: 20px;
  max-width: 100%;
}

html.mode-elderly .sub-page .item-time,
html.mode-elderly .sub-page .status-tag,
html.mode-elderly .sub-page .tab {
  font-size: 18px;
}

html.mode-elderly .sub-page .item-row {
  min-height: 72px;
}

html.mode-elderly .sub-page .item-thumb {
  width: 72px;
  height: 72px;
}
</style>
