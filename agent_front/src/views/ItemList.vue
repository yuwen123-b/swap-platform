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

    <el-tabs v-model="activeTab" class="explore-tabs" @tab-change="onTabChange">
      <!-- ========== 「闲」：邻里二手（现有列表原样，exchange_mode 1/2/3 全量） ========== -->
      <el-tab-pane name="used">
        <template #label>
          <span class="tab-main">闲</span>
          <span class="tab-sub">邻里二手</span>
        </template>

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
            <el-option label="免费送" value="1" />
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
                  <!-- 与首页卡片一致：仅已生成 360° 视图的物品显示角标 -->
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
          <div v-else-if="!loading && !loadError" class="green-empty">
            <span class="green-empty-icon">🌿</span>
            <p class="green-empty-text">暂时没有找到符合条件的物品哦～</p>
          </div>

          <!-- 加载失败提示（保留已加载列表，不再用本地 mock 覆盖真实数据） -->
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

      </el-tab-pane>

      <!-- ========== 「新」：积分兑换（一期只上商家好物；lazy 首次切到才挂载） ========== -->
      <el-tab-pane name="new" lazy>
        <template #label>
          <span class="tab-main">新</span>
          <span class="tab-sub">积分兑换</span>
        </template>

        <MerchantProductGrid />
      </el-tab-pane>
    </el-tabs>

    <el-dialog
      v-model="uploadVisible"
      title="上传物品"
      width="560px"
      destroy-on-close
      @closed="onDialogClosed"
    >
      <el-form label-position="top" @submit.prevent="submitUpload">
        <el-form-item label="物品名称" required>
          <el-input
            v-model="uploadForm.title"
            placeholder="例如：九成新儿童自行车"
            maxlength="50"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="物品描述" required>
          <el-input
            v-model="uploadForm.description"
            type="textarea"
            :rows="4"
            placeholder="描述物品状况、使用情况等"
            maxlength="500"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="物品图片" required>
          <!-- 复用公共上传组件：文件选择 / 拍照 / 拖拽 / 校验（jpg/png/webp/gif，≤5MB）都在组件内，
               提交仍是本页的 submitUpload() —— 组件不做上传 -->
          <ImageUploader
            v-model="imageFile"
            mode="publish"
            preview-alt="待上传物品图片预览"
            :max-size="MAX_IMAGE_SIZE"
          />
        </el-form-item>
        <el-form-item label="分类" required>
          <el-select v-model="uploadForm.category_id" placeholder="选择分类" class="form-control">
            <el-option v-for="category in categories" :key="category.id" :label="category.name" :value="category.id" />
          </el-select>
        </el-form-item>

        <!-- 交易方式：1=免费送 2=交换 3=低价转让 4=交给平台回收（与后端 item.exchange_mode 同口径）。
             文案刻意区分：本选项是「交给**平台**回收」（平台取件、立即得积分）；
             积分商城里的「绿源回收站」是商家模块的店铺，两者互不相干（用户要求 3）。 -->
        <el-form-item label="交易方式" required>
          <el-radio-group v-model="uploadForm.exchange_mode" class="mode-group">
            <el-radio-button :value="1">免费送</el-radio-button>
            <el-radio-button :value="2">交换</el-radio-button>
            <el-radio-button :value="3">低价转让</el-radio-button>
            <el-radio-button :value="4">交给平台回收</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item v-if="uploadForm.exchange_mode === 2" label="期望交换物品">
          <el-input v-model="uploadForm.expected_exchange" placeholder="例如：绘本、儿童玩具" />
        </el-form-item>

        <!-- 平台回收专属区：成色（估价依据）→ 估价展示 → 取件方式 -->
        <template v-if="uploadForm.exchange_mode === 4">
          <el-form-item label="物品成色" required>
            <el-radio-group v-model="uploadForm.condition_level" class="mode-group" @change="refreshEstimate">
              <el-radio-button v-for="n in 5" :key="n" :value="n">{{ CONDITION_TEXT[n] }}</el-radio-button>
            </el-radio-group>
            <p class="field-tip">平台按成色自动估价，提交后立即到账积分</p>
          </el-form-item>
          <el-form-item label="平台估价">
            <div class="estimate-box" aria-live="polite">
              <template v-if="estimateLoading">估价计算中…</template>
              <template v-else>
                <strong class="estimate-num">{{ estimatePoints }}</strong>
                <span class="estimate-unit">积分</span>
                <span class="estimate-note">提交后立即到账，无需等待成交</span>
              </template>
            </div>
          </el-form-item>
          <el-form-item label="取件方式" required>
            <el-radio-group v-model="recycleForm.pickup_method" class="mode-group">
              <el-radio-button :value="1">送到回收点</el-radio-button>
              <el-radio-button :value="2">上门取件</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="recycleForm.pickup_method === 2" label="取件地址" required>
            <el-input
              v-model="recycleForm.pickup_address"
              placeholder="填写上门取件地址（如：3 号楼 501）"
              maxlength="200"
              show-word-limit
            />
          </el-form-item>
        </template>

        <el-form-item v-if="uploadForm.exchange_mode === 3" label="转让价（元）" required>
          <el-input-number
            v-model="uploadForm.price"
            :min="0.01"
            :max="99999"
            :precision="2"
            :step="1"
            controls-position="right"
            class="form-control"
          />
          <p class="field-tip">收个小价，帮它找到下一个主人就好～</p>
        </el-form-item>

        <el-form-item label="联系方式" required>
          <el-input
            v-model="uploadForm.contact"
            placeholder="手机号、微信号或其他联系方式"
            maxlength="100"
            show-word-limit
          />
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
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { categories as staticCategories } from '../mock/home'
import { useUserStore } from '../store/user'
import { usePublishDraftStore } from '../store/publishDraft'
import { getItems, getCategories, uploadItem } from '../api/item'
import { getRecycleEstimate, submitRecycle } from '../api/recycle'
import ImageUploader from '../components/ImageUploader.vue'
import MerchantProductGrid from '../components/MerchantProductGrid.vue'

