<template>
  <div class="pano-viewer">
    <!-- Three.js 360° 画布容器（v-show：保持场景存活，仅隐藏） -->
    <div
      v-show="!showOriginal"
      ref="canvasContainer"
      class="canvas-container"
      tabindex="0"
      role="img"
      :aria-label="`拖动旋转查看，可小幅上下俯仰${isTouch ? '、双指缩放' : ''}，当前视角：${currentViewLabel}`"
      @pointerdown="onDragStart"
      @pointermove="onDragMove"
      @pointerup="onDragEnd"
      @pointercancel="onDragEnd"
      @keydown.left.prevent="step(-1)"
      @keydown.right.prevent="step(1)"
      @keydown.up.prevent="tiltStep(1)"
      @keydown.down.prevent="tiltStep(-1)"
      @dblclick="resetTilt"
    >
      <span class="badge-360" aria-hidden="true">360°</span>
      <span class="drag-hint" aria-hidden="true">{{ hintText }}</span>
    </div>

    <!-- 原图模式（v-show：避免 v-if 反复创建/销毁 img 造成切回时重新解码闪烁） -->
    <img
      v-show="showOriginal && !!originalImage"
      :src="originalImage || undefined"
      class="original-img"
      alt="查看原图"
      draggable="false"
    />

    <!-- 控制条 -->
    <div class="controls">
      <button
        v-if="originalImage"
        type="button"
        class="ctl-btn"
        :aria-label="showOriginal ? '返回 360° 全景视图' : '查看原图'"
        @click="toggleOriginal"
      >
        {{ showOriginal ? '返回 360°' : '查看原图' }}
      </button>
      <button
        type="button"
        class="ctl-btn"
        :aria-label="autoRotate ? '停止旋转' : '自动旋转'"
        @click="toggleAutoRotate"
      >
        {{ autoRotate ? '停止旋转' : '自动旋转' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'

const props = defineProps({
  views: { type: Object, required: true }, // { front, left, back, right }
  originalImage: { type: String, default: '' },
})
const emit = defineEmits(['error'])

const canvasContainer = ref(null)
const showOriginal = ref(false)
const autoRotate = ref(true)
const currentView = ref('front')

// 4 面板参数：角度 a_i = i * π/2，相机旋转 theta = -a_i 时看向面板 i
const ORDER = ['front', 'right', 'back', 'left']
const ANGLES = [0, Math.PI / 2, Math.PI, 3 * Math.PI / 2]
const RADIUS = 5
const PANEL_W = 2 * RADIUS * Math.tan(Math.PI / 4) // 10
// 面板高度要在垂直方向留出俯仰余量。
// 推导：俯仰 φ 时，画面顶边射线的俯仰角为 30°(半FOV) + φ，它射到墙面时的落点高度
// y = d · tan(30° + φ)，d 是沿该射线到墙面的水平距离。4 面面板拼成方柱，
// d 在正面为 5、在墙角为 5√2 ≈ 7.071（斜看墙角时射线走得更远，所以落点最高）。
// φ 取上限 15° 时最坏落点 y = 7.071 · tan45° = 7.071，故面板半高必须 ≥ 7.071。
// 原 7.5（半高 3.75）连 6.9° 都撑不住，会直接露出底色，所以加高到 14.4（半高 7.2）。
const PANEL_H = 14.4
// 视角图是 4:3，铺满宽度 10 时自然高度 7.5：加高后贴图只占中间这一段，
// 上下多余部分靠 ClampToEdge 复制边缘像素填充，主体不被拉伸。
const IMAGE_H = PANEL_W * 0.75 // 7.5

// 垂直俯仰上限：±15°（没有顶部/底部的图，不能真上下 360°）
const PHI_LIMIT = (15 * Math.PI) / 180
// 垂直拖拽灵敏度（rad/px）：约 105px 走满 ±15°，比水平的 0.01 更钝，避免一拖到底
const TILT_SPEED = 0.0025
// 键盘上下键每次步进 5°
const TILT_STEP = Math.PI / 36

// 占位底色：贴图尚未加载完时露出的颜色（与容器背景一致）
const PLACEHOLDER_COLOR = 0x0f2416

const VIEW_LABELS = { front: '正面', right: '右侧', back: '背面', left: '左侧' }
const currentViewLabel = computed(() => VIEW_LABELS[currentView.value] || currentView.value)

/* 触摸设备：提示文案改说"双指缩放"（手机没有滚轮，PC 端也没有滚轮缩放，
   但 PC 用户对"拖动"的预期一致，所以只在触屏上追加双指说明） */
const isTouch = ref(false)
const hintText = computed(() =>
  isTouch.value ? '单指拖动 · 双指缩放 · 双击回正' : '拖动旋转 · ↕ 俯仰 · 双击回正',
)

// Three.js 运行时对象
let scene, camera, renderer, animationId
let theta = 0 // 当前水平旋转角
let targetTheta = 0 // 目标水平旋转角
let phi = 0 // 当前垂直俯仰角（0 = 水平，正 = 抬头）
let targetPhi = 0 // 目标垂直俯仰角
let autoTimer = null
let dragX = null
let dragY = null
let lastView = ''
let resizeObserver

function clampPhi(v) {
  return Math.max(-PHI_LIMIT, Math.min(PHI_LIMIT, v))
}

/* ---------- 键盘导航 ---------- */
function step(dir) {
  // dir=1 → 右（下一视角），dir=-1 → 左（上一视角）
  targetTheta -= dir * Math.PI / 2
}

function tiltStep(dir) {
  // dir=1 → 抬头，dir=-1 → 低头
  targetPhi = clampPhi(targetPhi + dir * TILT_STEP)
}

/* ---------- 双击回正 ---------- */
function resetTilt() {
  targetPhi = 0
}

/* ---------- 自动旋转（只动 theta，phi 保持不动） ---------- */
function startAutoRotate() {
  stopAutoRotate()
  autoTimer = setInterval(() => {
    targetTheta -= Math.PI / 2
  }, 3000)
}

function stopAutoRotate() {
  if (autoTimer) {
    clearInterval(autoTimer)
    autoTimer = null
  }
}

function toggleAutoRotate() {
  autoRotate.value = !autoRotate.value
  if (autoRotate.value) startAutoRotate()
  else stopAutoRotate()
}

/* ---------- 360° ⇄ 原图 切换 ---------- */
function toggleOriginal() {
  showOriginal.value = !showOriginal.value
}

/* ---------- 拖拽（水平改 theta，垂直改 phi）+ 双指捏合缩放 ---------- */
/* 多指跟踪：pointerId → 坐标。单指走旋转/俯仰，双指走 fov 缩放。
   两个手势互斥——双指按下时立刻把 dragX 置空，避免"边转边缩"。 */
const pointers = new Map()
let pinchStartDist = 0
let pinchStartFov = 0

const FOV_DEFAULT = 60
const FOV_MIN = 26 // 放大到 26°（视野窄 = 靠近看）
const FOV_MAX = 86 // 缩小到 86°（视野宽 = 退远看）

function pointerDistance() {
  const [a, b] = [...pointers.values()]
  if (!a || !b) return 0
  return Math.hypot(a.x - b.x, a.y - b.y) || 1
}

function applyPinch() {
  if (!camera || pointers.size < 2) return
  const dist = pointerDistance()
  if (!pinchStartDist) {
    pinchStartDist = dist
    pinchStartFov = camera.fov
    return
  }
  // 两指张开（dist 变大）→ ratio < 1 → fov 变小 → 画面放大
  const ratio = pinchStartDist / dist
  camera.fov = Math.min(FOV_MAX, Math.max(FOV_MIN, pinchStartFov * ratio))
  camera.updateProjectionMatrix()
}

function onDragStart(e) {
  pointers.set(e.pointerId, { x: e.clientX, y: e.clientY })
  e.currentTarget.setPointerCapture?.(e.pointerId)

  if (pointers.size === 2) {
    // 进入双指模式：停自动旋转、退出单指拖拽
    pinchStartDist = pointerDistance()
    pinchStartFov = camera ? camera.fov : FOV_DEFAULT
    dragX = null
    dragY = null
    if (autoRotate.value) stopAutoRotate()
    return
  }

  dragX = e.clientX
  dragY = e.clientY
  if (autoRotate.value) stopAutoRotate()
}

function onDragMove(e) {
  if (!pointers.has(e.pointerId)) return
  pointers.set(e.pointerId, { x: e.clientX, y: e.clientY })

  if (pointers.size >= 2) {
    applyPinch()
    return
  }

  if (dragX === null || dragY === null) return
  const dx = e.clientX - dragX
  const dy = e.clientY - dragY
  targetTheta -= dx * 0.01
  // 往上拖（dy < 0）→ 抬头，phi 增大
  targetPhi = clampPhi(targetPhi - dy * TILT_SPEED)
  dragX = e.clientX
  dragY = e.clientY
}

function onDragEnd(e) {
  pointers.delete(e.pointerId)
  if (pointers.size < 2) pinchStartDist = 0

  // 双指松开一根：剩下那根重新作为拖拽起点，避免画面"跳"一下
  if (pointers.size === 1) {
    const p = [...pointers.values()][0]
    dragX = p.x
    dragY = p.y
    return
  }

  dragX = null
  dragY = null
  if (autoRotate.value) startAutoRotate()
}

/* ---------- 当前视角判定（用于 aria-label） ---------- */
function getCurrentView() {
  const effective = ((-theta) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI)
  let closest = 0
  let minDiff = Infinity
  for (let i = 0; i < ORDER.length; i++) {
    if (!props.views[ORDER[i]]) continue
    let diff = Math.abs(effective - ANGLES[i])
    diff = Math.min(diff, 2 * Math.PI - diff)
    if (diff < minDiff) {
      minDiff = diff
      closest = i
    }
  }
  return ORDER[closest]
}

/* ---------- Three.js 初始化 ---------- */
function initThree() {
  const container = canvasContainer.value
  if (!container || container.clientWidth === 0) return

  try {
    scene = new THREE.Scene()

    const aspect = container.clientWidth / container.clientHeight
    camera = new THREE.PerspectiveCamera(60, aspect, 0.1, 100)
    camera.position.set(0, 0, 0)
    // 欧拉顺序必须显式设为 YXZ（先偏航 theta 再俯仰 phi）。
    // 默认的 XYZ 是 Rx·Ry：俯仰量会随偏航角衰减（转到侧面时上下倾斜完全失效）。
    camera.rotation.order = 'YXZ'

    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setSize(container.clientWidth, container.clientHeight)
    renderer.setPixelRatio(window.devicePixelRatio)
    // 输出色彩空间 / 色调映射：显式声明（three 0.186 的默认值就是
    // SRGBColorSpace + NoToneMapping，写出来是为了不依赖库默认值、防止升级后被改变）
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.NoToneMapping
    renderer.toneMappingExposure = 1.0
    // 深绿占位底色交给 clearColor 承担。
    // 注意：不能用 material.color 来做占位色 —— MeshBasicMaterial 的 color
    // 是与 map 逐像素相乘的乘数，设成深色会把贴图整体压暗并偏色。
    renderer.setClearColor(PLACEHOLDER_COLOR, 1)
    container.appendChild(renderer.domElement)

    const loader = new THREE.TextureLoader()
    let totalTextures = 0
    let failedCount = 0

    ORDER.forEach((name, i) => {
      const url = props.views[name]
      if (!url) return
      totalTextures++

      const geometry = new THREE.PlaneGeometry(PANEL_W, PANEL_H)
      const material = new THREE.MeshBasicMaterial({
        // 必须保持白色（默认值）：color 是乘数，设成深色会染色整张贴图
        color: 0xffffff,
        side: THREE.DoubleSide,
      })
      const angle = ANGLES[i]
      const mesh = new THREE.Mesh(geometry, material)
      mesh.position.set(
        RADIUS * Math.sin(angle),
        0,
        -RADIUS * Math.cos(angle),
      )
      mesh.rotation.y = -angle
      scene.add(mesh)

      loader.load(
        url,
        (texture) => {
          texture.colorSpace = THREE.SRGBColorSpace
          // 纵向 overscan：贴图只铺中间 IMAGE_H 这一段（保持 4:3 不变形），
          // uv.y 实际落在 [-0.46, 1.46]，越界部分由 ClampToEdge 复制边缘像素填充。
          // 水平静止时这段填充完全在视野外（|y| ≤ 2.89 < 3.75），只有俯仰到极限
          // 才会在画面顶/底露出填充带 —— 内容是图片最外一行像素，通常是背景色。
          const scaleY = PANEL_H / IMAGE_H
          texture.wrapT = THREE.ClampToEdgeWrapping
          texture.repeat.set(1, scaleY)
          texture.offset.set(0, (1 - scaleY) / 2)
          material.map = texture
          material.needsUpdate = true
        },
        undefined,
        () => {
          failedCount++
          if (failedCount === totalTextures) {
            // 全部贴图加载失败，通知父组件降级
            emit('error')
          }
        },
      )
    })

    // 如果没有任何贴图可加载，直接降级
    if (totalTextures === 0) {
      emit('error')
      return
    }

    animate()

    if (autoRotate.value) startAutoRotate()

    // 容器尺寸变化时同步更新相机和渲染器
    resizeObserver = new ResizeObserver(() => {
      if (!renderer || !camera || !container) return
      const w = container.clientWidth
      const h = container.clientHeight
      if (w === 0 || h === 0) return
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      renderer.setSize(w, h)
    })
    resizeObserver.observe(container)
  } catch {
    // WebGL 初始化失败（浏览器不支持或资源不足）
    emit('error')
  }
}

function animate() {
  animationId = requestAnimationFrame(animate)
  // 原图模式下画布不可见：保留 RAF 调度（便于切回时瞬间恢复），
  // 但不推进角度、不更新视角、不渲染 —— 避免白白占用 GPU 与「切回时视角已悄悄转走」
  if (showOriginal.value) return
  // 缓动：theta / phi 逐帧逼近各自目标值
  theta += (targetTheta - theta) * 0.12
  phi += (targetPhi - phi) * 0.12
  camera.rotation.y = theta
  camera.rotation.x = phi

  const view = getCurrentView()
  if (view !== lastView) {
    lastView = view
    currentView.value = view
  }

  renderer.render(scene, camera)
}

/* ---------- 切换 360° / 原图 的副作用 ---------- */
watch(showOriginal, (val) => {
  if (val) {
    // 进入原图：停掉自动旋转（保留 autoRotate 偏好，切回时按偏好恢复）
    stopAutoRotate()
    return
  }
  // 切回 360°：此前容器是 display:none（尺寸为 0），需等 DOM 恢复后再同步尺寸
  nextTick(() => {
    if (!renderer || !camera || !canvasContainer.value) return
    const w = canvasContainer.value.clientWidth
    const h = canvasContainer.value.clientHeight
    if (w === 0 || h === 0) return
    camera.aspect = w / h
    camera.updateProjectionMatrix()
    renderer.setSize(w, h)
    // 立即补渲染一帧，避免等待下一次 RAF 时才出画面
    renderer.render(scene, camera)
  })
  if (autoRotate.value) startAutoRotate()
})

/* ---------- 生命周期 ---------- */
onMounted(async () => {
  isTouch.value =
    window.matchMedia?.('(hover: none)').matches || (navigator.maxTouchPoints || 0) > 0
  await nextTick()
  initThree()
})

onBeforeUnmount(() => {
  if (animationId) {
    cancelAnimationFrame(animationId)
    animationId = null
  }
  stopAutoRotate()
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  if (renderer) {
    renderer.dispose()
    if (renderer.domElement?.parentNode) {
      renderer.domElement.parentNode.removeChild(renderer.domElement)
    }
    renderer = null
  }
  scene = null
  camera = null
})
</script>

<style scoped>
.pano-viewer {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
  height: 100%;
}

.canvas-container {
  position: relative;
  flex: 1;
  min-height: 0;
  width: 100%;
  border-radius: 16px;
  overflow: hidden;
  background: #0f2416;
  cursor: grab;
  /* 必须是 none：pan-y 会把垂直手势交给浏览器滚页面，pointermove 收不到，
     垂直俯仰在触摸端就完全无效。代价是在这块画布上纵向滑动不再滚页面。 */
  touch-action: none;
}

.canvas-container:active {
  cursor: grabbing;
}

.canvas-container:focus-visible {
  outline: 3px solid #2f855a;
  outline-offset: 2px;
}

.canvas-container :deep(canvas) {
  display: block;
}

.badge-360 {
  position: absolute;
  top: 12px;
  right: 12px;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  background: rgba(47, 133, 90, 0.7);
  pointer-events: none;
  z-index: 1;
}

.drag-hint {
  position: absolute;
  bottom: 10px;
  left: 50%;
  transform: translateX(-50%);
  padding: 4px 14px;
  border-radius: 999px;
  font-size: 13px;
  color: #fff;
  background: rgba(0, 0, 0, 0.45);
  pointer-events: none;
  z-index: 1;
}

.original-img {
  flex: 1;
  min-height: 0;
  width: 100%;
  /* 用 max-height 而非 height：flex-basis 已决定主尺寸，写死 height:100% 只会带来溢出隐患 */
  max-height: 100%;
  object-fit: contain;
  border-radius: 16px;
  user-select: none;
  pointer-events: none;
}

.controls {
  display: flex;
  gap: 10px;
}

.ctl-btn {
  min-height: 40px;
  padding: 0 16px;
  font-size: 14px;
  font-weight: 600;
  border: 1px solid rgba(47, 133, 90, 0.4);
  border-radius: 10px;
  background: #fff;
  color: #1b5e20;
  cursor: pointer;
}

.ctl-btn:hover {
  background: #ecfdf5;
}

.ctl-btn:focus-visible {
  outline: 3px solid #2f855a;
  outline-offset: 2px;
}

/* 助老模式：提示条与按钮放大（拖拽区域本身不动，避免影响父级卡片布局） */
html.mode-elderly .drag-hint {
  font-size: 16px;
  padding: 6px 18px;
}

html.mode-elderly .ctl-btn {
  min-height: 56px;
  font-size: 19px;
  padding: 0 22px;
}

/* ============================================================
   移动端（≤767px）
   ① 提示条文案已在脚本里按设备切换（触屏说"双指缩放"，并去掉"↕ 俯仰"，
      因为手机用户对上下俯仰的预期弱，先说清两个主要手势）；
   ② 控制条按钮抬高到 44px 并平分宽度。
   ============================================================ */
@media (max-width: 767px) {
  .controls {
    gap: 8px;
    flex-wrap: nowrap;
  }

  .ctl-btn {
    flex: 1 1 0;
    min-width: 0;
    min-height: 44px;
    padding: 0 8px;
    font-size: 13px;
    touch-action: manipulation;
    -webkit-tap-highlight-color: transparent;
  }

  .drag-hint {
    bottom: 8px;
    padding: 3px 10px;
    font-size: 11px;
    white-space: nowrap;
  }

  .badge-360 {
    top: 8px;
    right: 8px;
    font-size: 11px;
  }
}

/* 高对比度：画布上的两个浮层改为黑底白字白描边，保证在深色画面上可读 */
html.theme-high-contrast .drag-hint,
html.theme-high-contrast .badge-360 {
  background: #000;
  color: #fff;
  border: 2px solid #fff;
}
</style>
