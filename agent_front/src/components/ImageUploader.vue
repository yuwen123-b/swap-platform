<!--
  通用图片选择组件（智能定价页 / 物品识别页共用）
  ---------------------------------------------------------------
  职责：把「选一张图」这件事做好 —— 文件选择 / 拍照 / 拖拽 / 校验 / 预览。
  **不做上传**：什么时候提交、提交到哪个接口，由页面自己决定。

  v-model 绑定的是 File 对象（不是 URL）：
  各页面都是「选完文件后由页面自己发 FormData」，没有独立的上传步骤，
  因此组件不产出 URL（定价接口只收 JSON、识别接口返回的 image_url 需重新签名，
  两者都不适合当作组件的输出）。

  拖拽落区由 allowDrag 单独控制（默认开）：
  物品识别页 / 发布物品页开启，智能定价页显式传 :allow-drag="false" 关闭
  —— 这里**不再**用 mode 卡拖拽，避免"传了 allow-drag 却不生效"的隐式规则。

  降级策略：
  1. 初始化检测 navigator.mediaDevices?.getUserMedia
     → 不存在（http 非 localhost / 老浏览器）直接标记为降级，「拍照上传」按钮
       改为触发 input[capture]，且**只在第一次点击时提示一次原因**；
  2. 运行时失败（权限拒绝 / 无设备 / 被占用）由 CameraCaptureDialog 分类提示，
     需要落到文件选择的场景通过 @fallback 回到本组件的隐藏 input。
-->
<template>
  <div class="image-uploader">
    <!-- 拖拽落区：由 allowDrag 决定（识别页 / 发布页开启，定价页显式关闭） -->
    <div
      v-if="showDrag"
      class="drop-zone"
      :class="{ active: dragActive }"
      @click="pickFile"
      @dragover.prevent="onDragOver"
      @dragleave.prevent="onDragLeave"
      @drop.prevent="onDrop"
    >
      <img v-if="previewUrl" class="drop-preview" :src="previewUrl" :alt="previewAlt" />
      <template v-else>
        <svg class="drop-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="17 8 12 3 7 8" />
          <line x1="12" y1="3" x2="12" y2="15" />
        </svg>
        <p class="drop-tip">拖拽图片到这里，或 <em>点击选择</em></p>
        <small class="drop-sub">{{ hintText }}</small>
      </template>
    </div>

    <!-- 两个入口按钮（保持与截图一致的并排布局） -->
    <div class="picker-row">
      <button type="button" class="picker-btn" @click="pickFile">图片上传</button>
      <button type="button" class="picker-btn accent" @click="openCamera">拍照上传</button>
    </div>

    <!-- 非拖拽模式的预览 -->
    <div v-if="!showDrag && previewUrl" class="preview-wrap">
      <img :src="previewUrl" :alt="previewAlt" />
    </div>

    <div v-if="previewUrl" class="uploader-foot">
      <el-button link type="danger" size="small" @click="clear">移除图片</el-button>
      <span class="foot-meta">{{ fileName }} · {{ fileSizeText }}</span>
    </div>

    <!-- 页面自定义状态行（如定价页的「已识别/识别失败」提示） -->
    <slot name="status" />

    <!-- 隐藏的原生输入：文件选择 + 拍照降级（capture 让移动端优先调起后置相机） -->
    <input
      ref="fileInput"
      class="file-proxy"
      type="file"
      :accept="accept"
      @change="handleInputChange"
    />
    <input
      ref="cameraInput"
      class="file-proxy"
      type="file"
      :accept="accept"
      capture="environment"
      @change="handleInputChange"
    />

    <CameraCaptureDialog
      v-model="cameraVisible"
      :max-size="maxSize"
      @captured="handleCaptured"
      @fallback="handleCameraFallback"
    />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import CameraCaptureDialog from './CameraCaptureDialog.vue'

const props = defineProps({
  // 选中的文件（v-model）
  modelValue: { type: Object, default: null },
  // 语义标记：'pricing' 智能定价 / 'identify' 物品识别 / 'publish' 发布物品
  // 注意：不参与任何逻辑判断（拖拽只看 allowDrag），仅供调用方自述与排查用
  mode: { type: String, default: 'pricing' },
  // 单文件大小上限
  maxSize: { type: Number, default: 5 * 1024 * 1024 },
  // 是否渲染拖拽落区：**只由本 prop 决定**（初版被 mode === 'identify' 额外卡死，
  // 导致别的页面传 allow-drag 也不生效）。要关拖拽请显式传 :allow-drag="false"。
  allowDrag: { type: Boolean, default: true },
  // 是否展示预览
  showPreview: { type: Boolean, default: true },
  accept: { type: String, default: 'image/*' },
  previewAlt: { type: String, default: '已选图片预览' },
})

const emit = defineEmits(['update:modelValue', 'selected'])

const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif']
const ALLOWED_TEXT = 'jpg/png/webp/gif'
// 统一按 5MB 文本框呈现，与后端 MAX_IMAGE_SIZE 对齐
const maxSizeText = computed(() => `${Math.round(props.maxSize / 1024 / 1024)}MB`)
const hintText = computed(() => `支持 ${ALLOWED_TEXT}，最大 ${maxSizeText.value}`)

const fileInput = ref(null)
const cameraInput = ref(null)
const cameraVisible = ref(false)
const dragActive = ref(false)
const previewUrl = ref('')

// 初始化检测：无 mediaDevices 说明处于非安全上下文（http 非 localhost）或老浏览器。
// 这是环境能力，启动时判一次即可，不必每次点击都探测。
const cameraSupported = typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia
const showDrag = computed(() => props.allowDrag)
// 降级提示只在首次点击出现一次，避免反复弹窗打扰
const degradedWarned = ref(false)

