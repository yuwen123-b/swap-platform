<template>
  <div class="pano-viewer">
    <!-- 查看区：四视角切换，支持拖拽/触摸滑动 -->
    <div
      class="stage"
      role="img"
      :aria-label="t('panorama.ariaStage', { tip: t('panorama.dragTip'), view: viewLabel(currentName) })"
      tabindex="0"
      @pointerdown="onDragStart"
      @pointermove="onDragMove"
      @pointerup="onDragEnd"
      @pointercancel="onDragEnd"
      @keydown.left.prevent="step(-1)"
      @keydown.right.prevent="step(1)"
    >
      <template v-if="!showOriginal">
        <img
          v-for="(url, name) in orderedViews" :key="name"
          v-show="name === currentName"
          class="view-img"
          :src="url"
          :alt="viewLabel(name)"
          draggable="false"
        />
        <span class="drag-hint" aria-hidden="true">⟵ ⟶ {{ t('panorama.dragTip') }}</span>
      </template>
      <img v-else class="view-img" :src="originalImage" :alt="t('panorama.viewOriginal')" draggable="false" />
    </div>

    <!-- 控制条：自动旋转 / 查看原图 -->
    <div class="controls">
      <button type="button" class="ctl-btn" :aria-label="autoPlaying ? t('panorama.stop') : t('panorama.autoPlay')" @click="toggleAuto">
        {{ autoPlaying ? '⏸' : '▶' }} {{ autoPlaying ? t('panorama.stop') : t('panorama.autoPlay') }}
      </button>
      <button type="button" class="ctl-btn" :aria-label="showOriginal ? t('panorama.view360') : t('panorama.viewOriginal')" @click="showOriginal = !showOriginal">
        {{ showOriginal ? t('panorama.view360') : t('panorama.viewOriginal') }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { useI18n } from '../i18n'

const props = defineProps({
  views: { type: Object, required: true }, // { front, left, back, right }
  originalImage: { type: String, default: '' },
})
const { t } = useI18n()

// 固定视角顺序：front → right → back → left（每 3 秒转 90°）
const ORDER = ['front', 'right', 'back', 'left']
const orderedViews = computed(() => {
  const out = {}
  for (const name of ORDER) if (props.views[name]) out[name] = props.views[name]
  return out
})

const currentIndex = ref(0)
const currentName = computed(() => ORDER[currentIndex.value])
const showOriginal = ref(false)
const autoPlaying = ref(false)
let autoTimer = null
let dragX = null

function viewLabel(name) {
  const key = `panorama.${name}`
  const text = t(key)
  return text === key ? name : text
}

function step(dir) {
  const count = ORDER.length
  currentIndex.value = (currentIndex.value + dir + count) % count
}

function toggleAuto() {
  autoPlaying.value = !autoPlaying.value
  if (autoPlaying.value) {
    autoTimer = setInterval(() => step(1), 3000)
  } else {
    clearInterval(autoTimer)
  }
}

function onDragStart(e) {
  dragX = e.clientX
  e.currentTarget.setPointerCapture?.(e.pointerId)
}

function onDragMove(e) {
  if (dragX === null) return
  const delta = e.clientX - dragX
  if (Math.abs(delta) > 60) {
    step(delta < 0 ? 1 : -1)
    dragX = e.clientX
  }
}

function onDragEnd() { dragX = null }

onBeforeUnmount(() => clearInterval(autoTimer))
</script>

<style scoped>
.pano-viewer { display: flex; flex-direction: column; gap: 12px; }
.stage {
  position: relative; width: 100%; aspect-ratio: 4 / 3; overflow: hidden;
  border-radius: 16px; background: #0f2416; cursor: grab; touch-action: pan-y;
}
.stage:active { cursor: grabbing; }
.stage:focus-visible { outline: 3px solid #2f855a; outline-offset: 2px; }
.view-img {
  width: 100%; height: 100%; object-fit: contain;
  user-select: none; pointer-events: none;
}
.drag-hint {
  position: absolute; bottom: 10px; left: 50%; transform: translateX(-50%);
  padding: 4px 14px; border-radius: 999px; font-size: 13px;
  color: #fff; background: rgba(0, 0, 0, 0.45); pointer-events: none;
}
.controls { display: flex; gap: 10px; }
.ctl-btn {
  min-height: 40px; padding: 0 16px; font-size: 14px; font-weight: 600;
  border: 1px solid rgba(47, 133, 90, 0.4); border-radius: 10px;
  background: #fff; color: #1B5E20; cursor: pointer;
}
.ctl-btn:hover { background: #ecfdf5; }
.ctl-btn:focus-visible { outline: 3px solid #2f855a; outline-offset: 2px; }
</style>