// 与后端 app/api/v1/item.py 的 MAX_IMAGE_SIZE 保持一致
const MAX_IMAGE_SIZE = 5 * 1024 * 1024
// 与后端 item.py 的 MIN_PRICE / MAX_PRICE 保持一致（低价转让价区间）
const MIN_PRICE = 0.01
const MAX_PRICE = 99999

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const publishDraft = usePublishDraftStore()

/* ============================================================
   双 Tab：闲（邻里二手）/ 新（积分兑换）
   ------------------------------------------------------------
   - 默认落「闲」且**不写 tab 参数**，保持既有入口语义
     （首页两个入口 /items 与 /items?category_id=xx 都不带 tab）。
   - 切到「新」写 ?tab=new；切回「闲」删掉该参数。
   - URL 是唯一真源：前进/后退经 watch(route.query.tab) 反向同步 activeTab。
   - 两个 Tab 的状态互不干扰：筛选、排序、页码在切走再切回后原样保留
     （「闲」pane 不卸载，不用 v-if）。
   ============================================================ */
function tabFromQuery(value) {
  const raw = Array.isArray(value) ? value[0] : value
  return raw === 'new' ? 'new' : 'used'
}

const activeTab = ref(tabFromQuery(route.query.tab))

function onTabChange(name) {
  const next = name === 'new' ? 'new' : 'used'
  // 已在目标 Tab（含前进/后退触发的程序化切换）时不重复写历史
  if (next === tabFromQuery(route.query.tab)) return
  const query = { ...route.query }
  if (next === 'new') {
    query.tab = 'new'
  } else {
    delete query.tab
  }
  router.push({ path: route.path, query })
}

watch(
  () => route.query.tab,
  (value) => {
    const next = tabFromQuery(value)
    if (activeTab.value !== next) activeTab.value = next
  },
)

