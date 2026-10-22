<template>
  <div class="model-viewer">
    <!-- Three.js 画布容器（v-show：保持场景存活，仅隐藏） -->
    <div
      v-show="!showOriginal"
      ref="canvasContainer"
      class="canvas-container"
      tabindex="0"
      role="img"
      :aria-label="ariaText"
      @dblclick="resetView"
    >
      <span class="badge-3d" aria-hidden="true">3D</span>
      <span class="drag-hint" aria-hidden="true">{{ hintText }}</span>

      <!-- 加载进度：40MB 级 GLB 首次加载较慢，必须有可见反馈 -->
      <div v-if="loading" class="loading-overlay" role="status" aria-live="polite">
        <span class="loading-text">
          3D 模型加载中{{ progressText }}，请稍候…
        </span>
        <div class="progress-track">
          <div
            class="progress-fill"
            :class="{ indeterminate: !hasProgress }"
            :style="hasProgress ? { width: `${progress}%` } : undefined"
          />
        </div>
      </div>
    </div>

    <!-- 原图模式（v-show：避免反复创建销毁 img 造成切回时重新解码闪烁） -->
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
        :aria-label="showOriginal ? '返回 3D 模型' : '查看原图'"
        @click="toggleOriginal"
      >
        {{ showOriginal ? '返回 3D' : '查看原图' }}
      </button>
      <button
        type="button"
        class="ctl-btn"
        :aria-label="autoRotate ? '停止旋转' : '自动旋转'"
        @click="toggleAutoRotate"
      >
        {{ autoRotate ? '停止旋转' : '自动旋转' }}
      </button>
      <button type="button" class="ctl-btn" aria-label="重置视角" @click="resetView">
        重置视角
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'

const props = defineProps({
  modelUrl: { type: String, required: true }, // 带签名的 GLB 地址
  originalImage: { type: String, default: '' },
})
const emit = defineEmits(['error'])

const canvasContainer = ref(null)
const showOriginal = ref(false)
const autoRotate = ref(true)
const loading = ref(true)
const progress = ref(0)
const hasProgress = ref(false)

const progressText = computed(() =>
  hasProgress.value ? `（${Math.round(progress.value)}%）` : '',
)

/* ---------- 设备判定：提示文案要说对话（手机没有"滚轮"） ----------
   hover: none 命中触屏设备（含微信内置浏览器）；
   maxTouchPoints > 0 兜住二合一笔记本用触摸时的场景。 */
const isTouch = ref(false)
const hintText = computed(() =>
  isTouch.value ? '单指拖动旋转 · 双指缩放 · 双击回正' : '拖动旋转 · 滚轮缩放 · 双击回正',
)
const ariaText = computed(() => {
  const gesture = isTouch.value ? '单指拖动旋转、双指缩放' : '拖动旋转、滚轮缩放'
  return `3D 模型，可${gesture}${autoRotate.value ? '，当前自动旋转中' : ''}`
})

/* ---------- Three.js 运行时对象 ---------- */
let scene, camera, renderer, controls, animationId, resizeObserver
let pmremGenerator, envTexture, loadedModel
let initialCameraPos = null

/* ---------- 自动旋转 ---------- */
function toggleAutoRotate() {
  autoRotate.value = !autoRotate.value
  if (controls) controls.autoRotate = autoRotate.value
}

/* ---------- 双击 / 按钮：重置视角 ---------- */
function resetView() {
  if (!controls || !camera || !initialCameraPos) return
  camera.position.copy(initialCameraPos)
  controls.target.set(0, 0, 0)
  controls.update()
}

/* ---------- 3D ⇄ 原图 切换 ---------- */
function toggleOriginal() {
  showOriginal.value = !showOriginal.value
}

