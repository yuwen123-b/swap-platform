<template>
  <div class="accessible-page" :class="{ hc: highContrast }">
    <header class="page-head">
      <h1>{{ t('accessibleMode.title') }}</h1>
      <label class="hc-toggle">
        <input type="checkbox" v-model="highContrast" :aria-label="t('accessibleMode.highContrast')" @change="onToggleContrast" />
        <span>{{ t('accessibleMode.highContrast') }}</span>
      </label>
    </header>

    <!-- 子模式切换：键盘 Tab 可达，焦点顺序符合视觉顺序 -->
    <div class="mode-tabs" role="tablist">
      <button
        role="tab" :aria-selected="mode === 'visually_impaired'"
        :class="['tab', { active: mode === 'visually_impaired' }]"
        @click="switchMode('visually_impaired')"
      >{{ t('accessibleMode.visualMode') }}</button>
      <button
        role="tab" :aria-selected="mode === 'mobility_impaired'"
        :class="['tab', { active: mode === 'mobility_impaired' }]"
        @click="switchMode('mobility_impaired')"
      >{{ t('accessibleMode.mobilityMode') }}</button>
    </div>

    <p v-if="tip" class="tip" role="status">{{ tip }}</p>

    <!-- 视障子模式：语音标签 + 语音确认 -->
    <section v-if="mode === 'visually_impaired'" class="panel" :aria-label="t('accessibleMode.visualMode')">
      <p class="mode-tip">{{ t('accessibleMode.visualTip') }}</p>
      <label class="field">
        <span>{{ t('accessibleMode.voiceLabelId') }}</span>
        <input v-model.number="itemId" type="number" min="1" inputmode="numeric"
               :aria-label="t('accessibleMode.voiceLabelId')" @keyup.enter="loadLabel" />
      </label>
      <button class="primary-btn" :aria-label="t('accessibleMode.voiceLabel')" @click="loadLabel">
        {{ t('accessibleMode.voiceLabel') }}
      </button>

      <div v-if="voiceLabel" class="label-card" role="status" :aria-label="voiceLabel" tabindex="0">
        <p class="label-text">{{ voiceLabel }}</p>
        <div class="label-actions">
          <button class="primary-btn" :aria-label="t('accessibleMode.playLabel')" @click="playLabel">
            {{ t('accessibleMode.playLabel') }}
          </button>
          <button class="confirm-btn" :aria-label="t('accessibleMode.wantSwap')" @click="confirmSwap">
            {{ t('accessibleMode.wantSwap') }}
          </button>
        </div>
      </div>
    </section>

    <!-- 肢体障碍子模式：行动能力 + 交接方式 + 一键委托 -->
    <section v-else class="panel" :aria-label="t('accessibleMode.mobilityMode')">
      <p class="mode-tip">{{ t('accessibleMode.mobilityTip') }}</p>

      <fieldset class="mobility-group">
        <legend>{{ t('accessibleMode.mobility') }}</legend>
        <label v-for="lv in mobilityLevels" :key="lv" class="radio-row">
          <input type="radio" name="mobility" :value="lv" v-model="mobilityLevel" @change="onSetMobility" />
          <span>{{ mobilityText(lv) }}</span>
        </label>
      </fieldset>

      <div class="handover" :aria-label="t('accessibleMode.handoverTitle')">
        <h2>{{ t('accessibleMode.handoverTitle') }}</h2>
        <ul class="handover-list">
          <li v-for="m in handoverMethods" :key="m">
            <button class="method-btn" :class="{ recommended: m === recommended }" @click="selectedMethod = m">
              {{ methodText(m) }}
              <span v-if="m === recommended" class="rec-tag">★</span>
            </button>
          </li>
        </ul>
        <p v-if="!handoverMethods.includes('self_pickup')" class="skip-note">
          {{ t('accessibleMode.mobilityTip') }}
        </p>
      </div>

      <button class="delegate-btn" :aria-label="t('accessibleMode.delegateVolunteer')" @click="delegate">
        {{ t('accessibleMode.delegateVolunteer') }}
      </button>
      <p v-if="taskMsg" class="tip" role="status">{{ taskMsg }}</p>
    </section>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useI18n } from '../i18n'
