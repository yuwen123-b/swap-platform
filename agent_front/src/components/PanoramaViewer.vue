<template>
  <div class="pano-viewer">
    <!-- Three.js 360° 画布容器 -->
    <div
      v-show="!showOriginal"
      ref="canvasContainer"
      class="canvas-container"
      tabindex="0"
      role="img"
      :aria-label="t('panorama.ariaStage', { tip: t('panorama.dragTip'), view: currentViewLabel })"
      @pointerdown="onDragStart"
      @pointermove="onDragMove"
      @pointerup="onDragEnd"
      @pointercancel="onDragEnd"
      @keydown.left.prevent="step(-1)"
      @keydown.right.prevent="step(1)"
    >
      <span class="badge-360" aria-hidden="true">360°</span>
      <span class="drag-hint" aria-hidden="true">⟵ ⟶ {{ t('panorama.dragTip') }}</span>
    </div>

    <!-- 原图模式 -->
    <img
      v-if="showOriginal && originalImage"
      :src="originalImage"
      class="original-img"
      :alt="t('panorama.viewOriginal')"
      draggable="false"
    />

    <!-- 控制条 -->
    <div class="controls">
      <button
        v-if="originalImage"
        type="button"
        class="ctl-btn"
        :aria-label="showOriginal ? t('panorama.view360') : t('panorama.viewOriginal')"
        @click="showOriginal = !showOriginal"
      >
        {{ showOriginal ? t('panorama.view360') : t('panorama.viewOriginal') }}
      </button>
      <button
        type="button"
        class="ctl-btn"
        :aria-label="autoRotate ? t('panorama.stop') : t('panorama.autoPlay')"
        @click="toggleAutoRotate"
      >
        {{ autoRotate ? t('panorama.stop') : t('panorama.autoPlay') }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { useI18n } from '../i18n'

const props = defineProps({
  views: { type: Object, required: true }, // { front, left, back, right }
  originalImage: { type: String, default: '' },
})
const emit = defineEmits(['error'])
const { t } = useI18n()

const canvasContainer = ref(null)
const showOriginal = ref(false)
const autoRotate = ref(true)
const currentView = ref('front')

// 4 面板参数：角度 a_i = i * π/2，相机旋转 theta = -a_i 时看向面板 i
const ORDER = ['front', 'right', 'back', 'left']
const ANGLES = [0, Math.PI / 2, Math.PI, 3 * Math.PI / 2]
const RADIUS = 5
const PANEL_W = 2 * RADIUS * Math.tan(Math.PI / 4) // 10
const PANEL_H = 7.5

const currentViewLabel = computed(() => {
  const key = `panorama.${currentView.value}`
  const text = t(key)
  return text === key ? currentView.value : text
})

// Three.js 运行时对象
let scene, camera, renderer, animationId
let theta = 0 // 当前旋转角
let targetTheta = 0 // 目标旋转角
let autoTimer = null
let dragX = null
let lastView = ''
let resizeObserver

/* ---------- 键盘导航 ---------- */
function step(dir) {
  // dir=1 → 右（下一视角），dir=-1 → 左（上一视角）
  targetTheta -= dir * Math.PI / 2
}

/* ---------- 自动旋转 ---------- */
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

/* ---------- 拖拽 ---------- */
function onDragStart(e) {
  dragX = e.clientX
  e.currentTarget.setPointerCapture?.(e.pointerId)
  if (autoRotate.value) stopAutoRotate()
}

function onDragMove(e) {
  if (dragX === null) return
  const delta = e.clientX - dragX
  targetTheta -= delta * 0.01
  dragX = e.clientX
}

function onDragEnd(e) {
  if (dragX === null) return
  dragX = null
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

    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setSize(container.clientWidth, container.clientHeight)
    renderer.setPixelRatio(window.devicePixelRatio)
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
        color: 0x0f2416,
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
  // 缓动：theta 逐帧逼近 targetTheta
  theta += (targetTheta - theta) * 0.12
  camera.rotation.y = theta

  const view = getCurrentView()
  if (view !== lastView) {
    lastView = view
    currentView.value = view
  }

  renderer.render(scene, camera)
}

/* ---------- 切回画布时重算尺寸 ---------- */
watch(showOriginal, (val) => {
  if (val || !renderer || !camera || !canvasContainer.value) return
  nextTick(() => {
    const w = canvasContainer.value.clientWidth
    const h = canvasContainer.value.clientHeight
    if (w === 0 || h === 0) return
    camera.aspect = w / h
    camera.updateProjectionMatrix()
    renderer.setSize(w, h)
  })
})

/* ---------- 生命周期 ---------- */
onMounted(async () => {
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
  touch-action: pan-y;
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
  height: 100%;
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
</style>