const apiItems = ref([])
const categories = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 12
const loading = ref(false)
const loadError = ref(false)
const sortBy = ref('created_at')
const uploadVisible = ref(false)
const uploading = ref(false)
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
  // 1=免费送 2=交换 3=低价转让 4=交给平台回收（与 item.exchange_mode 同口径）
  exchange_mode: 1,
  // 低价转让时的转让价；非低价转让提交时会归 0（后端也会再兜一层）
  price: 0.01,
  // 成色：平台回收时必填（1-5，估价依据）；其它方式 0 表示未填写
  condition_level: 0,
  original_price: 0,
})

// 平台回收提交参数（随物品一起在发布成功后提交给 PUT /items/{id}/recycle）
const recycleForm = reactive({
  pickup_method: 1,
  pickup_address: '',
})

// ---------- 平台估价：服务端唯一真源，前端只展示、绝不本地复算 ----------
const estimatePoints = ref(0)
const estimateLoading = ref(false)

async function refreshEstimate() {
  // 成色未选（0）：清空估价展示
  const level = Number(uploadForm.condition_level) || 0
  if (level < 1) {
    estimatePoints.value = 0
    return
  }
  estimateLoading.value = true
  try {
    const data = await getRecycleEstimate(level, { skipErrorToast: true })
    estimatePoints.value = Number(data?.estimate_points) || 0
  } catch {
    // 估价接口失败不阻断发布：提交时后端会重新按服务端口径计算
    estimatePoints.value = 0
    ElMessage.warning('估价暂时不可用，可稍后重试；到账积分以后端实际计算为准')
  } finally {
    estimateLoading.value = false
  }
}

// 切到「交给平台回收」时按当前成色（若有）刷新估价；切走时复位成色与回收表单
watch(
  () => uploadForm.exchange_mode,
  (mode) => {
    if (Number(mode) === 4) {
      refreshEstimate()
    } else {
      uploadForm.condition_level = 0
      estimatePoints.value = 0
    }
  },
)

// 绿色默认占位图（内联 SVG，无需额外文件）
const FALLBACK_IMAGE =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='600' height='420'%3E%3Crect width='100%25' height='100%25' fill='%23E8F5E9'/%3E%3Cg fill='none' stroke='%234CAF50' stroke-width='6' stroke-linecap='round'%3E%3Cpath d='M300 250c-20-52-62-76-102-72-40 4-64 34-62 70 2 34 28 56 64 56h98c34 0 60-22 62-54 2-34-20-62-58-66-38-4-78 18-96 66'/%3E%3C/g%3E%3C/svg%3E"

/* ---------- 交换模式 / 成色文案 ---------- */
// 与 item.exchange_mode 列注释同口径：1=免费送 2=交换 3=低价转让 4=平台回收
const MODE_TEXT = { 1: '免费送', 2: '交换', 3: '低价转让', 4: '平台回收' }
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
    // 距离排序时后端才返回 distance_km（未公开位置 / 无坐标的物品为 undefined）
    distanceKm: item.distance_km ?? null,
    // 360° 角标：列表接口仅透出 panorama_status（views 大 JSON 不下发）
    panoramaStatus: item.panorama_status || 'none',
  }
}

function normalizeDisplayItem(item) {
  if (item && Object.prototype.hasOwnProperty.call(item, 'conditionLevel')) {
    return {
      id: item.id,
      title: item.title,
      image: item.image || FALLBACK_IMAGE,
      conditionLevel: item.conditionLevel,
      modeCode: Number(item.modeCode ?? 2),
      carbon: Number(item.carbon ?? 0),
      category_id: item.category_id ?? null,
      distanceKm: item.distanceKm ?? null,
      panoramaStatus: item.panoramaStatus || 'none',
    }
  }
  return normalizeApiItem(item)
}

/* ---------- 展示列表：仅接口真实物品（筛选/排序/分页均由服务端完成） ---------- */
const displayItems = computed(() => apiItems.value.map(normalizeDisplayItem))

/* 交换模式标签配色：按数值 code 判断 */
function modeClass(code) {
  if (Number(code) === 3) return 'mode-points'
  if (Number(code) === 1) return 'mode-free'
  if (Number(code) === 4) return 'mode-recycle'
  return 'mode-swap'
}

