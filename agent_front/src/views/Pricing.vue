<template>
  <section class="page">
    <div class="eyebrow">AI 智能定价</div>
    <h1 class="page-title">
      给物品一个<br />
      <span class="gradient-text">有依据的价格。</span>
    </h1>

    <div class="pricing-layout">
      <!-- 表单 -->
      <el-card class="form-card" shadow="never">
        <h2 class="panel-title">输入物品信息</h2>
        <el-form label-position="top" @submit.prevent="estimate">
          <el-form-item label="物品名称">
            <el-input v-model="form.item_name" placeholder="例如：九成新儿童自行车" />
          </el-form-item>

          <el-form-item label="物品描述（可选）">
            <el-input
              v-model="form.description"
              type="textarea"
              :rows="3"
              placeholder="例如：自行车有轻微划痕，后座可拆卸，适合孩子使用"
            />
          </el-form-item>

          <el-form-item label="物品分类">
            <div class="category-picker">
              <div class="category-tags" role="group" aria-label="物品分类选择">
                <button
                  v-for="name in PRESET_CATEGORIES"
                  :key="name"
                  type="button"
                  class="category-tag"
                  :class="{ 'is-active': form.item_category === name }"
                  :aria-pressed="form.item_category === name"
                  @click="toggleCategory(name)"
                >
                  {{ name }}
                </button>
                <!-- 「其他」= 自定义分类：点击展开小输入框，值同样写回 form.item_category -->
                <button
                  type="button"
                  class="category-tag"
                  :class="{ 'is-active': showCustom }"
                  :aria-pressed="showCustom"
                  @click="toggleOther"
                >
                  其他
                </button>
              </div>

              <el-input
                v-show="showCustom"
                ref="customCategoryInput"
                v-model="form.item_category"
                class="category-custom"
                maxlength="20"
                show-word-limit
                placeholder="请输入自定义分类，例如：乐器"
              />
            </div>
          </el-form-item>

          <el-form-item label="物品图片（可选）">
            <!-- 公共上传组件：图片不再直接进估价接口，而是先识别、回填、由用户确认 -->
            <!-- 估价页不需要拖拽落区：显式关闭（allowDrag 默认是 true） -->
            <ImageUploader
              v-model="imageFile"
              mode="pricing"
              preview-alt="待估价图片预览"
              :max-size="MAX_IMAGE_SIZE"
              :allow-drag="false"
            >
              <template #status>
                <p v-if="recognitionState === 'done'" class="recog-status done">
                  已识别，请确认信息后再次点击估价
                  <el-button link type="primary" size="small" @click="resetRecognition">重新识别</el-button>
                </p>
                <p v-else-if="recognitionState === 'failed'" class="recog-status failed">
                  自动识别失败，请手动填写物品信息
                  <el-button link type="primary" size="small" @click="resetRecognition">重试识别</el-button>
                </p>
              </template>
            </ImageUploader>
          </el-form-item>

          <el-form-item label="成色等级">
            <el-rate
              v-model="form.condition_level"
              :texts="conditionTexts"
              show-text
            />
          </el-form-item>

          <el-form-item label="原价（元）">
            <el-input-number
              v-model="form.original_price"
              :min="1"
              :precision="2"
              controls-position="right"
            />
          </el-form-item>

          <el-button
            type="primary"
            native-type="submit"
            :loading="loading"
            class="full"
          >
            {{ estimateLabel }}
          </el-button>
        </el-form>
      </el-card>

      <!-- 结果与历史 -->
      <div class="result-area">
        <div v-if="result" class="result glass-card">
          <div class="result-banner">
            <div class="eyebrow">建议售价</div>
            <div class="price">¥ {{ result.suggested_price }}</div>
            <span class="rate-chip chip">折旧率 {{ (Number(result.depreciation_rate) * 100).toFixed(1) }}%</span>
          </div>
          <p class="reason muted">{{ result.pricing_reason }}</p>

          <!-- 一键发布：把「图片 + 已填信息 + 建议售价」通过 pinia 草稿带到发布弹窗 -->
          <div class="result-actions">
            <el-button type="primary" class="publish-btn" @click="publishWithPrice">
              用这个价格发布
            </el-button>
            <span class="publish-tip muted">
              将带着图片和这份估价结果去发布，价格与交易方式都还能再改
            </span>
          </div>
        </div>

        <div v-else class="empty-result glass-card">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 2v4M12 18v4M2 12h4M18 12h4"/>
            <circle cx="12" cy="12" r="4"/>
          </svg>
          <p>填写信息，获取一份透明的定价建议</p>
        </div>

        <div class="history" v-if="history.length">
          <h2 class="panel-title">最近定价记录</h2>
          <div v-for="record in history" :key="record.id" class="history-row">
            <span class="history-name">{{ record.item_name }}</span>
            <strong>¥ {{ record.suggested_price }}</strong>
            <small class="muted">{{ formatTime(record.created_at) }}</small>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import ImageUploader from '../components/ImageUploader.vue'
