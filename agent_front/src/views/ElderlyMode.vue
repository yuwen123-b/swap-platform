<template>
  <div class="elderly-page">
    <h1 class="page-title">助老模式</h1>
    <p class="page-subtitle">按住说话，我来帮您</p>

    <!-- 结果区：三态卡片 -->
    <section class="result-area" aria-live="polite">
      <!-- 我听到的是：独立卡片，让老人确认「系统真的听懂了」 -->
      <div v-if="heardText" class="heard-card">
        <span class="heard-label">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
            <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
            <path d="M12 19v4" />
          </svg>
          我听到您说
        </span>
        <p class="heard-text">{{ heardText }}</p>
      </div>

      <!-- 等待后端识别与回答：有明显动效，不是静止的空白 -->
      <div v-if="busy" class="thinking-row" role="status">
        <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
        <span>正在思考，请稍等…</span>
      </div>

      <p v-if="replyText" class="reply">{{ replyText }}</p>

      <ElderlyCard v-if="card" :card="card" @view-item="goItem" />

      <!-- 播报反馈：从「拿到音频」到「真正出声」之间也有提示 -->
      <div v-if="speaking" class="speaking-row" role="status">
        <span class="bars" aria-hidden="true"><i></i><i></i><i></i></span>
        <span>{{ speakTip }}</span>
      </div>

      <!-- 兜底入口：iOS/微信里自动播报常被拦，点一下就是「用户手势」，必定能出声 -->
      <button v-if="canReplay" class="replay-btn" type="button" @click="replay">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M11 5 6 9H2v6h4l5 4V5z" />
          <path d="M15.5 8.5a5 5 0 0 1 0 7" />
          <path d="M18.5 5.5a9 9 0 0 1 0 13" />
        </svg>
        再听一遍
      </button>

      <p v-if="errorTip" class="error-tip" role="alert">{{ errorTip }}</p>
      <p v-if="!card && !heardText && !busy && !replyText" class="empty-tip">您可以说：我想换电饭煲</p>
    </section>

    <!-- 输入区：按住说话 + 文字兜底 -->
    <VoiceInput :busy="busy" @press="onPress" @audio="onAudio" @text="onText" />

    <!-- 右下角固定：呼叫子女/志愿者 -->
    <button
      class="help-btn"
      type="button"
      aria-label="呼叫子女/志愿者"
      @click="onCallHelp"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z"/>
      </svg>
      <span>呼叫子女/志愿者</span>
    </button>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import VoiceInput from '../components/VoiceInput.vue'
import ElderlyCard from '../components/ElderlyCard.vue'
import { elderlyInteract, callHelp } from '../api/elderly'
import { useUserStore } from '../store/user'
import { tts, ttsState } from '../utils/tts'

const router = useRouter()
const userStore = useUserStore()
userStore.hydrate()

const card = ref(null)
const heardText = ref('')
const replyText = ref('')
const errorTip = ref('')

// 正在等后端（识别 + 意图 + 合成）：驱动「正在思考」与按钮禁用
const busy = ref(false)
// 上一轮播报内容：留给「再听一遍」用
const lastSpeech = ref(null)
const lastAudioUrl = ref('')

const speaking = computed(
  () => ttsState.status === 'loading' || ttsState.status === 'playing',
)
const speakTip = computed(() => {
  if (ttsState.status === 'loading') return '正在准备语音…'
  return ttsState.mode === 'browser' ? '正在用手机朗读…' : '正在播报…'
})
const canReplay = computed(() => !!lastSpeech.value && !busy.value && !speaking.value)

const userId = () => userStore.user?.id || 0

function playReply(speech, audioUrl) {
  if (!speech?.text) return
  lastSpeech.value = speech
  lastAudioUrl.value = audioUrl || ''
  // 后端音频优先；被拦截/失败/超时都会自动降级为浏览器本地播报（见 utils/tts.js）
  tts.speak(speech, audioUrl || '')
}

// 按 Blob 的真实 MIME 选扩展名：Chrome 新版 MediaRecorder 产出 audio/mp4，
// 旧代码一律写成 recording.webm，服务端落盘后文件名与内容不一致，排查时极易误判。
function audioFilename(blob) {
  const type = (blob?.type || '').toLowerCase()
  if (type.includes('mp4') || type.includes('m4a')) return 'recording.m4a'
  if (type.includes('mpeg') || type.includes('mp3')) return 'recording.mp3'
  if (type.includes('ogg')) return 'recording.ogg'
  if (type.includes('wav')) return 'recording.wav'
  return 'recording.webm'
}

async function send(formData) {
  if (busy.value) return
  busy.value = true
  errorTip.value = ''
  heardText.value = ''
  try {
    const data = await elderlyInteract(formData)
    heardText.value = data.action_result?.heard_text || ''
    replyText.value = data.response_text || ''
    card.value = data.action_result?.card || null
    playReply(data.action_result?.speech, data.response_audio_url)
    const action = data.action_result?.action
    if (action?.type === 'navigate' && action.path) router.push(action.path)
  } catch (err) {
    if (err?.response?.status === 503) {
      errorTip.value = '语音识别暂不可用，请改用文字输入'
    } else {
      errorTip.value = '操作失败，请稍后再试'
    }
  } finally {
    busy.value = false
  }
}

function onAudio(blob) {
  const fd = new FormData()
  fd.append('audio', blob, audioFilename(blob))
  fd.append('user_id', String(userId()))
  fd.append('lang', 'zh')
  send(fd)
}

function onText(text) {
  const fd = new FormData()
  fd.append('text', text)
  fd.append('user_id', String(userId()))
  fd.append('lang', 'zh')
  send(fd)
}

