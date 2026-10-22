/**
 * 助老模式语音播报（TTS）：后端音频优先，浏览器合成本地兜底。
 *
 * 为什么需要这一层（真机实测结论）：
 * 1. 移动端浏览器（iOS Safari / 微信内置）有自动播放限制：音频若不是在用户手势的
 *    同一个调用栈里触发，play() 会被拒（NotAllowedError）。助老链路上音频 URL 是
 *    await 接口之后才拿到的，手势上下文早就丢了 —— 必须先用一次手势「解锁」复用的
 *    audio 元素，后续对它 play() 才稳定被允许。
 * 2. 后端音频也可能取不到（未配 TTS / 签名过期 / 弱网超时）。此时要立刻降级到
 *    window.speechSynthesis，而不是让老人对着无声页面干等。
 * 3. speechSynthesis 逐句排队播报：iOS 上连续 speak 多句只念最后一句，
 *    必须用 onend 串起来。
 *
 * 组件侧只需：按住时调 unlock()；拿到结果后调 speak(speech, url)；读 ttsState 渲染状态。
 */
import { reactive } from 'vue'

/** 播报状态：idle 静默 / loading 准备中 / playing 正在播 / failed 完全不可用 */
export const ttsState = reactive({
  status: 'idle',
  mode: '', // server 后端音频 / browser 浏览器合成
})

// 0.02s 静音 WAV（204 字节）：只在解锁时播一次，听不见但能让浏览器放行后续播放
const SILENT_WAV = 'data:audio/wav;base64,UklGRsQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YaAAAACAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA'

let player = null
let unlocked = false
let runId = 0
let watchdog = 0

function audioEl() {
  if (!player) {
    player = new Audio()
    player.preload = 'auto'
    player.setAttribute('playsinline', '') // iOS 内联播放，不弹全屏播放器
  }
  return player
}

/** 在用户手势的同步调用栈里解锁音频元素，返回是否解锁成功。 */
export function unlock() {
  if (unlocked) return true
  const el = audioEl()
  try {
    el.src = SILENT_WAV
    const ret = el.play()
    unlocked = true
    // 解锁失败不报错：真到播报时还有 speechSynthesis 兜底
    if (ret && typeof ret.catch === 'function') ret.catch(() => { unlocked = false })
  } catch {
    unlocked = false
  }
  return unlocked
}

function resetPlayer() {
  if (!player) return
  try {
    player.onplaying = null
    player.onended = null
    player.onerror = null
    player.pause()
    player.removeAttribute('src')
    player.load()
  } catch {
    /* 忽略：某些浏览器在元素未加载时 pause 会抛 */
  }
}

export function stop() {
  runId += 1
  clearTimeout(watchdog)
  resetPlayer()
  try {
    window.speechSynthesis?.cancel()
  } catch {
    /* 忽略 */
  }
  ttsState.status = 'idle'
  ttsState.mode = ''
}

function browserSpeak(speech, id, reason) {
  const synth = typeof window !== 'undefined' ? window.speechSynthesis : null
  if (!synth || typeof window.SpeechSynthesisUtterance !== 'function') {
    ttsState.status = 'failed'
    console.warn('[tts] 当前浏览器不支持 speechSynthesis，无法播报')
    return Promise.resolve(false)
  }
  const sentences =
    speech.sentences && speech.sentences.length ? speech.sentences : [speech.text]
  ttsState.mode = 'browser'
  ttsState.status = 'playing'
  if (reason) console.info('[tts] 已降级为浏览器本地播报，原因：', reason)

  try {
    synth.cancel()
    if (synth.paused) synth.resume()
  } catch {
    /* 忽略 */
  }

  return new Promise((resolve) => {
    let i = 0
    const next = () => {
      if (id !== runId) return resolve(false)
      if (i >= sentences.length) {
        ttsState.status = 'idle'
        return resolve(true)
      }
      const utter = new SpeechSynthesisUtterance(sentences[i])
      i += 1
      utter.lang = speech.voice || 'zh-CN'
      utter.rate = speech.rate || 0.8
      utter.onend = next
      utter.onerror = next // 某一句失败不应卡住后面几句
      try {
        synth.speak(utter)
      } catch (err) {
        console.warn('[tts] speechSynthesis.speak 失败：', err)
        next()
      }
    }
    next() // 用 onend 串行，避免 iOS 只念最后一句
  })
}

/** 后端音频失败/超时 → 清理 audio 元素并改用本地合成。 */
function fallback(speech, id, reason) {
  if (id !== runId) return
  clearTimeout(watchdog)
  resetPlayer()
  browserSpeak(speech, id, reason)
}

/**
 * 播报一段回复。
 * @param {{text:string, sentences?:string[], rate?:number, voice?:string}} speech
 * @param {string} audioUrl 后端 TTS 音频地址（可为空：直接本地合成）
 */
export function speak(speech, audioUrl = '') {
  const text = (speech && speech.text) || ''
  if (!text) return Promise.resolve(false)

  const id = ++runId
  clearTimeout(watchdog)
  resetPlayer()
  try {
    window.speechSynthesis?.cancel()
  } catch {
    /* 忽略 */
  }

  if (!audioUrl) return browserSpeak(speech, id, '后端未返回音频')

  ttsState.mode = 'server'
  ttsState.status = 'loading'
  const el = audioEl()
  el.src = audioUrl
  try {
    el.load() // 立刻发起请求，缩短「发送 → 出声」的间隔
  } catch {
    /* 忽略 */
  }

  // 6s 还没开播（弱网 / 解码卡住但没触发 error）：先让老人听到声音，别干等
  watchdog = setTimeout(() => {
    if (id === runId && ttsState.status !== 'playing') fallback(speech, id, '后端音频 6s 未开播')
  }, 6000)

  el.onplaying = () => {
    if (id !== runId) return
    clearTimeout(watchdog)
    ttsState.status = 'playing'
  }
  el.onended = () => {
    if (id !== runId) return
    ttsState.status = 'idle'
  }
  el.onerror = () => {
    if (id !== runId) return
    console.warn('[tts] 后端音频加载失败：', audioUrl)
    fallback(speech, id, '音频加载失败')
  }

  const ret = el.play()
  if (ret && typeof ret.then === 'function') {
    // 关键：play() 的 Promise 必须接住，否则 iOS 的 NotAllowedError 只在控制台一闪而过
    ret.catch((err) => {
      console.warn('[tts] 后端音频被拒绝播放：', err?.name, err?.message)
      fallback(speech, id, err?.name || 'play 被拒绝')
    })
  }
  return Promise.resolve(true)
}

export const tts = { speak, stop, unlock, state: ttsState }

// 仅开发环境暴露只读把手：真机/自动化排查时能直接看播报状态与音频元素进度
if (import.meta.env.DEV) {
  window.__tts = { state: ttsState, el: audioEl, unlocked: () => unlocked }
}