import { usePublishDraftStore } from '../store/publishDraft'
import { pricing, pricingHistory, recognizeFile } from '../api/ai'

// 与后端 app/api/v1/ai.py 的 MAX_IMAGE_SIZE 保持一致
const MAX_IMAGE_SIZE = 5 * 1024 * 1024

const router = useRouter()
const publishDraft = usePublishDraftStore()

const form = reactive({
  item_name: '',
  description: '',
  item_category: '',
  condition_level: 4,
  original_price: 500,
})

// 预设分类：仍写入 form.item_category（字符串），后端 app/schemas/pricing.py 的字段名与校验都不变
const PRESET_CATEGORIES = ['数码电子', '家居家具', '服饰鞋包', '图书文具', '母婴玩具', '运动户外', '家电厨具']

// 「其他」自定义分类：展开小输入框，值同样落在 form.item_category
const showCustom = ref(false)
const customCategoryInput = ref(null)

const imageFile = ref(null)
// idle：还没识别过 / done：识别成功待用户确认 / failed：识别失败，改为手工填写
const recognitionState = ref('idle')
// 记录「已经为哪个文件跑过识别」，避免同一张图反复触发识别
let recognizedFile = null

const conditionTexts = computed(() => ['较差', '一般', '良好', '很新', '全新'])

const result = ref(null)
const history = ref([])
const loading = ref(false)
// '' / 'recognizing' / 'pricing'：两段式 loading 文案，避免长耗时被误认为卡死
const loadingPhase = ref('')

const estimateLabel = computed(() => {
  if (!loading.value) return '开始 AI 估价'
  return loadingPhase.value === 'recognizing' ? '正在识别物品…' : '正在生成估价…'
})

// 换图后必须重新识别（第一次识别失败也算「已尝试」，由 reroll 按钮显式重试）
watch(imageFile, (file) => {
  if (file !== recognizedFile) recognitionState.value = 'idle'
})

function formatTime(value) {
  if (!value) return ''
  return String(value).replace('T', ' ').slice(0, 16)
}

/* ---------- 分类标签选择 ---------- */
// 点击预设标签：未选中 → 选中；已选中 → 取消（清空）
function toggleCategory(name) {
  if (form.item_category === name) {
    form.item_category = ''
    return
  }
  form.item_category = name
  showCustom.value = false
}

// 点击「其他」：展开/收起自定义输入框；收起时清掉自定义值
function toggleOther() {
  if (showCustom.value) {
    showCustom.value = false
    if (!PRESET_CATEGORIES.includes(form.item_category)) form.item_category = ''
    return
  }
  if (PRESET_CATEGORIES.includes(form.item_category)) form.item_category = ''
  showCustom.value = true
  nextTick(() => customCategoryInput.value?.focus?.())
}

// AI 识别回填的分类可能不在预设列表内（如「乐器」）→ 自动切到自定义模式并回显，避免值被隐藏
watch(
  () => form.item_category,
  (val) => {
    if (val && !PRESET_CATEGORIES.includes(val)) showCustom.value = true
  },
)

async function loadHistory() {
  try {
    const data = await pricingHistory({ page: 1, size: 5 })
    history.value = data.items || []
  } catch {
    history.value = []
  }
}

function canPrice() {
  return Boolean(form.item_name?.trim() && form.item_category?.trim() && form.original_price)
}