// 按下说话：必须在手势的同一个调用栈里解锁音频（iOS 只认手势内的 play），
// 同时停掉上一轮播报，避免喇叭盖住麦克风。
function onPress() {
  tts.stop()
  tts.unlock()
}

function replay() {
  if (!lastSpeech.value) return
  tts.unlock() // 点击本身也是手势：先解锁，再播
  tts.speak(lastSpeech.value, lastAudioUrl.value)
}

async function onCallHelp() {
  errorTip.value = ''
  try {
    await callHelp({ user_id: userId(), context: heardText.value || replyText.value, lang: 'zh' })
    replyText.value = '已通知您的紧急联系人'
    card.value = { status: 'contacted', label: '已帮您联系' }
    playReply(
      { text: '已通知您的紧急联系人', sentences: ['已通知您的紧急联系人'], rate: 0.8, voice: 'zh-CN' },
      '',
    )
  } catch {
    errorTip.value = '操作失败，请稍后再试'
  }
}

function goItem(id) {
  router.push(`/items/${id}`)
}

onBeforeUnmount(() => tts.stop())
</script>

<style scoped>
.elderly-page {
  min-height: calc(100vh - 120px);
  padding: 32px 24px 220px;
  display: flex; flex-direction: column; align-items: center; gap: 32px;
  font-size: 26px; color: #1a1a1a; background: #F0F7F2;
}
.page-title { font-size: 40px; font-weight: 800; margin: 0; color: #14532D; }
.page-subtitle { font-size: 26px; margin: 0; color: #374151; }

.result-area { width: 100%; max-width: 640px; display: flex; flex-direction: column; gap: 16px; align-items: stretch; }
.empty-tip { font-size: 24px; color: #374151; text-align: center; }
.reply { font-size: 28px; font-weight: 700; color: #14532D; margin: 0; }
.error-tip { font-size: 24px; color: #B71C1C; margin: 0; }

/* 「我听到您说」：白底 + 左侧色条，比正文重、比结果轻，一眼看到「听懂了什么」 */
.heard-card {
  display: flex; flex-direction: column; gap: 8px;
  padding: 16px 20px;
  background: #ffffff;
  border-left: 8px solid #1B5E20;
  border-radius: 16px;
  box-shadow: 0 4px 14px rgba(20, 83, 45, 0.1);
}
.heard-label {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 20px; font-weight: 700; color: #4B5563;
}
.heard-label svg { width: 22px; height: 22px; }
.heard-text {
  margin: 0;
  font-size: 30px; font-weight: 800; line-height: 1.35; color: #14532D;
  word-break: break-word;
}

/* 思考态：三个跳动圆点 + 文案 */
.thinking-row {
  display: flex; align-items: center; gap: 12px;
  font-size: 24px; color: #374151;
}
.dots, .bars { display: inline-flex; align-items: center; gap: 6px; }
.dots i {
  width: 10px; height: 10px; border-radius: 50%; background: #1B5E20;
  animation: dot-bounce 1.2s ease-in-out infinite;
}
.dots i:nth-child(2) { animation-delay: .16s; }
.dots i:nth-child(3) { animation-delay: .32s; }
@keyframes dot-bounce {
  0%, 80%, 100% { transform: translateY(0); opacity: .45; }
  40% { transform: translateY(-8px); opacity: 1; }
}

/* 播报态：音量条上下跳动，提示「真的在出声」，无声时也能看出差别 */
.speaking-row {
  display: flex; align-items: center; gap: 12px;
  font-size: 22px; color: #0D47A1;
}
.bars i {
  width: 6px; height: 10px; border-radius: 3px; background: #0D47A1;
  animation: bar-bounce .9s ease-in-out infinite;
}
.bars i:nth-child(2) { animation-delay: .15s; }
.bars i:nth-child(3) { animation-delay: .3s; }
@keyframes bar-bounce {
  0%, 100% { height: 8px; }
  50% { height: 22px; }
}

.replay-btn {
  align-self: flex-start;
  display: inline-flex; align-items: center; gap: 10px;
  min-height: 64px; padding: 0 22px;
  font-size: 24px; font-weight: 700;
  color: #0D47A1; background: #ffffff;
  border: 3px solid #0D47A1; border-radius: 16px; cursor: pointer;
  -webkit-user-select: none; user-select: none;
}
.replay-btn svg { width: 28px; height: 28px; }
.replay-btn:focus-visible { outline: 4px solid #1B5E20; outline-offset: 3px; }

.help-btn {
  position: fixed; right: 24px; bottom: 24px; z-index: 70;
  display: flex; align-items: center; gap: 12px;
  min-height: 88px; padding: 0 28px;
  font-size: 26px; font-weight: 700;
  color: #fff; background: #B71C1C; border: none; border-radius: 24px; cursor: pointer;
  box-shadow: 0 10px 26px rgba(183, 28, 28, 0.4);
}
.help-btn svg { width: 32px; height: 32px; }
.help-btn:focus-visible { outline: 4px solid #0D47A1; outline-offset: 3px; }

@media (prefers-reduced-motion: reduce) {
  .dots i, .bars i { animation: none; }
}

/* 窄屏：结果区贴边一点，别让 24px 内边距挤掉内容宽度 */
@media (max-width: 767px) {
  .elderly-page { padding: 20px 16px 200px; gap: 24px; }
  .page-title { font-size: 34px; }
  .page-subtitle { font-size: 22px; }
  .heard-text { font-size: 26px; }
  .reply { font-size: 25px; }
  .help-btn { min-height: 76px; padding: 0 20px; font-size: 22px; border-radius: 20px; }
  .help-btn svg { width: 26px; height: 26px; }
}
</style>
