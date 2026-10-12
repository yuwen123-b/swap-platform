<template>
  <section class="page explore-page">
    <div class="heading-row">
      <div>
        <div class="eyebrow">社区好物</div>
        <h1 class="page-title">
          正在流动的<span class="gradient-text">温暖物品</span>
        </h1>
      </div>
      <el-button type="primary" class="upload-trigger" @click="openUploadDialog">
        上传物品
      </el-button>
    </div>

    <div class="filters glass-card">
      <el-input
        v-model="filters.keyword"
        placeholder="搜索物品名称或描述"
        clearable
        @keyup.enter="search"
        @clear="search"
      />
      <el-select
        v-model="filters.category_id"
        placeholder="全部分类"
        clearable
        @change="search"
      >
        <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
      </el-select>
      <el-select
        v-model="filters.exchange_mode"
        placeholder="全部方式"
        clearable
        @change="search"
      >
        <el-option label="赠送" value="1" />
        <el-option label="交换" value="2" />
        <el-option label="低价转让" value="3" />
      </el-select>
      <el-button type="primary" @click="search">搜索</el-button>
    </div>

    <div class="sort-row glass-card">
      <span class="sort-label">排序：</span>
      <el-radio-group v-model="sortBy" @change="onSortChange">
        <el-radio-button value="created_at">最新发布</el-radio-button>
        <el-radio-button value="distance">离我最近</el-radio-button>
        <el-radio-button value="carbon_value">碳减排最多</el-radio-button>
      </el-radio-group>
    </div>

    <div v-loading="loading">
      <el-row v-if="displayItems.length" :gutter="18">
        <el-col
          v-for="item in displayItems"
          :key="item.id"
          :xs="12"
          :sm="12"
          :md="8"
          :lg="6"
        >
          <article class="item-card" @click="router.push(`/items/${item.id}`)">
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
                  本社区
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
      <div v-else-if="!loading && !loadError" class="green-empty">
        <span class="green-empty-icon">🌿</span>
        <p class="green-empty-text">暂时没有找到符合条件的物品哦～</p>
      </div>

      <!-- 距离排序等开发中提示 -->
      <el-alert
        v-if="showDistanceTip && !loading"
        class="load-error"
        title="距离排序功能开发中"
        type="info"
        show-icon
        :closable="false"
      />
      <el-alert
        v-if="loadError && !loading"
        class="load-error"
        title="物品列表加载失败"
        description="请检查网络后稍后再试，或调整筛选条件。"
        type="warning"
        show-icon
        :closable="false"
      />
    </div>

    <div class="pager" v-if="total > pageSize">
      <el-pagination
        layout="prev, pager, next"
        :total="total"
        :page-size="pageSize"
        v-model:current-page="page"
        @current-change="load"
      />
    </div>

    <el-dialog v-model="uploadVisible" title="上传物品" width="560px" destroy-on-close>
      <el-form label-position="top" @submit.prevent="submitUpload">
        <el-form-item label="物品名称" required>
          <el-input v-model="uploadForm.title" placeholder="例如：九成新儿童自行车" />
        </el-form-item>
        <el-form-item label="物品描述" required>
          <el-input
            v-model="uploadForm.description"
            type="textarea"
            :rows="4"
            placeholder="描述物品状况、使用情况等"
          />
        </el-form-item>
        <el-form-item label="物品图片">
          <input
            ref="imageInput"
            class="image-input"
            type="file"
            accept="image/*"
            @change="handleImageChange"
          />
          <div v-if="imagePreview" class="image-preview-wrap">
            <img class="image-preview" :src="imagePreview" alt="物品图片预览" />
            <el-button link type="danger" @click="clearImage">移除图片</el-button>
          </div>
        </el-form-item>
        <el-form-item label="分类" required>
          <el-select v-model="uploadForm.category_id" placeholder="选择分类" class="form-control">
            <el-option v-for="category in categories" :key="category.id" :label="category.name" :value="category.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="期望交换物品">
          <el-input v-model="uploadForm.expected_exchange" placeholder="例如：绘本、儿童玩具" />
        </el-form-item>
        <el-form-item label="联系方式" required>
          <el-input v-model="uploadForm.contact" placeholder="手机号、微信号或其他联系方式" />
        </el-form-item>
        <div class="dialog-actions">
          <el-button @click="uploadVisible = false">取消</el-button>
          <el-button type="primary" native-type="submit" :loading="uploading">提交上传</el-button>
        </div>
      </el-form>
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '../store/user'
import { getItems, getCategories, uploadItem } from '../api/item'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const apiItems = ref([])
const categories = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 12
const loading = ref(false)
const loadError = ref(false)
const showDistanceTip = ref(false)
const sortBy = ref('created_at')
const uploadVisible = ref(false)
const uploading = ref(false)
const imageInput = ref(null)
const imagePreview = ref('')
const imageFile = ref(null)

