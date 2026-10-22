<!--
  拍照上传弹窗（职责单一）
  ---------------------------------------------------------------
  只做四件事：开关摄像头 / 预览 / 拍照 / 把 File 交给父组件。
  不做上传、不做业务判断、不依赖任何第三方库。

  ⚠ 为什么需要「挑设备」这一整套逻辑
  Windows 笔记本常常同时暴露多个 videoinput：
    - Integrated Camera        ← 真正能出画的彩色摄像头
    - Integrated IR Camera     ← 红外，被 Windows Hello 独占，网页打不开
    - Windows Virtual Camera / VirtualCameraService（联想等厂商安装）← 虚拟设备
  getUserMedia 只按约束挑一个，挑错了就直接失败或出黑屏。
  因此这里分四轮尝试：带朝向偏好 → 系统默认 → 最宽松 → 逐设备（跳过红外/虚拟）。

  ===============================================================
  切换摄像头：两套逻辑（移动端 / 桌面端 不共用）
  ===============================================================
  · 移动端（isMobile）—— 只用 facingMode，'user' ⇄ 'environment'
      iOS / Android 的 deviceId 每个会话都会变，跨会话不可靠，不能当标识用；
      且安卓多摄机型会把主摄/超广角/长焦全部枚举出来，按 deviceId 轮换会切到
      超广角，用户以为是「切前置」。所以移动端只在前/后之间切。
  · 桌面端（!isMobile）—— 维持原有 deviceId 轮换（桌面没有前后置概念）
  · 切换失败 —— 先存快照 → stopStream → 试新约束 → 失败则用快照回滚，
      提示「切换失败，当前设备可能不支持该摄像头」，**不关弹窗**；
      只有回滚也失败才显示错误遮罩（保留重试 / 改用文件上传两条出路）。

  前置预览镜像：预览层 scaleX(-1)（像照镜子），拍照走 canvas.drawImage
  取的是 video 原始像素、不受 CSS transform 影响 → 照片保持真实朝向。

  摄像头释放（多重保险，缺一不可）：
  1. 关闭弹窗   —— @close（动画开始即停，指示灯立刻熄灭）+ @closed 兜底
  2. 组件卸载   —— onBeforeUnmount
  3. 关闭页面   —— beforeunload / pagehide（直接关标签页时释放设备）
  任一时刻释放后都要清空 video.srcObject，否则安卓上会残留一路占用。

  状态清理分两个函数（重要）：
  · stopStream()        —— 只释放资源（track + srcObject + ready）
  · resetSessionState() —— 清业务状态（facing / deviceId / label / 摄像头列表 / 按钮）
  二者在「打开」与「关闭」路径上成对调用；但**切换**路径只调 stopStream，
  否则切换瞬间 switchable 被清掉会让「切换摄像头」按钮闪一下、
  连带「取消 / 拍照」左右跳动。