/* 图片加载失败：仅回填一次默认绿色占位图，避免死循环 */
function onImgError(event) {
  const img = event.target
  if (img.dataset.fb) return
  img.dataset.fb = '1'
  img.src = FALLBACK_IMAGE
}

/* 「离我最近」依赖用户位置：未设置时给出可操作的引导 */
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
    .then(() => router.push(loggedIn ? '/profile/location' : '/login?redirect=/items'))
    .catch(() => {})
}

async function load(isRetry = false) {
  loading.value = true
  loadError.value = false
  const isNearest = sortBy.value === 'distance'
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
      // 后端不可用时不再静默降级：保留真实列表并给出明确提示
      skipErrorToast: true,
    })
    // 已登录但未设置位置：后端返回 need_location，明确引导并回退到「最新发布」
    if (isNearest && data?.need_location) {
      sortBy.value = 'created_at'
      if (!isRetry) await load(true)
      guideToSetLocation()
      return
    }
    if (isNearest && data?.distance_sorted && !(data.nearby_count > 0)) {
      ElMessage.info('附近暂无已公开位置的物品，已按默认顺序展示')
    }
    apiItems.value = data.items || []
    total.value = data.total || 0
  } catch (error) {
    // 注意：HTTP 4xx 走 axios 错误拦截器，后端提示在 response.data.message
    const serverMsg = error?.response?.data?.message || error?.message || ''
    if (isNearest) {
      // 未登录（后端 400）或距离排序不可用：回退排序并重新加载
      sortBy.value = 'created_at'
      if (!isRetry) await load(true)
      if (serverMsg.includes('位置')) {
        // 需要用户去设置位置：给可操作的入口（不重复弹 toast）
        guideToSetLocation()
      } else {
        ElMessage.warning(serverMsg || '距离排序暂时不可用，已切换回最新发布')
      }
      return
    }
    // 不再用本地 mock 覆盖真实数据：仅置错误标记，保留已加载的真实列表
    loadError.value = true
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

/* ---------- AI 估价草稿预填（from=pricing） ---------- */
// 分类映射策略：拿估价的**中文分类名**去已加载的分类表里找同名项；
// 找到就用它的 id，找不到就**留空 + 明确提示**——不猜、不默认、不 fallback 到某个分类，
// 否则会把用户的物品悄悄归到错误分类下。
function applyCategoryByName(name) {
  const wanted = (name || '').trim()
  if (!wanted) return
  const hit = categories.value.find((category) => category.name === wanted)
  if (hit) {
    uploadForm.category_id = hit.id
    return
  }
  uploadForm.category_id = null
  ElMessage.warning(`分类「${wanted}」无法自动匹配，请手动选择`)
}

function applyDraft(draft) {
  if (!draft) return
  // 图片：直接接 File 引用（store 传引用，不做序列化）
  if (draft.imageFile) imageFile.value = draft.imageFile
  uploadForm.title = draft.title || ''
  uploadForm.description = draft.description || ''
  uploadForm.condition_level = Number(draft.conditionLevel) || 0
  uploadForm.original_price = Number(draft.originalPrice) || 0
  uploadForm.contact = draft.contact || ''
  applyCategoryByName(draft.categoryName)
  // 估价给了建议售价 → 默认切到「低价转让」并预填转让价（用户可再改成免费送 / 交换）
  if (draft.price) {
    uploadForm.exchange_mode = 3
    uploadForm.price = Number(draft.price)
  }
}

// 弹窗关闭（含取消、点遮罩）：清掉草稿，避免下次进入被旧估价数据污染。
// 刻意只清草稿、不重置表单——保留用户已填内容，与改动前的行为一致。
function onDialogClosed() {
  if (publishDraft.draft) publishDraft.clearDraft()
}

// 预览图与 objectURL 的生命周期现在由 ImageUploader 自己管（含移除图片按钮），
// 这里只负责清空选中文件，提交前校验读的仍是 imageFile
function clearImage() {
  imageFile.value = null
}

function resetUploadForm() {
  Object.assign(uploadForm, {
    title: '',
    description: '',
    category_id: null,
    expected_exchange: '',
    contact: '',
    exchange_mode: 1,
    price: 0.01,
    condition_level: 0,
    original_price: 0,
  })
  Object.assign(recycleForm, {
    pickup_method: 1,
    pickup_address: '',
  })
  estimatePoints.value = 0
  clearImage()
}

async function submitUpload() {
  // 前置校验：与后端 create_item 保持一致（trim 后判空 + 长度上限 + 图片必填）
  const title = uploadForm.title.trim()
  const description = uploadForm.description.trim()
  const contact = uploadForm.contact.trim()
  if (!title || !description || !contact || !uploadForm.category_id) {
    ElMessage.warning('请填写物品名称、描述、分类和联系方式')
    return
  }
  if (title.length > 50) {
    ElMessage.warning('物品名称不能超过 50 字')
    return
  }
  if (description.length > 500) {
    ElMessage.warning('物品描述不能超过 500 字')
    return
  }
  if (contact.length > 100) {
    ElMessage.warning('联系方式不能超过 100 字')
    return
  }
  // 交易方式与转让价：与后端 MIN_PRICE / MAX_PRICE 口径一致
  const mode = Number(uploadForm.exchange_mode) || 1
  if (mode === 3) {
    const price = Number(uploadForm.price)
    if (!price || price < MIN_PRICE || price > MAX_PRICE) {
      ElMessage.warning(`转让价需在 ${MIN_PRICE} - ${MAX_PRICE} 元之间`)
      return
    }
  }
  // 平台回收：成色必填（估价依据）、上门取件必填地址（与后端口径一致）
  if (mode === 4) {
    const condition = Number(uploadForm.condition_level) || 0
    if (condition < 1 || condition > 5) {
      ElMessage.warning('请选择物品成色，平台将按成色估价')
      return
    }
    if (Number(recycleForm.pickup_method) === 2) {
      const address = recycleForm.pickup_address.trim()
      if (!address) {
        ElMessage.warning('选择上门取件时请填写取件地址')
        return
      }
      if (address.length > 200) {
        ElMessage.warning('取件地址不能超过 200 个字符')
        return
      }
    }
  }
  if (!imageFile.value) {
    ElMessage.warning('请至少上传 1 张物品图片')
    return
  }

  const formData = new FormData()
  formData.append('title', title)
  formData.append('description', description)
  formData.append('category_id', String(uploadForm.category_id))
  formData.append('expected_exchange', mode === 2 ? uploadForm.expected_exchange : '')
  formData.append('contact', contact)
  formData.append('exchange_mode', String(mode))
  formData.append('price', mode === 3 ? String(uploadForm.price) : '0')
  formData.append('condition_level', String(uploadForm.condition_level || 0))
  formData.append('original_price', String(uploadForm.original_price || 0))
  formData.append('image', imageFile.value)

  uploading.value = true
  try {
    const created = await uploadItem(formData)
    if (mode === 4) {
      await submitRecycleAfterPublish(created?.id)
      return
    }
    // 提交后进入待审核（status=4），审核通过前不出现在列表中，故不刷新列表
    ElMessage.success('提交成功，等待审核通过后展示')
    ElMessage.info('360° 效果生成中，完成后可在物品详情页查看')
    uploadVisible.value = false
    publishDraft.clearDraft()
    resetUploadForm()
  } catch (error) {
    ElMessage.error(error.message || '物品上传失败，请稍后重试')
  } finally {
    uploading.value = false
  }
}

/* ---------- 平台回收：发布成功后立即提交回收（两次调用非原子的兜底，见风险 R2） ---------- */
async function submitRecycleAfterPublish(itemId) {
  if (!itemId) {
    // 理论不可达（后端必回 id）：兜底提示，不让用户以为回收已成功
    ElMessage.error('物品已发布，但回收提交失败：未取到物品编号，请到「我的物品」重新操作')
    uploadVisible.value = false
    return
  }
  try {
    const result = await submitRecycle(itemId, {
      pickup_method: Number(recycleForm.pickup_method) || 1,
      pickup_address: recycleForm.pickup_address.trim() || null,
    }, { skipErrorToast: true })
    ElMessage.success(`已获得 ${result?.points_reward ?? estimatePoints.value} 积分`)
    ElMessage.info('平台将安排取件，可在「我的回收单」查看进度')
    uploadVisible.value = false
    publishDraft.clearDraft()
    resetUploadForm()
  } catch (error) {
    const serverMsg = error?.response?.data?.message || error?.message || ''
    uploadVisible.value = false
    if (serverMsg.includes('已在回收流程中')) {
      // 重复提交：物品其实已经进回收流程了，引导去查看而不是盲目重试
      ElMessage.warning('该物品已在回收流程中，请到「我的回收单」查看')
    } else {
      // 物品已建、回收未成：明确告知两条路（去我的物品重试 / 联系客服），不做静默重试
      ElMessage.error(`物品已发布，但回收提交失败：${serverMsg || '请稍后重试'}`)
      ElMessage.info('可稍后到「我的物品」找到该物品重新提交回收')
    }
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

// 分类加载抽成可 await 的函数：估价草稿里的「中文分类名 → 分类ID」映射
// 必须在分类列表到位之后才能做，否则必然匹配不上而误报「无法自动匹配」。
async function loadCategories() {
  try {
    const data = await getCategories({ skipErrorToast: true })
    categories.value = (data && data.length ? data : staticCategories).map((item) => ({
      id: item.id,
      name: item.name,
    }))
  } catch {
    categories.value = staticCategories.map((item) => ({
      id: item.id,
      name: item.name,
    }))
  }
}

onMounted(async () => {
  // 支持首页分类入口携带的 ?category_id=xxx
  const queryCategory = Number(route.query.category_id)
  if (queryCategory) filters.category_id = queryCategory

  // 从 AI 估价页跳转（/items?from=pricing&action=publish）：
  // 草稿里的「中文分类名 → 分类ID」映射依赖分类列表，因此这条路要等分类到位；
  // 普通访问则保持「分类与物品加载互不阻塞」，避免单点失败导致整页 Network Error。
  const fromPricing = route.query.from === 'pricing'
  if (fromPricing) {
    await loadCategories()
  } else {
    loadCategories()
  }
  load()

  if (!fromPricing) return
  const draft = publishDraft.draft
  if (!draft) return
  applyDraft(draft)
  // 带 action=publish 时自动打开发布弹窗（用户仍可修改 / 取消）
  if (route.query.action === 'publish') openUploadDialog()
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

.form-control {
  width: 100%;
}

/* 交易方式三选：铺满并左对齐，助老/高对比度下由全局按钮样式接管尺寸 */
.mode-group {
  width: 100%;
}

.field-tip {
  margin: 6px 0 0;
  font-size: 12.5px;
  color: var(--text-secondary);
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

/* 360° 角标：与首页 .badge-360 同款（右下角，绿底白字） */
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

/* 平台回收标签：紫色系，与免费送/交换/转让三色区分开 */
.mode-recycle {
  background: #ede7f6;
  color: #6a4fa3;
}

/* 平台估价展示盒：估价数字一眼可见（服务端真源，前端只展示） */
.estimate-box {
  display: flex;
  align-items: baseline;
  gap: 6px;
  width: 100%;
  padding: 12px 16px;
  background: #f4fbf6;
  border: 1px dashed rgba(76, 175, 80, 0.45);
  border-radius: 12px;
}

.estimate-num {
  font-size: 26px;
  font-weight: 800;
  color: #2e7d32;
  font-variant-numeric: tabular-nums;
}

.estimate-unit {
  font-size: 14px;
  font-weight: 600;
  color: #2e7d32;
}

.estimate-note {
  margin-left: auto;
  font-size: 12.5px;
  color: var(--text-secondary);
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

/* ---------- 双 Tab（闲 / 新） ----------
   el-tabs 的内部 DOM 由 Element Plus 渲染，不带本组件的 scoped 属性，
   必须用 :deep() 才能命中（R1）。 */
.explore-tabs :deep(.el-tabs__header) {
  /* 顶部间距由 .heading-row 里上传按钮的 margin-bottom 提供，这里不再叠加 */
  margin: 0;
}

.explore-tabs :deep(.el-tabs__item) {
  height: auto;
  padding: 4px 2px 10px;
}

/* 单选/双击都可命中；助老模式下由非 scoped 段补到 60px */
.explore-tabs :deep(.el-tabs__item + .el-tabs__item) {
  margin-left: 26px;
}

.tab-main {
  font-size: 17px;
  font-weight: 700;
  line-height: 1.2;
}

/* 副标题继承 tab 的主色（选中变绿），只压低不透明度，避免两套配色打架 */
.tab-sub {
  margin-left: 6px;
  font-size: 12.5px;
  font-weight: 600;
  opacity: 0.7;
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

  .explore-tabs :deep(.el-tabs__item + .el-tabs__item) {
    margin-left: 18px;
  }

  .tab-sub {
    display: none;
  }
}

/* ============================================================
   移动端（≤767px）：保持 2 列，但压缩卡片高度与内边距
   为什么不直接改单列：二手浏览是「扫图」场景，2 列一屏能看到
   4–6 个物品，比单列（1 屏 2 个）效率高得多。只在 ≤360px
   （iPhone SE 一代级别）才降为单列，避免卡片被压到 158px 以下。
   ============================================================ */
@media (max-width: 767px) {
  .item-card {
    margin-bottom: 12px;
    border-radius: 14px;
  }

  /* 触屏没有 hover：去掉上浮与图片放大，否则点击瞬间卡片会"跳一下" */
  .item-card:hover {
    transform: none;
    box-shadow: none;
  }

  .item-card:hover .item-img img {
    transform: none;
  }

  .item-img {
    height: 130px;
  }

  .item-body {
    padding: 10px 12px 12px;
  }

  .item-name {
    font-size: 14px;
  }

  .item-tags {
    margin: 8px 0 10px;
  }

  .filters {
    margin: 18px 0 16px;
    padding: 12px;
    gap: 10px;
  }

  .filters .el-input,
  .filters .el-select {
    flex: 1 1 100%;
    width: 100%;
    min-width: 0;
  }

  /* 三个排序按钮在手机上排不下：改为横向滚动，不换行（换行会把筛选区顶高） */
  .sort-row {
    margin-bottom: 16px;
    padding: 10px 12px;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
  }

  .sort-row::-webkit-scrollbar {
    display: none;
  }

  .sort-row :deep(.el-radio-group) {
    flex-wrap: nowrap;
  }

  .upload-trigger {
    width: 100%;
  }
}

/* 超窄屏：降为单列 */
@media (max-width: 360px) {
  .explore-page :deep(.el-col) {
    max-width: 100%;
    flex: 0 0 100%;
  }

  .item-img {
    height: 168px;
  }
}
</style>

<!-- ============================================================
     非 scoped：根级主题选择器（html.mode-elderly / html.theme-high-contrast）
     在 scoped 下不生效，必须写在这里，并以 .explore-page 前缀隔离。
     ============================================================ -->
<style>
/* ---------- 高对比度：黑底白字 ---------- */
html.theme-high-contrast .explore-page .el-tabs__item {
  /* global.css 已保证文字为白；这里补上未选中项的可读性与分隔线 */
  color: #ffffff;
  opacity: 0.75;
}

html.theme-high-contrast .explore-page .el-tabs__item.is-active {
  color: #4ade80;
  opacity: 1;
}

html.theme-high-contrast .explore-page .el-tabs__nav-wrap::after {
  background-color: #ffffff;
}

html.theme-high-contrast .explore-page .el-tabs__active-bar {
  background: #4ade80;
}

/* ---------- 助老模式：点击目标 ≥60px、字号放大 ---------- */
html.mode-elderly .explore-page .explore-tabs .el-tabs__item {
  min-height: 60px;
  padding: 12px 4px;
}

html.mode-elderly .explore-page .explore-tabs .el-tabs__item + .el-tabs__item {
  margin-left: 30px;
}

html.mode-elderly .explore-page .explore-tabs .tab-main {
  font-size: 22px;
}

html.mode-elderly .explore-page .explore-tabs .tab-sub {
  font-size: 16px;
}
</style>