const filters = reactive({
  keyword: '',
  category_id: null,
  exchange_mode: null,
})

const uploadForm = reactive({
  title: '',
  description: '',
  category_id: null,
  expected_exchange: '',
  contact: '',
})

// 绿色默认占位图（内联 SVG，无需额外文件）
const FALLBACK_IMAGE =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='600' height='420'%3E%3Crect width='100%25' height='100%25' fill='%23E8F5E9'/%3E%3Cg fill='none' stroke='%234CAF50' stroke-width='6' stroke-linecap='round'%3E%3Cpath d='M300 250c-20-52-62-76-102-72-40 4-64 34-62 70 2 34 28 56 64 56h98c34 0 60-22 62-54 2-34-20-62-58-66-38-4-78 18-96 66'/%3E%3C/g%3E%3C/svg%3E"

/* ---------- 交换模式 / 成色文案 ---------- */
const MODE_TEXT = { 1: '赠送', 2: '交换', 3: '低价转让' }
function modeText(code) {
  return MODE_TEXT[Number(code)] || '交换'
}
const CONDITION_TEXT = { 1: '成色一般', 2: '七成新', 3: '八成新', 4: '九成新', 5: '几乎全新' }
function conditionText(level) {
  return CONDITION_TEXT[level] || '状态良好'
}

/* ---------- 字段归一化：接口数据统一为卡片展示结构 ---------- */
function firstImage(item) {
  if (typeof item.images === 'string') {
    try {
      const parsed = JSON.parse(item.images)
      return Array.isArray(parsed) && parsed.length ? parsed[0] : ''
    } catch {
      return ''
    }
  }
  return Array.isArray(item.images) && item.images.length ? item.images[0] : ''
}

function normalizeApiItem(item) {
  return {
    id: item.id,
    title: item.title,
    image: firstImage(item) || FALLBACK_IMAGE,
    conditionLevel: item.condition_level,
    modeCode: Number(item.exchange_mode ?? 2),
    carbon: Number(item.carbon_value || 0),
    category_id: item.category_id ?? null,
  }
}

/* ---------- 展示列表：仅接口真实物品（筛选/排序/分页均由服务端完成） ---------- */
const displayItems = computed(() => apiItems.value.map(normalizeApiItem))

/* 交换模式标签配色：按数值 code 判断 */
function modeClass(code) {
  if (Number(code) === 3) return 'mode-points'
  if (Number(code) === 1) return 'mode-free'
  return 'mode-swap'
}

/* 图片加载失败：仅回填一次默认绿色占位图，避免死循环 */
function onImgError(event) {
  const img = event.target
  if (img.dataset.fb) return
  img.dataset.fb = '1'
  img.src = FALLBACK_IMAGE
}

async function load() {
  loading.value = true
  loadError.value = false
  showDistanceTip.value = false
  try {
    const params = {
      keyword: filters.keyword || undefined,
      category_id: filters.category_id || undefined,
      exchange_mode: filters.exchange_mode || undefined,
      page: page.value,
      size: pageSize,
      sort_by: sortBy.value,
    }
    const data = await getItems(params, {
      // 距离排序会 400，改为页面内“开发中”提示，不弹红色错误 toast
      skipErrorToast: sortBy.value === 'distance',
    })
    apiItems.value = data.items || []
    total.value = data.total || 0
  } catch (error) {
    apiItems.value = []
    total.value = 0
    // 注意：HTTP 4xx 走 axios 错误拦截器，后端提示在 response.data.message
    const serverMsg = error?.response?.data?.message || error?.message || ''
    if (serverMsg.includes('距离排序')) {
      // 后端明确提示距离排序开发中：回退到最新发布，并重新加载
      showDistanceTip.value = true
      sortBy.value = 'created_at'
      loading.value = true
      try {
        const data = await getItems({
          keyword: filters.keyword || undefined,
          category_id: filters.category_id || undefined,
          exchange_mode: filters.exchange_mode || undefined,
          page: page.value,
          size: pageSize,
          sort_by: 'created_at',
        })
        apiItems.value = data.items || []
        total.value = data.total || 0
      } catch {
        loadError.value = true
      } finally {
        loading.value = false
      }
    } else {
      loadError.value = true
    }
  } finally {
    loading.value = false
  }
}

function openUploadDialog() {
  if (!userStore.isLoggedIn) {
    ElMessage.warning('请先登录后再上传物品')
    router.push('/login?redirect=/items')
    return
  }
  uploadVisible.value = true
}

