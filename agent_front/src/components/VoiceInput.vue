<template>
  <div class="voice-input">
    <!-- 按住说话按钮：高度 ≥80px、字号 ≥24px、图标必配文字 -->
    <button
      ref="btnRef"
      class="talk-btn"
      :class="{
        'is-opening': phase === 'opening',
        'is-recording': phase === 'recording',
        'is-canceling': phase === 'recording' && willCancel,
        'is-thinking': busy,
      }"
      type="button"
      :disabled="busy"
      :aria-label="btnText"
      :aria-busy="busy ? 'true' : 'false'"
      @touchstart.prevent="onTouchStart"
      @touchmove="onTouchMove"
      @touchend.prevent="onTouchEnd"
      @touchcancel.prevent="onTouchCancel"
      @pointerdown="onPointerDown"
      @pointerup="onPointerUp"
      @pointerleave="onPointerLeave"
      @pointercancel="onPointerCancel"
      @contextmenu.prevent
      @dragstart.prevent
      @selectstart.prevent
      @keydown.space.prevent="onKeyDown"
      @keyup.space.prevent="onKeyUp"
    >
      <!-- 录音水波纹：只在按下录音时启动，纯装饰 -->
      <span class="ripple" aria-hidden="true"></span>

      <span class="btn-icon" aria-hidden="true">
        <svg
          v-if="busy"
          class="spin"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2.4"
          stroke-linecap="round"
        >
          <path d="M12 3a9 9 0 1 0 9 9" />
        </svg>
        <svg
          v-else
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <rect x="9" y="2" width="6" height="12" rx="3" />
          <path d="M5 10v1a7 7 0 0 0 14 0v-1" />
          <path d="M12 18v4" />
        </svg>
      </span>
      <span class="btn-text">{{ btnText }}</span>
    </button>

    <!-- 录音时的提示条：老人看不清颜色变化，再给一句明确的操作说明 -->
    <p v-if="phase === 'recording'" class="rec-tip" :class="{ 'is-cancel': willCancel }">
      {{ willCancel ? '松手将取消这次录音' : '说完再松手，我在听' }}
    </p>

    <!-- 文字兜底：ASR 不可用或用户偏好打字 -->
    <form class="text-row" @submit.prevent="submitText">
      <input
        v-model="text"
        class="text-input"
        type="text"
        placeholder="也可以在这里打字，比如：我想换电饭煲"
        aria-label="也可以在这里打字，比如：我想换电饭煲"
      />
      <button class="send-btn" type="submit" :disabled="busy" aria-label="发送">发送</button>
    </form>

    <!-- 麦克风不可用时的说明入口：大字号、高对比，符合助老模式可读性要求 -->
    <button v-if="micUnavailable" class="why-btn" type="button" @click="showWhy">
      <span class="why-icon" aria-hidden="true">?</span>
      <span>为什么不能用麦克风？</span>
    </button>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const props = defineProps({
  // 父组件正在等后端识别/回答：按钮进入「正在思考」态并禁点，避免重复提交
  busy: { type: Boolean, default: false },
})

const emit = defineEmits(['audio', 'text', 'press'])

const btnRef = ref(null)
// 主状态机：idle 待按 → opening 正在开麦 → recording 录音中
const phase = ref('idle')
const willCancel = ref(false)
const seconds = ref(0)
const text = ref('')

let mediaRecorder = null
let chunks = []
let pressToken = 0 // 防止「按住→松手」快于 getUserMedia 返回时的竞态
let recordStartedAt = 0
let timerId = 0
let touchActive = false

// 文本尽量短：28px 字号在 375px 屏上约放得下 11 个字
const btnText = computed(() => {
  if (props.busy) return '正在思考，请稍等…'
  if (phase.value === 'opening') return '正在打开麦克风…'
  if (phase.value === 'recording') {
    // 计时从 1 秒起显示：刚按下就露出「0 秒」会让人以为坏了
    return willCancel.value ? '松开手指，取消发送' : `正在录音 ${Math.max(1, seconds.value)} 秒，松开发送`
  }
  return '按住 说话'
})

/* ---------- 麦克风可用性预判 ----------
 * 浏览器只允许安全上下文（HTTPS / localhost）使用麦克风。
 * 通过 HTTP + 局域网 IP 访问（真机联调最常见的形态）时，
 * navigator.mediaDevices 干脆是 undefined，按了也必然失败——
 * 与其让老人按了才看到报错，不如一开始就给出准确的原因。 */
const insecureContext =
  typeof window !== 'undefined' && window.isSecureContext === false

// 一旦确认不可用就置 true，模板据此显示「为什么不能用？」
const micUnavailable = ref(insecureContext)

