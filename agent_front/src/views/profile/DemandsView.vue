<template>
  <ProfileSubLayout title="我想要的" desc="发布你的需求，让邻居知道你在找什么；找到后可标记完成">
    <!-- ===== 发布 / 编辑 ===== -->
    <section class="profile-card">
      <div class="card-head">
        <h2 class="card-title">{{ editingId ? '编辑需求' : '发布需求' }}</h2>
        <button v-if="editingId" type="button" class="more-link" @click="resetForm">取消编辑</button>
      </div>

      <div class="form-item">
        <label class="form-label" for="demand-title">需求标题</label>
        <el-input
          id="demand-title"
          v-model="form.title"
          maxlength="100"
          show-word-limit
          placeholder="例如：想要一辆儿童自行车"
        />
      </div>

      <div class="form-item">
        <label class="form-label" for="demand-desc">详细描述（选填）</label>
        <el-input
          id="demand-desc"
          v-model="form.description"
          type="textarea"
          :rows="3"
          maxlength="500"
          show-word-limit
          resize="none"
          placeholder="说明尺寸、成色要求、可接受的交换方式等"
        />
      </div>

      <div class="form-item">
        <label class="form-label" for="demand-category">期望类别（选填）</label>
        <el-input id="demand-category" v-model="form.category" maxlength="50" placeholder="例如：运动 / 图书 / 母婴" />
      </div>

      <div class="form-actions">
        <el-button type="primary" class="save-btn" :loading="submitting" @click="submit">
          {{ editingId ? '保存修改' : '发布需求' }}
        </el-button>
      </div>
    </section>

    <!-- ===== 我的需求 ===== -->
    <section class="profile-card">
      <div class="card-head">
        <h2 class="card-title">我的需求</h2>
        <button type="button" class="more-link" :disabled="loading" @click="load">
          {{ loading ? '刷新中…' : '刷新' }}
        </button>
      </div>

      <div class="mini-tabs" role="tablist" aria-label="按状态筛选我的需求">
        <button
          v-for="tab in STATUS_TABS"
          :key="String(tab.key)"
          type="button"
          role="tab"
          class="mini-tab"
          :class="{ active: activeStatus === tab.key }"
          :aria-selected="activeStatus === tab.key"
          @click="switchStatus(tab.key)"
        >
          {{ tab.label }}
        </button>
      </div>

      <p v-if="loading && !demands.length" class="empty-text">加载中…</p>

      <template v-else-if="demands.length">
        <div v-for="demand in demands" :key="demand.id" class="demand-row">
          <div class="row-main">
            <span class="row-info">
              <span class="row-title">{{ demand.title || '未命名需求' }}</span>
              <span class="row-time">
                <template v-if="demand.category">{{ demand.category }} · </template>
                发布于 {{ formatDate(demand.created_at) }}
              </span>
            </span>
          </div>

          <span class="status-tag" :class="`s-${demand.status}`">{{ demand.status_label }}</span>

          <!-- 仅「进行中」可操作，避免点开才发现不可用 -->
          <span v-if="demand.status === 1" class="row-actions">
            <el-button link type="primary" @click="startEdit(demand)">编辑</el-button>
            <el-button link type="success" :loading="actingId === demand.id" @click="onComplete(demand)">
              标记完成
            </el-button>
            <el-button link type="danger" :loading="actingId === demand.id" @click="onCancel(demand)">
              撤销
            </el-button>
          </span>
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
        <p class="empty-text">
          {{ activeStatus === null ? '还没有发布过需求，在上面写一条试试吧' : '该状态下暂无需求' }}
        </p>
      </template>
    </section>
  </ProfileSubLayout>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import ProfileSubLayout from '../../layouts/ProfileSubLayout.vue'
import { cancelDemand, completeDemand, createDemand, getMyDemands, updateDemand } from '../../api/user'

const PAGE_SIZE = 10

// null 表示不筛选，与后端 status 可选参数对应
const STATUS_TABS = [
  { key: null, label: '全部' },
  { key: 1, label: '进行中' },
  { key: 2, label: '已完成' },
  { key: 3, label: '已撤销' },
]

const demands = ref([])
const total = ref(0)
const page = ref(1)
const size = ref(PAGE_SIZE)
const loading = ref(false)
const activeStatus = ref(null)

/* ---------- 发布 / 编辑表单 ---------- */
const form = reactive({ title: '', description: '', category: '' })
const editingId = ref(null)
const submitting = ref(false)
const actingId = ref(null)