function handleImageChange(event) {
  const file = event.target.files?.[0]
  if (!file) return
  imageFile.value = file
  if (imagePreview.value) URL.revokeObjectURL(imagePreview.value)
  imagePreview.value = URL.createObjectURL(file)
}

function clearImage() {
  imageFile.value = null
  if (imagePreview.value) URL.revokeObjectURL(imagePreview.value)
  imagePreview.value = ''
  if (imageInput.value) imageInput.value.value = ''
}

function resetUploadForm() {
  Object.assign(uploadForm, {
    title: '',
    description: '',
    category_id: null,
    expected_exchange: '',
    contact: '',
  })
  clearImage()
}

async function submitUpload() {
  if (!uploadForm.title || !uploadForm.description || !uploadForm.category_id || !uploadForm.contact) {
    ElMessage.warning('请填写物品名称、描述、分类和联系方式')
    return
  }

  const formData = new FormData()
  formData.append('title', uploadForm.title)
  formData.append('description', uploadForm.description)
  formData.append('category_id', String(uploadForm.category_id))
  formData.append('expected_exchange', uploadForm.expected_exchange)
  formData.append('contact', uploadForm.contact)
  if (imageFile.value) formData.append('image', imageFile.value)

  uploading.value = true
  try {
    await uploadItem(formData)
    // 提交后进入待审核（status=4），审核通过前不出现在列表中，故不刷新列表
    ElMessage.success('提交成功，等待审核通过后展示')
    ElMessage.info('360° 效果生成中，完成后可在物品详情页查看')
    uploadVisible.value = false
    resetUploadForm()
  } catch (error) {
    ElMessage.error(error.message || '物品上传失败，请稍后重试')
  } finally {
    uploading.value = false
  }
}

function search() {
  page.value = 1
  load()
}

function onSortChange() {
  page.value = 1
  load()
}

onMounted(() => {
  // 支持首页分类入口携带的 ?category_id=xxx
  const queryCategory = Number(route.query.category_id)
  if (queryCategory) filters.category_id = queryCategory
  // 分类与物品加载互不阻塞，避免单点失败导致整页 Network Error
  getCategories()
    .then((data) => {
      categories.value = data || []
    })
    .catch(() => {
      categories.value = []
    })
  load()
})

onBeforeUnmount(() => {
  if (imagePreview.value) URL.revokeObjectURL(imagePreview.value)
})
</script>

<style scoped>
.heading-row {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
}

.upload-trigger {
  margin-bottom: 28px;
}

.load-error {
  margin-top: 20px;
}

/* 排序行 */
.sort-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0 0 22px;
  padding: 12px 16px;
}

.sort-label {
  font-size: 14px;
  color: var(--text-secondary);
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
  color: #2e7d32;
  font-size: 15px;
  font-weight: 600;
}

.image-input {
  width: 100%;
  padding: 10px;
  border: 1px dashed var(--border-soft);
  border-radius: var(--r-sm);
  color: var(--text-secondary);
  background: var(--green-softer);
}

.image-preview-wrap {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-top: 12px;
}

.image-preview {
  width: 120px;
  height: 90px;
  border-radius: var(--r-sm);
  object-fit: cover;
  border: 1px solid var(--border-soft);
}

.form-control {
  width: 100%;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 10px;
}

.filters {
  display: flex;
  gap: 12px;
  margin: 30px 0 26px;
  padding: 16px;
  flex-wrap: wrap;
}

.filters .el-input {
  flex: 1;
  min-width: 200px;
}

.filters .el-select {
  width: 150px;
}

/* ---------- 物品卡片：白底 / 16px 圆角 / 浅绿边框 / 悬浮上浮 ---------- */
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
  border-color: #4caf50;
  transform: translateY(-6px);
  box-shadow: 0 16px 34px rgba(46, 125, 50, 0.16);
}

.item-img {
  position: relative;
  height: 168px;
  overflow: hidden;
  background: #f4fbf6;
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
  color: #2e7d32;
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
  color: #1b3a26;
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
  color: #2e7d32;
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
  color: #63786d;
  font-size: 12.5px;
}

.meta svg {
  width: 14px;
  height: 14px;
}

.meta.carbon {
  color: #4caf50;
}

.pager {
  display: flex;
  justify-content: center;
  margin-top: 40px;
}

@media (max-width: 500px) {
  .heading-row {
    align-items: flex-start;
    flex-direction: column;
    gap: 0;
  }

  .upload-trigger {
    margin-bottom: 18px;
  }

  .filters .el-select {
    width: 100%;
  }
}
</style>