// 按失败原因给出「能照着做」的中文提示，而不是一句笼统的"不可用"
function micErrorTip(err) {
  if (insecureContext) {
    return '当前为非 HTTPS 环境，浏览器限制了麦克风。请使用文字输入，或联系管理员配置 HTTPS。'
  }
  const name = err?.name || ''
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return '麦克风权限被拒绝：请点击浏览器地址栏左侧的图标，把「麦克风」设为允许后重试，或改用下方文字输入。'
  }
  if (name === 'NotFoundError' || name === 'NotReadableError') {
    return '未检测到可用的麦克风设备（或被其他应用占用），请改用下方文字输入。'
  }
  return '麦克风暂时不可用，请改用下方文字输入'
}

// 「为什么不能用？」弹窗：把三种原因和对应解法一次讲清
function showWhy() {
  const reason = insecureContext
    ? '当前页面是通过 HTTP（非 HTTPS）打开的。浏览器出于安全考虑，禁止非安全环境使用麦克风，这不是手机或软件坏了。'
    : '可能是浏览器拒绝了麦克风权限，也可能是设备没有麦克风或被其他应用占用。'
  ElMessageBox.alert(
    reason +
      '解决方法：\n' +
      (insecureContext
        ? '· 换用下方文字输入，功能完全一样；\n· 或联系管理员为网站配置 HTTPS 证书；\n· 本地开发时可用 http://localhost 访问（localhost 不受此限制）。'
        : '· 点击浏览器地址栏左侧的图标，把「麦克风」设为允许后刷新页面；\n· 检查设备是否接入麦克风、是否被微信等应用占用；\n· 权限解决前可先用下方文字输入，功能完全一样。'),
    '为什么不能用麦克风？',
    { confirmButtonText: '我知道了', customStyle: { maxWidth: '92vw' } },
  ).catch(() => {})
}

/* ---------- 按压生命周期 ---------- */
function startTimer() {
  stopTimer()
  seconds.value = 0
  recordStartedAt = Date.now()
  timerId = setInterval(() => { seconds.value = Math.floor((Date.now() - recordStartedAt) / 1000) }, 500)
}

function stopTimer() {
  if (timerId) clearInterval(timerId)
  timerId = 0
}

async function beginPress() {
  if (props.busy || phase.value !== 'idle') return
  willCancel.value = false
  // 同步回调父组件：在同一手势调用栈内「解锁」音频元素并停掉上一轮播报，
  // 一旦 await 过，iOS 就不再认这是用户手势了。
  emit('press')
  phase.value = 'opening'
  const token = ++pressToken

  if (insecureContext) {
    phase.value = 'idle'
    ElMessage.warning(micErrorTip(null))
    return
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    phase.value = 'idle'
    micUnavailable.value = true
    ElMessage.warning('当前浏览器不支持麦克风，请改用下方文字输入')
    return
  }

  let stream
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch (err) {
    if (token !== pressToken) return
    // 麦克风不可用（无权限 / 非安全上下文 / 设备缺失）：降级到文字输入，
    // 并明确告知用户——此前静默失败会让人以为「按住说话」按钮坏了
    micUnavailable.value = true
    phase.value = 'idle'
    ElMessage.warning(micErrorTip(err))
    return
  }

  // 授权弹窗期间手指已经松开：直接收摊，别凭空录一段
  if (token !== pressToken) {
    stream.getTracks().forEach((tr) => tr.stop())
    return
  }

  try {
    chunks = []
    const recorder = new MediaRecorder(stream)
    mediaRecorder = recorder
    recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data) }
    recorder.onstop = () => {
      stream.getTracks().forEach((tr) => tr.stop())
      // 太短的录音（误触/轻点）不送后端：既省一次识别费用，也不会得到「没听清」
      const held = Date.now() - recordStartedAt
      if (held < 400) {
        ElMessage.info('按住不放，说完再松手')
        return
      }
      const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' })
      if (blob.size > 0) emit('audio', blob)
    }
    recorder.start()
    phase.value = 'recording'
    startTimer()
  } catch {
    stream.getTracks().forEach((tr) => tr.stop())
    phase.value = 'idle'
    ElMessage.warning('录音启动失败，请改用下方文字输入')
  }
}