/* ---------- 让模型自适应视野：以包围球半径反推相机距离 ---------- */
function fitCameraToModel(object) {
  const box = new THREE.Box3().setFromObject(object)
  if (box.isEmpty()) return
  const size = box.getSize(new THREE.Vector3())
  const center = box.getCenter(new THREE.Vector3())
  const radius = Math.max(size.length() / 2, 0.001)

  // 把模型居中到原点，避免偏心模型转到一半出画
  object.position.sub(center)

  const halfFov = (camera.fov * Math.PI) / 360
  const distance = (radius / Math.sin(halfFov)) * 1.15
  const dir = new THREE.Vector3(0.6, 0.35, 1).normalize()
  camera.position.copy(dir.multiplyScalar(distance))
  camera.lookAt(0, 0, 0)
  initialCameraPos = camera.position.clone()

  camera.near = Math.max(radius / 100, 0.01)
  camera.far = radius * 100
  camera.updateProjectionMatrix()

  controls.minDistance = radius * 0.6
  controls.maxDistance = radius * 6
  controls.target.set(0, 0, 0)
  controls.update()
}

/* ---------- 加载 GLB ---------- */
function loadModel() {
  const loader = new GLTFLoader()
  loader.load(
    props.modelUrl,
    (gltf) => {
      loadedModel = gltf.scene
      // 环境贴图（RoomEnvironment）+ 灯光共同保证 PBR 材质不发黑
      scene.add(loadedModel)
      fitCameraToModel(loadedModel)
      loading.value = false
    },
    (event) => {
      if (event && event.total > 0) {
        hasProgress.value = true
        progress.value = Math.min((event.loaded / event.total) * 100, 100)
      }
    },
    () => {
      // 加载失败（签名过期 / 文件缺失 / 格式不支持）：交给父组件决定降级
      loading.value = false
      emit('error')
    },
  )
}