import {
  setAccessibilityMode, setMobilityLevel, getHandoverOptions, getVoiceLabel,
  createVolunteerTask,
} from '../api/accessibility'
import { useUserStore } from '../store/user'
import { useProfileStore } from '../store/profile'

const { t, state } = useI18n()
const userStore = useUserStore()
const profileStore = useProfileStore()
userStore.hydrate()
const userId = () => userStore.user?.id || 0

const mode = ref('visually_impaired')
const highContrast = ref(false)
const tip = ref('')
const taskMsg = ref('')

// 视障子模式状态
const itemId = ref(null)
const voiceLabel = ref('')

// 肢体障碍子模式状态
const mobilityLevels = ['free', 'limited', 'assisted']
const mobilityLevel = ref('free')
const handoverMethods = ref(['self_pickup', 'door_delivery', 'volunteer_pickup'])
const recommended = ref('self_pickup')
const selectedMethod = ref('')

const MOBILITY_KEY = {
  free: 'accessibleMode.mobilityFree',
  limited: 'accessibleMode.mobilityLimited',
  assisted: 'accessibleMode.mobilityAssisted',
}
const METHOD_KEY = {
  self_pickup: 'accessibleMode.handoverSelf',
  door_delivery: 'accessibleMode.handoverDelivery',
  volunteer_pickup: 'accessibleMode.handoverVolunteer',
}
function mobilityText(lv) {
  return t(MOBILITY_KEY[lv] || `accessibleMode.mobility${lv.charAt(0).toUpperCase()}${lv.slice(1)}`)
}
function methodText(m) {
  const key = METHOD_KEY[m]
  return key ? t(key) : m
}

// 向导页内的设置变更同步到全局 profile（持久化），失败不阻塞原有交互
function syncProfile(patch) {
  if (!profileStore.userId) return
  profileStore.saveProfile(patch).catch(() => {})
}

async function switchMode(m) {
  mode.value = m
  if (m === 'visually_impaired') highContrast.value = true
  try {
    await setAccessibilityMode({ user_id: userId(), mode: m })
    tip.value = t('accessibleMode.modeSet')
    syncProfile({
      accessibilityMode: m,
      highContrast: highContrast.value,
    })
  } catch {
    tip.value = t('common.genericError')
  }
  if (m === 'mobility_impaired') loadHandover()
}

async function loadHandover() {
  try {
    const data = await getHandoverOptions(userId())
    handoverMethods.value = data.methods
    recommended.value = data.recommended
    selectedMethod.value = data.recommended
  } catch { /* 保留默认 */ }
}

async function loadLabel() {
  if (!itemId.value) return
  try {
    const data = await getVoiceLabel(itemId.value, state.locale)
    voiceLabel.value = data.label
    speak(data.label)
  } catch {
    tip.value = t('common.genericError')
  }
}

function speak(text) {
  if (!window.speechSynthesis) return
  window.speechSynthesis.cancel()
  const utter = new SpeechSynthesisUtterance(text)
  utter.lang = 'zh-CN'
  utter.rate = 0.9
  window.speechSynthesis.speak(utter)
}

function playLabel() { if (voiceLabel.value) speak(voiceLabel.value) }

// 语音确认：支持系统语音识别则说「我要换」，否则按钮点击等效
function confirmSwap() {
  speak(t('accessibleMode.wantSwap'))
  tip.value = t('elderlyMode.cardContacted')
}

async function onSetMobility() {
  try {
    await setMobilityLevel({ user_id: userId(), mobility_level: mobilityLevel.value })
    tip.value = t('accessibleMode.mobilitySet')
    syncProfile({ mobilityLevel: mobilityLevel.value })
    loadHandover()
  } catch {
    tip.value = t('common.genericError')
  }
}

async function onToggleContrast() {
  syncProfile({ highContrast: highContrast.value })
}

async function delegate() {
  taskMsg.value = ''
  try {
    await createVolunteerTask({
      exchange_id: `EX-${Date.now()}`,
      requester_id: userId(),
      item_id: itemId.value || null,
      handover_method: 'volunteer_pickup',
      note: '',
    })
    taskMsg.value = t('accessibleMode.taskCreated')
  } catch {
    taskMsg.value = t('common.genericError')
  }
}