function finishPress(cancel) {
  if (phase.value === 'idle') return
  if (phase.value === 'opening') {
    // 还没拿到麦克风就松手：作废这次按下（beginPress 里会自行收尾流）
    pressToken += 1
    phase.value = 'idle'
    return
  }
  if (phase.value !== 'recording') return

  stopTimer()
  phase.value = 'idle'
  willCancel.value = false
  const recorder = mediaRecorder
  mediaRecorder = null
  if (!recorder) return
  if (cancel) {
    // 滑出按钮 = 放弃本次录音：摘掉 onstop 里的发送逻辑，只收资源
    recorder.ondataavailable = null
    recorder.onstop = () => recorder.stream?.getTracks?.().forEach((tr) => tr.stop())
  }
  if (recorder.state === 'recording') recorder.stop()
}

/* ---------- 触摸端：唯一真正需要 preventDefault 的地方 ---------- */
function onTouchStart(event) {
  // 双保险：模板已加 .prevent，这里再显式拦一次，
  // 彻底关掉长按弹出的「选择/复制」菜单，否则录音会被系统中断。
  event.preventDefault()
  touchActive = true
  beginPress()
}

function onTouchMove(event) {
  if (phase.value !== 'recording' && phase.value !== 'opening') return
  const touch = event.touches && event.touches[0]
  const el = btnRef.value
  if (!touch || !el) return
  const rect = el.getBoundingClientRect()
  const slack = 44 // 老人手抖是常态，留足容错，滑很远才算取消
  const outside =
    touch.clientX < rect.left - slack ||
    touch.clientX > rect.right + slack ||
    touch.clientY < rect.top - slack ||
    touch.clientY > rect.bottom + slack
  willCancel.value = outside
}

function onTouchEnd(event) {
  event.preventDefault()
  touchActive = false
  finishPress(willCancel.value)
}

function onTouchCancel() {
  touchActive = false
  finishPress(true)
}

/* ---------- 指针端（鼠标/触控板；触摸已由 touch 事件接管，避免双触发） ---------- */
function onPointerDown(event) {
  if (touchActive || event.pointerType === 'touch') return
  beginPress()
}

function onPointerUp(event) {
  if (touchActive || event.pointerType === 'touch') return
  finishPress(false)
}

function onPointerLeave(event) {
  if (touchActive || event.pointerType === 'touch') return
  if (phase.value === 'recording') finishPress(true)
}

function onPointerCancel(event) {
  if (touchActive || event.pointerType === 'touch') return
  finishPress(true)
}

/* ---------- 键盘可达：空格按住 = 说话 ---------- */
function onKeyDown(event) {
  if (event.repeat) return
  beginPress()
}

function onKeyUp() {
  finishPress(false)
}

function submitText() {
  const value = text.value.trim()
  if (!value || props.busy) return
  emit('text', value)
  text.value = ''
}

onBeforeUnmount(() => {
  stopTimer()
  pressToken += 1
  if (mediaRecorder?.state === 'recording') mediaRecorder.stop()
  mediaRecorder = null
})
</script>

<style scoped>
/* 问题 1 的根：整块操作区都禁掉选区与长按菜单。
   -webkit-touch-callout 关掉 iOS 的长按弹出菜单，
   user-select: none 关掉选区，二者缺一都会被系统菜单打断录音。 */
.voice-input {
  display: flex; flex-direction: column; gap: 16px; align-items: center; width: 100%;
  -webkit-user-select: none; user-select: none;
  -webkit-touch-callout: none;
  -webkit-tap-highlight-color: transparent;
  touch-action: manipulation;
}

.talk-btn {
  position: relative; overflow: hidden;
  display: flex; align-items: center; justify-content: center; gap: 14px;
  width: 100%; max-width: 560px; min-height: 96px;
  padding: 12px 20px;
  font-family: inherit;
  font-size: clamp(20px, 5.2vw, 28px); font-weight: 700; line-height: 1.25;
  color: #ffffff; background: #1B5E20; /* 白字对比度 ≥ 4.5:1 */
  border: none; border-radius: 24px; cursor: pointer;
  box-shadow: 0 10px 24px rgba(27, 94, 32, 0.35);
  /* 触摸端：禁止滚动/缩放手势抢走按压，长按不再触发选区 */
  touch-action: none; user-select: none; -webkit-user-select: none;
  -webkit-touch-callout: none;
  -webkit-tap-highlight-color: transparent;
  transition: background-color .18s ease, transform .12s ease, box-shadow .2s ease;
}
.talk-btn * { user-select: none; -webkit-user-select: none; -webkit-touch-callout: none; }
.talk-btn svg { width: 36px; height: 36px; flex: none; }
.btn-text { text-align: left; }
.btn-icon { display: inline-flex; flex: none; }

/* 按下即缩：给老人「我按到了」的第一反馈（略小于 1 才有按压感） */
.talk-btn:not(:disabled):active { transform: scale(0.975); }