// 只回填用户留空的字段：已填的内容是用户意图，不能被 AI 覆盖
function fillFromRecognition(recognition) {
  if (!recognition) return
  if (recognition.name && !form.item_name.trim()) form.item_name = recognition.name
  if (recognition.category && !form.item_category.trim()) form.item_category = recognition.category
  if (recognition.description && !form.description.trim()) form.description = recognition.description
  if (recognition.condition_level && form.condition_level === 4) {
    form.condition_level = recognition.condition_level
  }
}

// 第一步：识别 + 回填。**不自动估价**——留出时间让用户修正 AI 认错的信息
async function runRecognition() {
  loading.value = true
  loadingPhase.value = 'recognizing'
  try {
    const recognition = await recognizeFile(imageFile.value, { skipErrorToast: true })
    // 后端在「模型未配置 / 调用失败」时不会报错，而是降级为 200 + engine=mock 的演示结果。
    // 演示数据（「演示识别结果」/「其他闲置」）填进表单会直接误导估价，因此按识别失败处理。
    if (!recognition || recognition.engine === 'mock') {
      failRecognition()
      return
    }
    fillFromRecognition(recognition)
    recognizedFile = imageFile.value
    recognitionState.value = 'done'
    ElMessage.success('已识别，请确认信息后再次点击估价')
  } catch {
    // 识别失败不能让用户卡在「无法估价」：标记为 failed，下一次点击直接走纯 JSON 估价
    failRecognition()
  } finally {
    loading.value = false
    loadingPhase.value = ''
  }
}

// 识别不可用（网络/额度/超时/演示模式）：保持表单可编辑，用户手填后仍可正常估价
function failRecognition() {
  recognizedFile = imageFile.value
  recognitionState.value = 'failed'
  ElMessage.warning('自动识别失败，请手动填写物品信息')
}

// 第二步：纯 JSON 估价（图片不参与，接口本身也只接受 JSON）
async function runPricing() {
  loading.value = true
  loadingPhase.value = 'pricing'
  try {
    result.value = await pricing({ ...form })
    loadHistory()
  } catch {
    // 错误提示已由请求拦截器处理
  } finally {
    loading.value = false
    loadingPhase.value = ''
  }
}

function resetRecognition() {
  recognizedFile = null
  recognitionState.value = 'idle'
}

async function estimate() {
  // 有图且还没识别过：先识别。此时允许名称/分类为空——识别就是为了把它们填上
  if (imageFile.value && recognitionState.value === 'idle') {
    await runRecognition()
    return
  }

  // 校验失败必须有用户可见的提示，不能静默 return（否则点击「开始 AI 估价」像是没反应）
  if (!canPrice()) {
    ElMessage.warning('请填写物品名称、物品分类和原价')
    return
  }

  await runPricing()
}

/* ---------- 用这个价格发布 ---------- */
// 把估价结果 + 已填表单 + 图片 File 一起写进 pinia 草稿，跳到物品列表页的发布弹窗。
// 为什么用 store 而不是 sessionStorage：草稿含 File 对象，无法 JSON 序列化。
function publishWithPrice() {
  if (!result.value) return
  publishDraft.setDraft({
    source: 'pricing',
    imageFile: imageFile.value,
    title: form.item_name.trim(),
    description: form.description.trim(),
    // 分类传**中文名**：发布页再按名称映射 category_id，查不到就提示用户手动选
    categoryName: form.item_category.trim(),
    conditionLevel: form.condition_level,
    originalPrice: form.original_price,
    price: Number(result.value.suggested_price),
  })
  router.push({ path: '/items', query: { from: 'pricing', action: 'publish' } })
}

onMounted(loadHistory)
</script>

<style scoped>
.pricing-layout {
  display: grid;
  grid-template-columns: 390px 1fr;
  gap: 24px;
  margin-top: 36px;
}

.panel-title {
  font-size: 19px;
  margin-bottom: 24px;
}

.full {
  width: 100%;
}

/* ---------- 分类标签选择器 ---------- */
.category-picker {
  width: 100%;
}