-->
<template>
  <el-dialog
    v-model="visible"
    title="拍照上传"
    class="cam-dialog"
    width="min(680px, 92vw)"
    :close-on-click-modal="false"
    append-to-body
    @opened="startCamera"
    @close="onDialogClose"
    @closed="onDialogClosed"
  >
    <div class="cam-stage">
      <video
        ref="videoRef"
        class="cam-video"
        :class="{ mirrored: previewMirrored }"
        autoplay
        muted
        playsinline
        @loadedmetadata="ready = true"
      />

      <div v-if="starting" class="cam-mask">正在打开摄像头…</div>

      <!-- 失败但可自救：保留弹窗，给「重试」和「改用文件上传」两条出路 -->
      <div v-else-if="errorText" class="cam-mask cam-error">
        <p class="cam-error-text">{{ errorText }}</p>
        <div class="cam-error-actions">
          <button type="button" class="cam-btn primary" @click="retry">重试</button>
          <button type="button" class="cam-btn ghost" @click="useFileInstead('')">改用文件上传</button>
        </div>
      </div>

      <!-- 当前使用的摄像头：移动端用朝向文案，桌面端用设备 label -->
      <span v-if="!starting && !errorText && activeCameraText" class="cam-active-chip">
        {{ activeCameraText }}
      </span>

      <button
        v-if="!starting && !errorText"
        type="button"
        class="cam-switch-file"
        @click="useFileInstead('已切换为文件选择')"
      >
        改用文件上传
      </button>

      <div class="cam-bar">
        <button type="button" class="cam-btn ghost" @click="close">取消</button>
        <button type="button" class="cam-btn primary" :disabled="!ready" @click="capture">
          {{ ready ? '拍照' : '画面准备中…' }}
        </button>
        <!-- 只有确认存在多个可用摄像头时才出现（单摄笔记本/单摄手机不显示） -->
        <button
          v-if="switchable"
          type="button"
          class="cam-btn ghost"
          :disabled="starting || !sessionActive"
          :title="switchTitle"
          @click="switchCamera"
        >
          切换摄像头
        </button>
      </div>
    </div>

    <p class="cam-tip">首次使用浏览器会询问摄像头权限；照片仅用于本次识别 / 估价，不会上传到第三方。</p>
  </el-dialog>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  // 弹窗显隐（v-model）
  modelValue: { type: Boolean, default: false },
  // 拍照结果大小上限，转换后再校验（base64 兜底路径体积 +33%）
  maxSize: { type: Number, default: 5 * 1024 * 1024 },
})

const emit = defineEmits(['update:modelValue', 'captured', 'fallback'])

// 红外 / 虚拟摄像头：网页打不开或只能出黑屏，一律判定为不可用
const BAD_CAMERA_RE = /virtual|虚拟|spitcamera|infrared|\bIR\b|ir camera|红外|windows hello|obs virtual/i
// 常见的内置 / 外接真实摄像头
const GOOD_CAMERA_RE = /integrated|内置|built-in|hd camera|webcam|usb|facetime/i
// 预览分辨率偏好（失败会逐轮放宽）
const VIDEO_SIZE = { width: { ideal: 1280 }, height: { ideal: 720 } }

// 移动端判定：UA 优先（iPadOS 会伪装成 Mac，用 maxTouchPoints 兜底）。
// 不用 matchMedia('(pointer: coarse)')——带触摸屏的 Windows 笔记本同样会命中，
// 会把桌面端误判成移动端，进而给它传 facingMode（正是上次「打不开摄像头」的诱因）。
const isMobile = /Android|iPhone|iPad|iPod|Mobile|Windows Phone/i.test(navigator.userAgent)
  || (navigator.maxTouchPoints > 1 && /Mac/.test(navigator.platform || ''))
// 桌面端没有「前后置」概念，初始不传 facingMode；移动端优先后置（拍物品更符合直觉）
const INITIAL_FACING = isMobile ? 'environment' : ''

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const videoRef = ref(null)
const stream = ref(null)
const starting = ref(false)
const ready = ref(false)
const errorText = ref('')
const cameras = ref([])
// 移动端：当前朝向（'environment' 后置 / 'user' 前置 / '' 桌面端无此概念）
const facing = ref(INITIAL_FACING)
// 移动端是否支持切换朝向（单摄设备置 false 后按钮隐藏）
const facingSupported = ref(isMobile)
// 桌面端：当前 deviceId 与设备名
const activeDeviceId = ref('')
const activeLabel = ref('')
// 是否存在多个可切换的摄像头（由 syncSwitchable 统一维护，关闭时清零）
const switchable = ref(false)
// 本次是否已成功出画（用于提示文案与按钮可用性）
const sessionActive = ref(false)