function resetForm() {
  form.title = ''
  form.description = ''
  form.category = ''
  editingId.value = null
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
    if (activeStatus.value !== null) params.status = activeStatus.value
    const data = await getMyDemands(params)
    demands.value = data?.list || []
    total.value = Number(data?.total || 0)
  } catch {
    // 错误提示由请求拦截器统一处理
    demands.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function onPageChange(next) {
  page.value = next
  load()
}

function switchStatus(key) {
  if (activeStatus.value === key) return
  activeStatus.value = key
  // 切换筛选回到第一页，避免停在越界页码上看到空白
  page.value = 1
  load()
}

function startEdit(demand) {
  editingId.value = demand.id
  form.title = demand.title || ''
  form.description = demand.description || ''
  form.category = demand.category || ''
  // 表单在页面顶部，滚回去让用户看到
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

async function submit() {
  const title = form.title.trim()
  if (!title) {
    ElMessage.warning('请填写需求标题')
    return
  }

  submitting.value = true
  try {
    if (editingId.value) {
      await updateDemand(editingId.value, {
        title,
        description: form.description.trim(),
        category: form.category.trim(),
      })
      ElMessage.success('需求已更新')
    } else {
      await createDemand({
        title,
        description: form.description.trim() || undefined,
        category: form.category.trim() || undefined,
      })
      ElMessage.success('需求发布成功')
      page.value = 1
    }
    resetForm()
    await load()
  } catch (error) {
    // 后端已给出中文原因（如「只有进行中的需求可以编辑」），优先展示
    ElMessage.error(error?.response?.data?.message || '操作失败，请稍后再试')
  } finally {
    submitting.value = false
  }
}

async function onComplete(demand) {
  try {
    await ElMessageBox.confirm(
      `确定把「${demand.title || '该需求'}」标记为已完成吗？`,
      '标记完成',
      { confirmButtonText: '标记完成', cancelButtonText: '取消', type: 'success' },
    )
  } catch {
    return // 用户放弃
  }

  actingId.value = demand.id
  try {
    await completeDemand(demand.id)
    ElMessage.success('已标记为完成')
    await load()
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || '操作失败，请稍后再试')
  } finally {
    actingId.value = null
  }
}

async function onCancel(demand) {
  try {
    await ElMessageBox.confirm(
      `确定撤销「${demand.title || '该需求'}」吗？撤销后将不再出现在公开需求墙。`,
      '撤销需求',
      { confirmButtonText: '撤销', cancelButtonText: '再想想', type: 'warning' },
    )
  } catch {
    return // 用户放弃
  }

  actingId.value = demand.id
  try {
    await cancelDemand(demand.id)
    ElMessage.success('需求已撤销')
    // 当前页删空且不是第一页时回退一页，避免出现空白页
    if (demands.value.length === 1 && page.value > 1) page.value -= 1
    await load()
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || '操作失败，请稍后再试')
  } finally {
    actingId.value = null
  }
}

onMounted(load)
</script>

<style scoped>
/* ---------- 卡片头 ---------- */
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

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

/* ---------- 状态筛选（与 Profile.vue 的 mini-tabs 同构） ---------- */
.mini-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.mini-tab {
  padding: 6px 14px;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  color: var(--pc-text-sub);
  background: transparent;
  border: 1px solid var(--pc-border);
  border-radius: 999px;
  cursor: pointer;
  transition: color 0.2s ease, border-color 0.2s ease, background 0.2s ease;
}

.mini-tab:hover {
  color: var(--pc-green);
  border-color: var(--pc-green);
}

.mini-tab.active {
  color: #fff;
  background: var(--pc-green);
  border-color: var(--pc-green);
}

.mini-tab:focus-visible {
  outline: 3px solid var(--pc-green);
  outline-offset: 2px;
}

/* ---------- 需求行 ---------- */
.demand-row {
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

.card-head + .demand-row,
.mini-tabs + .demand-row {
  border-top: none;
}

.demand-row:hover {
  background: var(--pc-bg);
}

.row-main {
  flex: 1;
  min-width: 0;
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
  max-width: 360px;
}

.row-time {
  margin-top: 4px;
  font-size: 13px;
  color: var(--pc-text-sub);
}

.row-actions {
  display: inline-flex;
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
  color: #fff;
  border-radius: 999px;
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

/* ---------- 分页 ---------- */
.pager {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}

@media (max-width: 560px) {
  .demand-row {
    flex-wrap: wrap;
  }

  .row-title {
    max-width: 100%;
    white-space: normal;
  }
}
</style>

<!-- ============================================================
     高对比度 / 助老模式适配（必须非 scoped 才能命中 html 根级选择器）
     ============================================================ -->
<style>
html.theme-high-contrast .sub-page .status-tag {
  color: #000000;
}

html.theme-high-contrast .sub-page .s-1 {
  background: #4ade80;
}

html.theme-high-contrast .sub-page .s-2 {
  background: #e5e5e5;
}

html.theme-high-contrast .sub-page .s-3 {
  background: #fca5a5;
}

html.theme-high-contrast .sub-page .mini-tab.active {
  color: #000000;
}

html.mode-elderly .sub-page .row-title {
  font-size: 20px;
  max-width: 100%;
  white-space: normal;
}

html.mode-elderly .sub-page .row-time,
html.mode-elderly .sub-page .status-tag,
html.mode-elderly .sub-page .more-link,
html.mode-elderly .sub-page .mini-tab {
  font-size: 18px;
}

html.mode-elderly .sub-page .demand-row {
  min-height: 72px;
  flex-wrap: wrap;
}

html.mode-elderly .sub-page .mini-tab {
  min-height: 60px;
  padding: 10px 20px;
}
</style>