/* 正在开麦（申请权限的那 1~2 秒）：变红 + 呼吸，避免看起来像没反应 */
.talk-btn.is-opening { background: #B71C1C; animation: talk-breathe 1.1s ease-in-out infinite; }

/* 录音态：颜色加深 + 轻微放大 + 呼吸灯，三重变化确保一眼可辨 */
.talk-btn.is-recording {
  background: #8E0000;
  transform: scale(1.02);
  box-shadow: 0 14px 34px rgba(142, 0, 0, 0.55);
  animation: talk-breathe 1.5s ease-in-out infinite;
}
.talk-btn.is-canceling { background: #455A64; box-shadow: 0 10px 24px rgba(69, 90, 100, 0.45); }
/* 录音中手指仍按着，别让 :active 的缩放盖掉放大效果 */
.talk-btn.is-recording:active { transform: scale(1.02); }

.ripple {
  position: absolute; inset: 0; border-radius: inherit;
  pointer-events: none; opacity: 0;
}
.talk-btn.is-recording .ripple {
  opacity: 1;
  animation: talk-ripple 1.6s ease-out infinite;
}

/* 思考态：禁用但不要变成灰糊糊的，用深灰 + 转圈表达「在干活」 */
.talk-btn.is-thinking {
  background: #37474F; cursor: progress;
  box-shadow: 0 8px 20px rgba(55, 71, 79, 0.35);
  animation: none; transform: none;
}
.talk-btn:disabled { opacity: 1; }
.spin { animation: talk-spin 0.9s linear infinite; transform-origin: 50% 50%; }

.rec-tip {
  margin: 0; font-size: 22px; font-weight: 700; color: #8E0000;
  align-self: center;
}
.rec-tip.is-cancel { color: #455A64; }

@keyframes talk-spin { to { transform: rotate(360deg); } }
@keyframes talk-breathe {
  0%, 100% { box-shadow: 0 10px 24px rgba(183, 28, 28, 0.42); }
  50% { box-shadow: 0 16px 38px rgba(183, 28, 28, 0.72); }
}
@keyframes talk-ripple {
  0% { box-shadow: inset 0 0 0 0 rgba(255, 255, 255, 0.5); }
  70% { box-shadow: inset 0 0 0 22px rgba(255, 255, 255, 0); }
  100% { box-shadow: inset 0 0 0 22px rgba(255, 255, 255, 0); }
}

.talk-btn:focus-visible { outline: 4px solid #0D47A1; outline-offset: 3px; }

.text-row { display: flex; gap: 12px; width: 100%; max-width: 560px; }
.text-input {
  flex: 1; min-width: 0; /* 没有它，占位文案的固有宽度会把「发送」顶出 390px 屏 */
  min-height: 80px; font-size: 24px; padding: 0 20px;
  border: 3px solid #1B5E20; border-radius: 16px; color: #1a1a1a; background: #fff;
  /* 输入框要能正常长按选词/粘贴，父级的 user-select: none 不能连坐 */
  -webkit-user-select: text; user-select: text;
  -webkit-touch-callout: default;
}
.text-input:focus-visible { outline: 4px solid #0D47A1; outline-offset: 2px; }
.send-btn {
  min-height: 80px; min-width: 120px; font-size: 24px; font-weight: 700;
  color: #fff; background: #0D47A1; border: none; border-radius: 16px; cursor: pointer;
  -webkit-user-select: none; user-select: none;
}
.send-btn:disabled { opacity: .55; cursor: progress; }
.send-btn:focus-visible { outline: 4px solid #1B5E20; outline-offset: 3px; }

/* 「为什么不能用？」：仅在麦克风确认不可用时出现。
   字号 22px（≥22 符合助老可读性下限）、白底描边，弱于主操作但一眼可找。 */
.why-btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 10px;
  min-height: 56px; padding: 0 16px;
  font-size: 22px; font-weight: 700;
  color: #1B5E20; background: #ffffff;
  border: 3px solid #1B5E20; border-radius: 16px; cursor: pointer;
  /* 实测 390px 下文字 220px 与可用空间压线导致折行，收紧内边距 + 禁折行 */
  white-space: nowrap;
}
.why-icon {
  display: grid; place-items: center;
  width: 32px; height: 32px; border-radius: 50%;
  font-size: 20px; color: #fff; background: #1B5E20;
}
.why-btn:focus-visible { outline: 4px solid #0D47A1; outline-offset: 3px; }

/* 尊重系统「减弱动效」：动画关掉，但颜色/文字状态照旧可辨 */
@media (prefers-reduced-motion: reduce) {
  .talk-btn, .talk-btn.is-recording, .talk-btn.is-opening, .ripple, .spin { animation: none; }
}
</style>