const usableCameras = computed(() => cameras.value.filter((c) => c.score >= 0))
// 前置预览镜像：仅当确实用的是前置摄像头（桌面端 facing 恒为 ''，不受影响）
const previewMirrored = computed(() => facing.value === 'user')
const activeCameraText = computed(() => {
  if (!sessionActive.value) return ''
  // 移动端不依赖 label（iOS 首次授权后 label 仍可能为空），直接用朝向推导
  if (isMobile) return facing.value === 'user' ? '当前：前置摄像头' : '当前：后置摄像头'
  return activeLabel.value ? `当前：${activeLabel.value}` : ''
})
const switchTitle = computed(() => {
  if (isMobile) return '在前置 / 后置摄像头之间切换'
  const count = usableCameras.value.length
  return count > 1 ? `在 ${count} 个摄像头之间切换` : '当前设备只有一个可用摄像头'
})
const maxSizeText = computed(() => `${Math.round(props.maxSize / 1024 / 1024)}MB`)

function close() {
  visible.value = false
}

/* ---------------- 设备识别 ---------------- */

function scoreCamera(label) {
  if (!label) return 0
  if (BAD_CAMERA_RE.test(label)) return -10
  if (GOOD_CAMERA_RE.test(label)) return 10
  return 1
}

// 把浏览器报告的 facingMode 归一成 'user' / 'environment'（部分安卓会报 left / right）
function normalizeFacing(value) {
  if (!value) return ''
  const v = String(value).toLowerCase()
  if (v === 'environment') return 'environment'
  if (v === 'user' || v === 'left' || v === 'right') return 'user'
  return ''
}

function syncActiveLabel() {
  // 移动端不显示 label，避免 iOS 空 label 造成空提示
  if (isMobile) {
    activeLabel.value = ''
    return
  }
  activeLabel.value = cameras.value.find((c) => c.deviceId === activeDeviceId.value)?.label || ''
}

function syncSwitchable() {
  if (!sessionActive.value) {
    switchable.value = false
    return
  }
  switchable.value = isMobile ? facingSupported.value : usableCameras.value.length > 1
}

// 枚举视频输入设备并按「可用度」排序（桌面端主力；移动端仅在四轮全失败时兜底用一次）。
// 注意：label 只有在授权后才拿得到，所以这个函数必须在一次 getUserMedia 之后调用才有意义。
async function listCameras() {
  try {
    if (!navigator.mediaDevices?.enumerateDevices) return []
    const devices = await navigator.mediaDevices.enumerateDevices()
    const list = devices
      .filter((d) => d.kind === 'videoinput' && d.deviceId)
      .map((d) => ({ deviceId: d.deviceId, label: d.label || '', score: scoreCamera(d.label) }))
      .sort((a, b) => b.score - a.score)
    cameras.value = list
    syncActiveLabel()
    syncSwitchable()
    return list
  } catch {
    cameras.value = []
    return []
  }
}

/* ---------------- 摄像头生命周期 ---------------- */

function releaseMediaStream(mediaStream) {
  if (!mediaStream) return
  mediaStream.getTracks().forEach((track) => {
    try {
      track.stop()
    } catch {
      /* 已被浏览器回收，忽略 */
    }
  })
}

// 只释放资源：track.stop() + 清 srcObject，两件事都做才算真正释放
function stopStream() {
  releaseMediaStream(stream.value)
  stream.value = null
  if (videoRef.value) {
    try {
      videoRef.value.srcObject = null
    } catch {
      /* 忽略 */
    }
  }
  ready.value = false
  sessionActive.value = false
}

// 清空会话状态：下次打开不残留上一次的镜头 / 设备 / 按钮
function resetSessionState() {
  facing.value = INITIAL_FACING
  facingSupported.value = isMobile
  activeDeviceId.value = ''
  activeLabel.value = ''
  cameras.value = []
  switchable.value = false
}

function onDialogClose() {
  stopStream()
  resetSessionState()
}

function onDialogClosed() {
  stopStream()
  resetSessionState()
}

// 按约束取流；size=false 时用最宽松的 video:true
async function requestStream({ facing: wantFacing, deviceId } = {}) {
  if (!wantFacing && !deviceId) {
    return navigator.mediaDevices.getUserMedia({ video: true, audio: false })
  }
  const video = { ...VIDEO_SIZE }
  if (deviceId) video.deviceId = { exact: deviceId }
  if (wantFacing) video.facingMode = { ideal: wantFacing }
  return navigator.mediaDevices.getUserMedia({ video, audio: false })
}