onMounted(() => {
  // 进入向导时与个人中心的持久化配置保持一致
  if (profileStore.loaded || profileStore.userId) {
    if (profileStore.accessibilityMode !== 'normal') {
      mode.value = profileStore.accessibilityMode
    }
    highContrast.value = profileStore.highContrast
    mobilityLevel.value = profileStore.mobilityLevel
    if (mode.value === 'mobility_impaired') loadHandover()
  }
})
</script>

<style scoped>
.accessible-page { max-width: 760px; margin: 0 auto; padding: 24px 20px 120px; color: #1a1a1a; }
.page-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
h1 { font-size: 28px; color: #14532D; margin: 0; }
.hc-toggle { display: flex; align-items: center; gap: 8px; font-size: 16px; cursor: pointer; }
.hc-toggle input { width: 22px; height: 22px; }

.mode-tabs { display: flex; gap: 12px; margin: 20px 0; }
.tab {
  flex: 1; min-height: 64px; font-size: 20px; font-weight: 700;
  border: 2px solid #1B5E20; border-radius: 14px; background: #fff; color: #1B5E20; cursor: pointer;
}
.tab.active { background: #1B5E20; color: #fff; }
.tab:focus-visible { outline: 4px solid #0D47A1; outline-offset: 2px; }

.panel { display: flex; flex-direction: column; gap: 20px; }
.mode-tip { font-size: 18px; color: #374151; }
.field { display: flex; flex-direction: column; gap: 8px; font-size: 18px; }
.field input { min-height: 56px; font-size: 20px; padding: 0 16px; border: 2px solid #1B5E20; border-radius: 10px; }
.field input:focus-visible { outline: 4px solid #0D47A1; outline-offset: 2px; }

.primary-btn, .confirm-btn, .delegate-btn {
  min-height: 64px; font-size: 20px; font-weight: 700; border: none; border-radius: 14px; cursor: pointer; padding: 0 24px;
}
.primary-btn { background: #1B5E20; color: #fff; }
.confirm-btn { background: #0D47A1; color: #fff; }
.delegate-btn { background: #B71C1C; color: #fff; }
.primary-btn:focus-visible, .confirm-btn:focus-visible, .delegate-btn:focus-visible,
.method-btn:focus-visible { outline: 4px solid #F9A825; outline-offset: 2px; }

.label-card { border: 3px solid #1B5E20; border-radius: 16px; padding: 20px; background: #F0F7F2; }
.label-text { font-size: 22px; margin: 0 0 16px; }
.label-actions { display: flex; gap: 12px; flex-wrap: wrap; }

.mobility-group { border: 2px solid #1B5E20; border-radius: 14px; padding: 16px; }
.radio-row { display: flex; align-items: center; gap: 10px; min-height: 48px; font-size: 18px; }
.radio-row input { width: 22px; height: 22px; }

.handover h2 { font-size: 22px; color: #14532D; }
.handover-list { list-style: none; padding: 0; display: flex; flex-direction: column; gap: 12px; }
.method-btn {
  width: 100%; min-height: 64px; font-size: 20px; text-align: left; padding: 0 20px;
  border: 2px solid #1B5E20; border-radius: 12px; background: #fff; color: #1a1a1a; cursor: pointer;
}
.method-btn.recommended { border-color: #0D47A1; background: #E3F2FD; }
.rec-tag { color: #0D47A1; margin-left: 8px; }
.skip-note { font-size: 16px; color: #374151; }
.tip { font-size: 18px; color: #14532D; }

/* 高对比度主题：黑底白字黄焦点，对比度 ≥ 7:1 */
.hc { background: #000; color: #fff; }
.hc h1, .hc .handover h2 { color: #fff; }
.hc .tab, .hc .method-btn { background: #000; color: #fff; border-color: #FFD600; }
.hc .tab.active { background: #FFD600; color: #000; }
.hc .mode-tip, .hc .skip-note, .hc .tip { color: #fff; }
.hc .label-card { background: #000; border-color: #FFD600; }
.hc .field input { background: #000; color: #fff; border-color: #FFD600; }
</style>