watch(
  () => props.modelValue,
  (file) => {
    if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = file ? URL.createObjectURL(file) : ''
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
})

const fileName = computed(() => props.modelValue?.name || '已选图片')
const fileSizeText = computed(() => {
  const size = props.modelValue?.size || 0
  if (!size) return ''
  return size >= 1024 * 1024 ? `${(size / 1024 / 1024).toFixed(2)}MB` : `${Math.round(size / 1024)}KB`
})

function pickFile() {
  fileInput.value?.click()
}

function openCamera() {
  if (!cameraSupported) {
    if (!degradedWarned.value) {
      degradedWarned.value = true
      ElMessage.warning('当前环境不支持直接调用摄像头，已切换为文件选择')
    }
    cameraInput.value?.click()
    return
  }
  cameraVisible.value = true
}

// 相机组件要求降级（无设备 / 未知错误 / 非安全上下文）：接管为文件选择。
// message 为空表示弹窗内部已经提示过，这里不再重复弹第二条。
function handleCameraFallback(message) {
  if (message) ElMessage.warning(message)
  cameraInput.value?.click()
}

function handleInputChange(event) {
  const file = event.target.files?.[0]
  // 先复位，否则连续选同一张图不会再触发 change
  event.target.value = ''
  if (!file) return
  acceptFile(file)
}

function handleCaptured(file) {
  acceptFile(file)
}

function onDragOver() {
  dragActive.value = true
}

function onDragLeave() {
  dragActive.value = false
}

function onDrop(event) {
  dragActive.value = false
  const file = event.dataTransfer?.files?.[0]
  if (!file) return
  acceptFile(file)
}

function acceptFile(file) {
  if (!ALLOWED_TYPES.includes(file.type)) {
    ElMessage.warning(`仅支持 ${ALLOWED_TEXT} 格式图片`)
    return
  }
  if (file.size > props.maxSize) {
    ElMessage.warning(`图片大小不能超过 ${maxSizeText.value}`)
    return
  }
  emit('update:modelValue', file)
  emit('selected', file)
}

function clear() {
  emit('update:modelValue', null)
  emit('selected', null)
  if (fileInput.value) fileInput.value.value = ''
  if (cameraInput.value) cameraInput.value.value = ''
}
</script>

<style scoped>
.image-uploader {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
}

/* 隐藏但可被 .click() 触发（display:none 在部分旧内核上无法程序化点击） */
.file-proxy {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
  pointer-events: none;
}

.picker-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.picker-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 120px;
  min-height: 44px;
  padding: 10px 16px;
  border: 1px solid var(--border-soft);
  border-radius: 12px;
  background: var(--green-softer);
  color: var(--green-primary);
  font-weight: 600;
  font-size: 15px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.picker-btn:hover {
  border-color: var(--green-primary);
  background: rgba(76, 175, 80, 0.08);
}

.picker-btn.accent {
  background: linear-gradient(135deg, #eafaf0, #ecfdf5);
}

.drop-zone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 28px 18px;
  border: 1px dashed var(--border-soft);
  border-radius: var(--r-lg);
  background: var(--green-softer);
  cursor: pointer;
  transition: border-color 0.2s ease, background 0.2s ease;
}

.drop-zone:hover,
.drop-zone.active {
  border-color: var(--green-primary);
  background: rgba(76, 175, 80, 0.08);
}

.drop-icon {
  width: 38px;
  height: 38px;
  color: var(--green-primary);
  opacity: 0.7;
}

.drop-tip {
  margin: 0;
  font-size: 14px;
  color: var(--text-primary);
}

.drop-tip em {
  color: var(--green-primary);
  font-style: normal;
  font-weight: 600;
}

.drop-sub {
  font-size: 12px;
  color: var(--text-secondary);
}

.drop-preview {
  max-width: 100%;
  max-height: 260px;
  border-radius: 12px;
  object-fit: contain;
}

.preview-wrap {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid var(--border-soft);
  border-radius: var(--r-sm);
  background: var(--el-bg-color, #fff);
}

.preview-wrap img {
  width: 120px;
  height: 90px;
  object-fit: cover;
  border-radius: 10px;
  border: 1px solid var(--border-soft);
}

.uploader-foot {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.foot-meta {
  font-size: 12px;
  color: var(--text-secondary);
}
</style>

<!-- ============================================================
     助老模式 / 高对比度适配
     必须非 scoped——需要命中 html 根级选择器（与 ItemDetail.vue 约定一致）
     ============================================================ -->
<style>
html.mode-elderly .image-uploader .picker-btn {
  min-height: 60px;
  font-size: 18px;
  padding: 0 26px;
}

html.mode-elderly .image-uploader .drop-zone {
  padding: 36px 20px;
}

html.mode-elderly .image-uploader .drop-tip {
  font-size: 18px;
}

html.mode-elderly .image-uploader .drop-sub,
html.mode-elderly .image-uploader .foot-meta {
  font-size: 15px;
}

html.theme-high-contrast .image-uploader .picker-btn {
  background: #000000;
  color: #ffffff;
  border: 1px solid #ffffff;
}

html.theme-high-contrast .image-uploader .picker-btn:hover {
  background: #1a1a1a;
}

html.theme-high-contrast .image-uploader .drop-zone {
  background: #000000;
  border-color: #ffffff;
}

html.theme-high-contrast .image-uploader .drop-tip,
html.theme-high-contrast .image-uploader .drop-sub,
html.theme-high-contrast .image-uploader .foot-meta {
  color: #ffffff;
}

html.theme-high-contrast .image-uploader .drop-tip em {
  color: #4ade80;
}

html.theme-high-contrast .image-uploader .preview-wrap {
  background: #000000;
  border-color: #ffffff;
}
</style>