function applyStream(mediaStream, meta = {}) {
  ready.value = false
  stream.value = mediaStream

  const settings = mediaStream.getVideoTracks?.()[0]?.getSettings?.() || {}
  activeDeviceId.value = settings.deviceId || ''

  if (isMobile) {
    // 以浏览器实际给的朝向为准；拿不到就退回本次请求的朝向
    facing.value = normalizeFacing(settings.facingMode) || meta.facing || 'environment'
  } else {
    // 桌面端没有前后置概念，恒为 ''，预览不做镜像（与改造前一致）
    facing.value = ''
  }

  if (videoRef.value) {
    videoRef.value.srcObject = mediaStream
    // 个别浏览器不认 autoplay，显式 play 一次
    videoRef.value.play?.().catch(() => {})
  }

  sessionActive.value = true
  syncActiveLabel()
  syncSwitchable()
}

async function startCamera() {
  resetSessionState()
  await openStream(facing.value || INITIAL_FACING)
}

function retry() {
  openStream(facing.value || INITIAL_FACING)
}

async function openStream(orientation) {
  if (!navigator.mediaDevices?.getUserMedia) {
    // 非安全上下文（http 非 localhost）或浏览器过旧：直接降级
    emit('fallback', '当前环境不支持直接调用摄像头，已切换为文件选择')
    close()
    return
  }

  // 重开必须先释放旧流并清空 srcObject，
  // 否则会出现短暂双流占用，安卓上直接抛 NotReadableError
  stopStream()
  starting.value = true
  errorText.value = ''

  const attempts = []
  // 第 1 轮：移动端请求后置；桌面端不做朝向约束（orientation 为空，整轮跳过）
  if (orientation) attempts.push({ video: { facingMode: { ideal: orientation }, ...VIDEO_SIZE }, audio: false })
  // 第 2 轮：系统默认摄像头
  attempts.push({ video: { ...VIDEO_SIZE }, audio: false })
  // 第 3 轮：最宽松约束
  attempts.push({ video: true, audio: false })

  let mediaStream = null
  let lastError = null
  let facingRejected = false

  for (const constraints of attempts) {
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia(constraints)
      break
    } catch (error) {
      lastError = error
      if (error?.name === 'OverconstrainedError') facingRejected = true
    }
  }

  // 移动端朝向约束被明确拒绝 → 该设备只有一个朝向的摄像头，切换按钮没有意义
  if (!mediaStream && isMobile && facingRejected) facingSupported.value = false

  // 第 4 轮：逐设备尝试。桌面端是主力兜底（浏览器挑了红外/虚拟设备时靠它找真摄像头）；
  // 移动端保留同一条兜底（避免丢掉上次修好的能力），但移动端的正常打开与切换路径
  // 完全不使用这张设备表。
  if (!mediaStream) {
    const list = await listCameras()
    for (const cam of list) {
      if (cam.score < 0) continue
      try {
        mediaStream = await navigator.mediaDevices.getUserMedia({
          video: { deviceId: { exact: cam.deviceId }, ...VIDEO_SIZE },
          audio: false,
        })
        break
      } catch (error) {
        lastError = error
      }
    }
  }

  if (!mediaStream) {
    starting.value = false
    handleCameraError(lastError)
    return
  }

  // 等待期间用户可能已经关掉了弹窗
  if (!props.modelValue) {
    releaseMediaStream(mediaStream)
    starting.value = false
    return
  }

  await nextTick()
  applyStream(mediaStream, { facing: orientation })
  starting.value = false

  await preferRealCamera()
}

