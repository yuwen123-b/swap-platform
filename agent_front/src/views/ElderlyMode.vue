<template>
  <div class="elderly-page">
    <h1 class="page-title">{{ t('elderlyMode.title') }}</h1>
    <p class="page-subtitle">{{ t('elderlyMode.subtitle') }}</p>

    <!-- 结果区：三态卡片 -->
    <section class="result-area" aria-live="polite">
      <ElderlyCard v-if="card" :card="card" @view-item="goItem" />
      <p v-else class="empty-tip">{{ t('elderlyMode.empty') }}</p>

      <p v-if="heardText" class="heard">{{ t('elderlyMode.heard') }}：{{ heardText }}</p>
      <p v-if="replyText" class="reply">{{ replyText }}</p>
      <p v-if="errorTip" class="error-tip" role="alert">{{ errorTip }}</p>
    </section>

    <!-- 输入区：按住说话 + 文字兜底 -->
    <VoiceInput @audio="onAudio" @text="onText" />

    <!-- 右下角固定：呼叫子女/志愿者 -->
    <button
      class="help-btn"
      type="button"
      :aria-label="t('elderlyMode.callHelp')"
      @click="onCallHelp"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z"/>
      </svg>
      <span>{{ t('elderlyMode.callHelp') }}</span>
    </button>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import VoiceInput from '../components/VoiceInput.vue'
import ElderlyCard from '../components/ElderlyCard.vue'
import { elderlyInteract, callHelp } from '../api/elderly'
import { useI18n } from '../i18n'
import { useUserStore } from '../store/user'

const { t, state } = useI18n()
const router = useRouter()
const userStore = useUserStore()
userStore.hydrate()

const card = ref(null)
const heardText = ref('')
const replyText = ref('')
const errorTip = ref('')

const userId = () => userStore.user?.id || 0

// 语音播报：Web Speech API，按后端返回的分句/语速/音色
function speak(speech) {
  if (!speech || !window.speechSynthesis) return
  window.speechSynthesis.cancel()
  const sentences = speech.sentences?.length ? speech.sentences : [speech.text]
  for (const s of sentences) {
    const utter = new SpeechSynthesisUtterance(s)
    utter.lang = speech.voice || 'zh-CN'
    utter.rate = speech.rate || 0.8
    window.speechSynthesis.speak(utter)
  }
}

async function send(formData) {
  errorTip.value = ''
  try {
    const data = await elderlyInteract(formData)
    heardText.value = data.action_result?.heard_text || ''
    replyText.value = data.response_text || ''
    card.value = data.action_result?.card || null
    speak(data.action_result?.speech)
    const action = data.action_result?.action
    if (action?.type === 'navigate' && action.path) router.push(action.path)
  } catch (err) {
    if (err?.response?.status === 503) {
      errorTip.value = t('elderlyMode.asrUnavailable')
    } else {
      errorTip.value = t('common.genericError')
    }
  }
}

function onAudio(blob) {
  const fd = new FormData()
  fd.append('audio', blob, 'recording.webm')
  fd.append('user_id', String(userId()))
  fd.append('lang', state.locale)
  send(fd)
}

function onText(text) {
  const fd = new FormData()
  fd.append('text', text)
  fd.append('user_id', String(userId()))
  fd.append('lang', state.locale)
  send(fd)
}

async function onCallHelp() {
  errorTip.value = ''
  try {
    await callHelp({ user_id: userId(), context: heardText.value || replyText.value, lang: state.locale })
    replyText.value = t('elderlyMode.helpCalled')
    card.value = { status: 'contacted', label: t('elderlyMode.cardContacted') }
    speak({ text: t('elderlyMode.helpCalled'), sentences: [t('elderlyMode.helpCalled')], rate: 0.8, voice: 'zh-CN' })
  } catch {
    errorTip.value = t('common.genericError')
  }
}

function goItem(id) {
  router.push(`/items/${id}`)
}
</script>

<style scoped>
.elderly-page {
  min-height: calc(100vh - 120px);
  padding: 32px 24px 220px;
  display: flex; flex-direction: column; align-items: center; gap: 36px;
  font-size: 26px; color: #1a1a1a; background: #F0F7F2;
}
.page-title { font-size: 40px; font-weight: 800; margin: 0; color: #14532D; }
.page-subtitle { font-size: 26px; margin: 0; color: #374151; }

.result-area { width: 100%; max-width: 640px; display: flex; flex-direction: column; gap: 16px; align-items: stretch; }
.empty-tip { font-size: 24px; color: #374151; text-align: center; }
.heard { font-size: 24px; color: #374151; margin: 0; }
.reply { font-size: 28px; font-weight: 700; color: #14532D; margin: 0; }
.error-tip { font-size: 24px; color: #B71C1C; margin: 0; }

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
</style>