/* ---------- Three.js 初始化 ---------- */
function initThree() {
  const container = canvasContainer.value
  if (!container || container.clientWidth === 0) return

  try {
    scene = new THREE.Scene()

    const aspect = container.clientWidth / container.clientHeight
    camera = new THREE.PerspectiveCamera(45, aspect, 0.1, 1000)
    camera.position.set(0, 0, 5)

    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setSize(container.clientWidth, container.clientHeight)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1
    // alpha:true + 全透明清屏色：让外层 .visual 的浅绿渐变透上来，与详情页观感一致
    renderer.setClearColor(0x000000, 0)
    container.appendChild(renderer.domElement)

    // 灯光三件套：PBR（MeshStandardMaterial）在无光环境下会整体发黑。
    // 环境贴图提供柔和 IBL，两盏方向光负责主光与补光、塑造体积感。
    scene.add(new THREE.AmbientLight(0xffffff, 0.55))
    const keyLight = new THREE.DirectionalLight(0xffffff, 1.4)
    keyLight.position.set(4, 6, 5)
    scene.add(keyLight)
    const fillLight = new THREE.DirectionalLight(0xffffff, 0.45)
    fillLight.position.set(-5, -1, -4)
    scene.add(fillLight)

    // RoomEnvironment → PMREM：不引入 HDR 文件、零新依赖的标准环境光照方案
    pmremGenerator = new THREE.PMREMGenerator(renderer)
    envTexture = pmremGenerator.fromScene(new RoomEnvironment(), 0.04).texture
    scene.environment = envTexture

    controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controls.enablePan = false
    controls.autoRotate = autoRotate.value
    controls.autoRotateSpeed = 2
    controls.minDistance = 0.5
    controls.maxDistance = 50

    loadModel()
    animate()

    resizeObserver = new ResizeObserver(() => {
      if (!renderer || !camera || !controls || !container) return
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
    loading.value = false
    emit('error')
  }
}

function animate() {
  animationId = requestAnimationFrame(animate)
  // 原图模式下画布不可见：保留 RAF 调度，但不渲染，避免白白占用 GPU
  if (showOriginal.value) return
  controls.update()
  renderer.render(scene, camera)
}

/* ---------- 切换 3D / 原图 的副作用 ---------- */
watch(showOriginal, (val) => {
  if (val) return
  // 切回 3D：容器此前是 display:none（尺寸为 0），需等 DOM 恢复后再同步尺寸
  nextTick(() => {
    if (!renderer || !camera || !canvasContainer.value) return
    const w = canvasContainer.value.clientWidth
    const h = canvasContainer.value.clientHeight
    if (w === 0 || h === 0) return
    camera.aspect = w / h
    camera.updateProjectionMatrix()
    renderer.setSize(w, h)
    renderer.render(scene, camera)
  })
})

/* ---------- 生命周期 ---------- */
onMounted(async () => {
  isTouch.value =
    window.matchMedia?.('(hover: none)').matches || (navigator.maxTouchPoints || 0) > 0
  await nextTick()
  initThree()
})

function disposeSceneAssets() {
  if (!scene) return
  scene.traverse((node) => {
    const geometry = node.geometry
    if (geometry) geometry.dispose()
    const material = node.material
    if (!material) return
    const materials = Array.isArray(material) ? material : [material]
    materials.forEach((item) => {
      // 逐张贴图释放：GLB 的 PBR 贴图组不小，不释放会持续占显存
      Object.values(item).forEach((value) => {
        if (value && value.isTexture) value.dispose()
      })
      item.dispose()
    })
  })
}

onBeforeUnmount(() => {
  if (animationId) {
    cancelAnimationFrame(animationId)
    animationId = null
  }
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  if (controls) {
    controls.dispose()
    controls = null
  }
  disposeSceneAssets()
  if (envTexture) {
    envTexture.dispose()
    envTexture = null
  }
  if (pmremGenerator) {
    pmremGenerator.dispose()
    pmremGenerator = null
  }
  if (renderer) {
    renderer.dispose()
    if (renderer.domElement?.parentNode) {
      renderer.domElement.parentNode.removeChild(renderer.domElement)
    }
    renderer = null
  }
  loadedModel = null
  scene = null
  camera = null
})
</script>

<style scoped>
.model-viewer {
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
  cursor: grab;
  /* 必须是 none：否则触摸端的拖拽手势会被浏览器拿去滚页面，OrbitControls 收不到 */
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

.badge-3d {
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

.loading-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  padding: 0 12%;
  box-sizing: border-box;
  background: rgba(241, 249, 243, 0.72);
  z-index: 2;
}

.loading-text {
  font-size: 14px;
  font-weight: 600;
  color: #1b5e20;
  text-align: center;
}

.progress-track {
  width: 100%;
  max-width: 260px;
  height: 8px;
  border-radius: 999px;
  background: rgba(47, 133, 90, 0.2);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #4caf50, #2e7d32);
  transition: width 0.2s ease;
}

/* 服务端未给 Content-Length 时用不定态动画（避免进度条永远 0%） */
.progress-fill.indeterminate {
  width: 40%;
  animation: model-indeterminate 1.3s ease-in-out infinite;
}

@keyframes model-indeterminate {
  0% { margin-left: -40%; }
  100% { margin-left: 100%; }
}

.original-img {
  flex: 1;
  min-height: 0;
  width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 16px;
  user-select: none;
  pointer-events: none;
}

.controls {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
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

html.mode-elderly .loading-text {
  font-size: 18px;
}

/* 高对比度：画布浮层改黑底白字白描边，保证在浅色 3D 场景上也读得清 */
html.theme-high-contrast .drag-hint,
html.theme-high-contrast .badge-3d {
  background: #000;
  color: #fff;
  border: 2px solid #fff;
}

html.theme-high-contrast .loading-overlay {
  background: rgba(0, 0, 0, 0.85);
}

/* ============================================================
   移动端（≤767px）
   ① 控制条三个按钮需要一手可点：44px 高（iOS HIG 最小值），
      并平分宽度，避免"查看原图/停止旋转/重置视角"折成两行把画布压扁；
   ② 提示条文案已在脚本里按设备切换（手机说"双指缩放"，不说"滚轮"）。
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
    /* 触屏点击不要出现 300ms 延迟与蓝色高亮块 */
    touch-action: manipulation;
    -webkit-tap-highlight-color: transparent;
  }

  .drag-hint {
    bottom: 8px;
    padding: 3px 10px;
    font-size: 11px;
    white-space: nowrap;
  }

  .badge-3d {
    top: 8px;
    right: 8px;
    font-size: 11px;
  }
}

html.theme-high-contrast .loading-text {
  color: #fff;
}
</style>