// 拿到流之后再看一眼：如果浏览器给的是红外/虚拟设备，自动换到真实摄像头。
// 移动端直接跳过（此处按 deviceId 重开会打乱 facing 状态，且移动端摄像头基本都是真实的）
async function preferRealCamera() {
  if (isMobile) return
  const list = await listCameras()
  if (!list.length) return
  const current = list.find((c) => c.deviceId === activeDeviceId.value)
  // 认不出当前设备时不动手，避免抢掉用户/系统本来正确的默认选择
  if (!current || current.score >= 0) return
  const target = list.find((c) => c.score > 0) || usableCameras.value[0]
  if (!target) return
  await reopenWith({ deviceId: target.deviceId }, { facing: facing.value, deviceId: activeDeviceId.value })
}

// 错误分类：文案固定；权限/占用保持弹窗打开并给重试出路，无设备/未知直接降级到文件选择
function handleCameraError(error) {
  const name = error?.name || ''
  if (name) console.warn('[相机] 打开失败:', name, error?.message)

  if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
    errorText.value = '请允许浏览器访问摄像头'
    ElMessage.warning('请允许浏览器访问摄像头')
  } else if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
    ElMessage.warning('未检测到摄像头，已切换到文件上传')
    useFileInstead(null)
  } else if (name === 'NotReadableError' || name === 'TrackStartError') {
    errorText.value = '摄像头被其他应用占用'
    ElMessage.warning('摄像头被其他应用占用')
  } else {
    ElMessage.warning('无法打开摄像头，已切换到文件上传')
    useFileInstead(null)
  }
}

// 降级：交给父组件的隐藏 input[capture] 接管（message 为 null 表示弹窗内已提示过）
function useFileInstead(message) {
  if (message) ElMessage.warning(message)
  emit('fallback', message || '')
  close()
}

/* ---------------- 切换摄像头 ---------------- */

// 统一入口：移动端切朝向，桌面端切设备
function switchCamera() {
  if (starting.value || !sessionActive.value) return
  if (isMobile) switchByFacing()
  else switchByDeviceId()
}

// 移动端：'environment' ⇄ 'user'，不使用 deviceId
function switchByFacing() {
  const target = facing.value === 'environment' ? 'user' : 'environment'
  // 快照必须在 stopStream 之前采集
  reopenWith({ facing: target }, { facing: facing.value, deviceId: '' })
}

// 桌面端：在可用设备间轮换（保持原有逻辑）
function switchByDeviceId() {
  const list = usableCameras.value
  if (list.length < 2) return
  const index = list.findIndex((c) => c.deviceId === activeDeviceId.value)
  // 拿不到当前 deviceId 时 index = -1，从 0 之后开始找，避免「点了没反应」
  let next = null
  for (let step = 1; step <= list.length; step += 1) {
    const candidate = list[((index < 0 ? 0 : index) + step) % list.length]
    if (candidate && candidate.deviceId !== activeDeviceId.value) {
      next = candidate
      break
    }
  }
  if (!next) return
  reopenWith({ deviceId: next.deviceId }, { facing: facing.value, deviceId: activeDeviceId.value })
}

// 按快照生成回滚约束。
// 注意必须返回 {} 而不是 null：requestStream 用的是对象解构，
// 解构默认值只对 undefined 生效，传 null 会直接抛 TypeError，
// 会把「回滚」路径打成「回滚失败 → 关弹窗」。
function snapshotConstraint(snapshot) {
  if (isMobile && snapshot.facing) return { facing: snapshot.facing }
  if (snapshot.deviceId) return { deviceId: snapshot.deviceId }
  return {} // 兜底：最宽松约束（系统默认摄像头）
}

