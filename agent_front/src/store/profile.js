import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { getProfile, updateProfile } from '../api/user'

// 根元素 class 与契约保持一致
const ROOT_CLASS_MAP = {
  elderlyMode: 'mode-elderly',
  visual: 'mode-visual',
  mobility: 'mode-mobility',
  highContrast: 'theme-high-contrast',
}

export const useProfileStore = defineStore('profile', () => {
  const loaded = ref(false)
  const userId = ref(null)
  const elderlyMode = ref(false)
  const accessibilityMode = ref('normal') // normal / visually_impaired / mobility_impaired
  const mobilityLevel = ref('free') // free / limited / assisted
  const highContrast = ref(false)
  const language = ref('zh_CN')
  // 碳积分余额：积分商城（/merchant）与兑换弹窗都从这里读，
  // 避免同一数字在多处各拉一次接口。数据源仍是 GET /user/profile 的 points 字段。
  const points = ref(0)

  const isVisual = computed(() => accessibilityMode.value === 'visually_impaired')
  const isMobility = computed(() => accessibilityMode.value === 'mobility_impaired')

  function syncDom() {
    const root = document.documentElement
    root.classList.toggle(ROOT_CLASS_MAP.elderlyMode, elderlyMode.value)
    root.classList.toggle(ROOT_CLASS_MAP.visual, isVisual.value)
    root.classList.toggle(ROOT_CLASS_MAP.mobility, isMobility.value)
    root.classList.toggle(ROOT_CLASS_MAP.highContrast, highContrast.value)
  }

  // 后端 profile 响应 -> 本地状态（language 对应后端 preferred_lang）
  function apply(p) {
    if (!p) return
    if (p.user_id !== undefined) userId.value = p.user_id
    if (p.elderly_mode !== undefined) elderlyMode.value = Boolean(p.elderly_mode)
    if (p.accessibility_mode) accessibilityMode.value = p.accessibility_mode
    if (p.mobility_level) mobilityLevel.value = p.mobility_level
    if (p.high_contrast !== undefined) highContrast.value = Boolean(p.high_contrast)
    if (p.language) language.value = p.language
    // points 只认非 undefined：applyFromUser 传的登录返回体里没有该字段，
    // 不能因为「没传」就把已有余额清成 0。
    if (p.points !== undefined) setPoints(p.points)
    syncDom()
  }

  // 登录/会话接口返回的 user 对象内已带 profile 字段，先即时应用
  function applyFromUser(user) {
    if (!user || user.id === undefined) return
    userId.value = user.id
    apply({
      user_id: user.id,
      elderly_mode: user.elderly_mode ?? 0,
      accessibility_mode: user.accessibility_mode || 'normal',
      mobility_level: user.mobility_level || 'free',
      high_contrast: user.high_contrast ?? 0,
      language: user.language || 'zh_CN',
    })
  }

  // 档案接口已收口：user_id 由后端从 JWT 解析，前端不再传参
  async function fetchProfile() {
    const data = await getProfile()
    apply(data)
    loaded.value = true
    return data
  }

  /* ============================================================
     碳积分（积分商城用）
     ============================================================ */

  // 余额只接受非负整数；后端 points 是整数，浮点/空值一律夹紧
  function setPoints(value) {
    const n = Math.floor(Number(value))
    points.value = Number.isFinite(n) && n > 0 ? n : 0
  }

  // 单独拉一次余额（不覆盖 loaded，避免被当成「档案已加载」）
  async function fetchPoints() {
    const data = await getProfile()
    apply(data)
    return points.value
  }

  // 兑换成功后的本地扣减：纯前端记账，真实余额以 /redeem 返回的 points_balance 为准
  function deductPoints(amount) {
    const n = Math.floor(Number(amount))
    if (!Number.isFinite(n) || n <= 0) return points.value
    setPoints(points.value - n)
    return points.value
  }

  // 保存到后端并立即更新全局状态；失败时抛出由调用方提示
  async function saveProfile(patch) {
    const data = await updateProfile(patch)
    apply(data)
    return data
  }

  function reset() {
    loaded.value = false
    userId.value = null
    elderlyMode.value = false
    accessibilityMode.value = 'normal'
    mobilityLevel.value = 'free'
    highContrast.value = false
    language.value = 'zh_CN'
    points.value = 0
    const root = document.documentElement
    Object.values(ROOT_CLASS_MAP).forEach((cls) => root.classList.remove(cls))
  }

  // 供根布局绑定：{ 'mode-elderly': true, ... }
  const rootClasses = computed(() => ({
    [ROOT_CLASS_MAP.elderlyMode]: elderlyMode.value,
    [ROOT_CLASS_MAP.visual]: isVisual.value,
    [ROOT_CLASS_MAP.mobility]: isMobility.value,
    [ROOT_CLASS_MAP.highContrast]: highContrast.value,
  }))

  return {
    loaded, userId, elderlyMode, accessibilityMode, mobilityLevel,
    highContrast, language, isVisual, isMobility, rootClasses, points,
    apply, applyFromUser, fetchProfile, saveProfile, reset,
    fetchPoints, deductPoints, setPoints,
  }
})
