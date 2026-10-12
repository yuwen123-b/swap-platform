<template>
  <div class="voice-input">
    <!-- 按住说话按钮：高度 ≥80px、字号 ≥24px、图标必配文字 -->
    <button
      class="talk-btn"
      :class="{ recording }"
      type="button"
      :aria-label="recording ? '松开 发送' : '按住 说话'"
      @pointerdown.prevent="startRecord"
      @pointerup.prevent="stopRecord"
      @pointerleave="cancelIfRecording"
      @keydown.space.prevent="startRecord"
      @keyup.space.prevent="stopRecord"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <rect x="9" y="2" width="6" height="12" rx="3" />
        <path d="M5 10v1a7 7 0 0 0 14 0v-1" />
        <path d="M12 18v4" />
      </svg>
      <span>{{ recording ? '正在录音，松开发送' : '按住 说话' }}</span>
    </button>

    <!-- 文字兜底：ASR 不可用或用户偏好打字 -->
    <form class="text-row" @submit.prevent="submitText">
      <input
        v-model="text"
        class="text-input"
        type="text"
        placeholder="也可以在这里打字，比如：我想换电饭煲"
        aria-label="也可以在这里打字，比如：我想换电饭煲"
      />
      <button class="send-btn" type="submit" aria-label="发送">发送</button>
    </form>
  </div>
</template>

<script setup>
import { onBeforeUnmount, ref } from 'vue'

const emit = defineEmits(['audio', 'text'])

const recording = ref(false)
const text = ref('')
let mediaRecorder = null
let chunks = []

async function startRecord() {
  if (recording.value) return
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    chunks = []
    mediaRecorder = new MediaRecorder(stream)
    mediaRecorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data) }
    mediaRecorder.onstop = () => {
      stream.getTracks().forEach((tr) => tr.stop())
      const blob = new Blob(chunks, { type: mediaRecorder.mimeType || 'audio/webm' })
      if (blob.size > 0) emit('audio', blob)
    }
    mediaRecorder.start()
    recording.value = true
  } catch {
    // 麦克风不可用：静默降级到文字输入
    recording.value = false
  }
}

function stopRecord() {
  if (!recording.value || !mediaRecorder) return
  recording.value = false
  mediaRecorder.stop()
}

function cancelIfRecording() {
  // 手指滑出按钮区域：取消本次录音，不发送
  if (recording.value && mediaRecorder) {
    mediaRecorder.ondataavailable = null
    mediaRecorder.onstop = () => mediaRecorder?.stream?.getTracks?.().forEach((tr) => tr.stop())
    recording.value = false
    mediaRecorder.stop()
  }
}

function submitText() {
  const value = text.value.trim()
  if (!value) return
  emit('text', value)
  text.value = ''
}

onBeforeUnmount(() => { if (mediaRecorder?.state === 'recording') mediaRecorder.stop() })
</script>

<style scoped>
.voice-input { display: flex; flex-direction: column; gap: 20px; align-items: center; width: 100%; }

.talk-btn {
  display: flex; align-items: center; justify-content: center; gap: 16px;
  width: 100%; max-width: 560px; min-height: 96px;
  font-size: 28px; font-weight: 700;
  color: #ffffff; background: #1B5E20; /* 白字对比度 ≥ 4.5:1 */
  border: none; border-radius: 24px; cursor: pointer;
  box-shadow: 0 10px 24px rgba(27, 94, 32, 0.35);
  touch-action: none; user-select: none;
}
.talk-btn svg { width: 36px; height: 36px; }
.talk-btn.recording { background: #B71C1C; }
.talk-btn:focus-visible { outline: 4px solid #0D47A1; outline-offset: 3px; }

.text-row { display: flex; gap: 12px; width: 100%; max-width: 560px; }
.text-input {
  flex: 1; min-height: 80px; font-size: 24px; padding: 0 20px;
  border: 3px solid #1B5E20; border-radius: 16px; color: #1a1a1a; background: #fff;
}
.text-input:focus-visible { outline: 4px solid #0D47A1; outline-offset: 2px; }
.send-btn {
  min-height: 80px; min-width: 120px; font-size: 24px; font-weight: 700;
  color: #fff; background: #0D47A1; border: none; border-radius: 16px; cursor: pointer;
}
.send-btn:focus-visible { outline: 4px solid #1B5E20; outline-offset: 3px; }
</style>