// 切换执行：先存快照 → stopStream → 试新约束 → 失败用快照回滚 → 回滚也失败才报错
async function reopenWith(constraint, snapshot) {
  stopStream()
  starting.value = true
  errorText.value = ''

  let failure = null
  try {
    const mediaStream = await requestStream(constraint)
    // 移动端核对：浏览器实际给的是不是我们要的朝向
    // （用 ideal 不会抛错，只能靠回读 getSettings 判断）
    const actualFacing = normalizeFacing(mediaStream.getVideoTracks?.()[0]?.getSettings?.().facingMode)
    if (constraint.facing && actualFacing && actualFacing !== constraint.facing) {
      releaseMediaStream(mediaStream)
      failure = { name: 'OverconstrainedError', message: `设备未提供 ${constraint.facing} 摄像头` }
    } else {
      await nextTick()
      applyStream(mediaStream, { facing: constraint.facing })
    }
  } catch (error) {
    failure = error
  }

  if (!failure) {
    starting.value = false
    return
  }

  // 明确不支持目标朝向 / 目标设备 → 之后不再显示切换按钮
  if (isMobile && failure.name === 'OverconstrainedError') facingSupported.value = false

  // 回滚到切换前的摄像头：保持原画面，不把用户扔在原地
  try {
    const rolled = await requestStream(snapshotConstraint(snapshot))
    await nextTick()
    applyStream(rolled, { facing: snapshot.facing })
    ElMessage.warning('切换失败，当前设备可能不支持该摄像头')
  } catch (rollbackError) {
    handleCameraError(rollbackError)
  } finally {
    starting.value = false
  }
}

/* ---------------- 拍照 ---------------- */

function capture() {
  const video = videoRef.value
  if (!video || !video.videoWidth || !video.videoHeight) {
    ElMessage.warning('摄像头画面尚未就绪，请稍候再试')
    return
  }

  const canvas = document.createElement('canvas')
  canvas.width = video.videoWidth
  canvas.height = video.videoHeight
  const ctx = canvas.getContext('2d')
  if (!ctx) {
    ElMessage.warning('拍照失败，请重试')
    return
  }
  // canvas 取的是 video 的原始像素，不受预览层 scaleX(-1) 影响 → 照片始终是真实朝向
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height)

  toBlobCompat(canvas, (blob) => {
    if (!blob) {
      ElMessage.warning('拍照失败，请重试')
      return
    }
    // 大小校验放在转换之后：toDataURL 兜底路径比原图大 ~33%，
    // 若在转换前判断，同一张照片可能前端放行、后端 400
    if (blob.size > props.maxSize) {
      ElMessage.warning(`图片大小不能超过 ${maxSizeText.value}`)
      return
    }
    const file = new File([blob], `camera-${Date.now()}.jpg`, { type: 'image/jpeg' })
    emit('captured', file)
    close()
  })
}

// canvas.toBlob 在旧版 Safari 上不存在，走 dataURL → Blob 兜底
function toBlobCompat(canvas, done) {
  if (typeof canvas.toBlob === 'function') {
    canvas.toBlob((blob) => done(blob), 'image/jpeg', 0.9)
    return
  }
  try {
    const dataUrl = canvas.toDataURL('image/jpeg', 0.9)
    const base64 = dataUrl.split(',')[1] || ''
    const binary = atob(base64)
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
    done(new Blob([bytes], { type: 'image/jpeg' }))
  } catch {
    done(null)
  }
}

/* ---------------- 释放兜底 ---------------- */

watch(
  () => props.modelValue,
  (open) => {
    if (!open) {
      stopStream()
      resetSessionState()
    }
  },
)

onMounted(() => {
  // 直接关标签页/切后台时也要把摄像头交还系统
  window.addEventListener('beforeunload', stopStream)
  window.addEventListener('pagehide', stopStream)
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', stopStream)
  window.removeEventListener('pagehide', stopStream)
  stopStream()
  resetSessionState()
})
</script>

<style scoped>
.cam-stage {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  border-radius: 12px;
  overflow: hidden;
  background: #0b1220;
}

.cam-video {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  background: #0b1220;
}

/* 前置摄像头预览镜像（像照镜子）；只影响预览，不影响拍照结果 */
.cam-video.mirrored {
  transform: scaleX(-1);
}

.cam-mask {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: #ffffff;
  font-size: 14px;
  letter-spacing: 0.02em;
  background: var(--cam-mask-bg, rgba(11, 18, 32, 0.72));
}

.cam-error {
  align-content: center;
  gap: 16px;
  padding: 20px;
  text-align: center;
}

.cam-error-text {
  margin: 0;
  font-size: 16px;
  font-weight: 500;
}