.category-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* 未选中：浅灰底 + 深色字 + 灰边框；选中：品牌绿底白字 */
.category-tag {
  min-height: 36px;
  padding: 8px 16px;
  border-radius: 999px;
  border: 1px solid rgba(35, 66, 54, 0.18);
  background: #f3f4f6;
  color: #2f3a35;
  font-size: 14px;
  font-weight: 500;
  line-height: 1;
  cursor: pointer;
  transition: transform 0.15s ease, background 0.15s ease, border-color 0.15s ease,
    color 0.15s ease;
}

.category-tag:hover {
  transform: translateY(-1px);
  border-color: var(--green-primary);
}

.category-tag:focus-visible {
  outline: 3px solid var(--green-primary);
  outline-offset: 2px;
}

.category-tag.is-active {
  background: var(--green-primary);
  border-color: var(--green-primary);
  color: #fff;
}

.category-tag.is-active:hover {
  background: var(--green-hover);
  border-color: var(--green-hover);
}

.category-custom {
  margin-top: 10px;
}

/* 识别状态行：让用户明确知道「现在该再点一次估价」 */
.recog-status {
  margin: 0;
  padding: 8px 12px;
  border-radius: var(--r-sm);
  font-size: 13px;
  line-height: 1.7;
}

.recog-status.done {
  background: var(--green-softer);
  color: var(--green-primary);
}

.recog-status.failed {
  background: var(--peach-soft, #fff7ed);
  color: var(--peach-deep, #c2410c);
}

.result-area {
  min-height: 400px;
}

.result {
  overflow: hidden;
}

.result-banner {
  padding: 32px 34px 26px;
  background: linear-gradient(120deg, var(--teal-soft), var(--green-softer));
}

.price {
  font-size: 56px;
  font-weight: 700;
  color: var(--teal-deep);
  margin: 12px 0 14px;
}

.rate-chip {
  background: #fff;
}

.reason {
  padding: 24px 34px 30px;
  margin: 0;
  line-height: 1.8;
  font-size: 14.5px;
}

/* 一键发布：结果卡底部操作区 */
.result-actions {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  padding: 0 34px 30px;
  margin-top: -10px;
}

.publish-btn {
  box-shadow: var(--shadow-btn);
}

.publish-tip {
  font-size: 12.5px;
  line-height: 1.6;
}

.empty-result {
  min-height: 260px;
  display: grid;
  place-items: center;
  text-align: center;
  padding: 30px;
}

.empty-result svg {
  width: 54px;
  height: 54px;
  color: var(--teal);
  opacity: 0.6;
  margin-bottom: 14px;
}

.empty-result p {
  color: var(--text-secondary);
  font-size: 14px;
}

.history {
  margin-top: 30px;
}

.history-row {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 18px;
  align-items: center;
  padding: 13px 2px;
  border-bottom: 1px solid var(--border-soft);
  font-size: 13.5px;
}

.history-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-row strong {
  color: var(--teal-deep);
}

.history-row small {
  font-size: 12px;
}

@media (max-width: 750px) {
  .pricing-layout {
    grid-template-columns: 1fr;
  }

  .price {
    font-size: 44px;
  }
}
</style>

<!-- 非 scoped：根节点上的 html.mode-elderly / html.theme-high-contrast 需要全局选择器才能命中 -->
<style>
/* 助老模式：分类标签最小高度 60px、字号放大（沿用 .el-button 在助老模式下的 60px 点击目标口径） */
html.mode-elderly .category-tag {
  min-height: 60px;
  padding: 14px 24px;
  font-size: 18px;
}

/* 高对比度：项目的高对比度是「黑底白字」主题（见 global.css html.theme-high-contrast），
   因此未选中用黑底白字白描边，选中用「品牌绿底黑字」高亮（与 .el-button--primary 同款处理）。 */
html.theme-high-contrast .category-tag {
  background: #000;
  color: #fff;
  border: 2px solid #fff;
}

html.theme-high-contrast .category-tag:hover {
  background: #000;
  border-color: #4ade80;
  transform: none;
}

html.theme-high-contrast .category-tag.is-active {
  background: #4ade80;
  border-color: #4ade80;
  color: #000;
  font-weight: 700;
}

html.theme-high-contrast .category-tag:focus-visible {
  outline: 3px solid #ffd400;
  outline-offset: 2px;
}
</style>