.cam-error-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  flex-wrap: wrap;
}

.cam-switch-file {
  position: absolute;
  top: 10px;
  right: 10px;
  padding: 6px 12px;
  border: 1px solid var(--cam-chip-border, rgba(255, 255, 255, 0.55));
  border-radius: 999px;
  background: var(--cam-chip-bg, rgba(17, 24, 39, 0.5));
  color: var(--cam-chip-fg, #ffffff);
  font-size: 12px;
  cursor: pointer;
}

.cam-switch-file:hover {
  background: var(--cam-chip-bg-hover, rgba(17, 24, 39, 0.72));
}

/* 当前摄像头提示：压在画面左上角，不占用底部按钮栏，窄屏也不会换行挤按钮 */
.cam-active-chip {
  position: absolute;
  top: 10px;
  left: 10px;
  padding: 6px 12px;
  border: 1px solid var(--cam-chip-border, rgba(255, 255, 255, 0.55));
  border-radius: 999px;
  background: var(--cam-chip-bg, rgba(17, 24, 39, 0.5));
  color: var(--cam-chip-fg, #ffffff);
  font-size: 12px;
  pointer-events: none;
}

/* 底部按钮栏：半透明压在画面上 */
.cam-bar {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  gap: 12px;
  justify-content: center;
  align-items: center;
  flex-wrap: wrap;
  padding: 12px 14px;
  background: var(--cam-bar-bg, rgba(17, 24, 39, 0.55));
}

.cam-btn {
  min-width: 96px;
  min-height: 44px;
  padding: 0 18px;
  border-radius: 12px;
  border: 1px solid transparent;
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.2s ease, background 0.2s ease;
}

.cam-btn.primary {
  background: var(--green-primary);
  color: #ffffff;
  box-shadow: var(--shadow-btn);
}

.cam-btn.ghost {
  background: var(--cam-ghost-bg, rgba(255, 255, 255, 0.16));
  border-color: var(--cam-ghost-border, rgba(255, 255, 255, 0.6));
  color: var(--cam-ghost-fg, #ffffff);
}

.cam-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  box-shadow: none;
}

.cam-tip {
  margin: 14px 0 0;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text-secondary);
}
</style>

<!-- ============================================================
     助老模式 / 高对比度适配
     必须非 scoped——需要命中 html 根级选择器（与 ItemDetail.vue 约定一致）
     ============================================================ -->
<style>
/* 助老模式：弹窗内所有按钮点击目标 ≥ 60px */
html.mode-elderly .cam-dialog .cam-btn {
  min-height: 60px;
  font-size: 18px;
  padding: 0 24px;
}

html.mode-elderly .cam-dialog .cam-switch-file,
html.mode-elderly .cam-dialog .cam-active-chip {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  font-size: 15px;
  padding: 0 16px;
}

html.mode-elderly .cam-dialog .cam-tip,
html.mode-elderly .cam-dialog .cam-error-text {
  font-size: 16px;
}

/* 高对比度：黑底 + 纯白描边，半透明栏压到接近纯黑保证可读 */
html.theme-high-contrast .cam-dialog .cam-stage {
  --cam-bar-bg: rgba(0, 0, 0, 0.92);
  --cam-mask-bg: rgba(0, 0, 0, 0.94);
  --cam-chip-bg: #000000;
  --cam-chip-bg-hover: #1a1a1a;
  --cam-chip-border: #ffffff;
  --cam-chip-fg: #ffffff;
  --cam-ghost-bg: #000000;
  --cam-ghost-border: #ffffff;
  --cam-ghost-fg: #ffffff;
  border: 1px solid #ffffff;
}

html.theme-high-contrast .cam-dialog .cam-btn.primary {
  background: #4ade80;
  color: #000000;
  box-shadow: none;
}

html.theme-high-contrast .cam-dialog .cam-tip,
html.theme-high-contrast .cam-dialog .cam-mask,
html.theme-high-contrast .cam-dialog .cam-active-chip {
  color: #ffffff;
}
</style>
