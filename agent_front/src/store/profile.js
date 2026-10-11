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

  async function fetchProfile(id) {
    const targetId = id ?? userId.value
    if (!targetId) return
    const data = await getProfile(targetId)
    apply(data)
    loaded.value = true
    return data
  }

  // 保存到后端并立即更新全局状态；失败时抛出由调用方提示
  async function saveProfile(patch) {
    if (!userId.value) throw new Error('login required')
    const data = await updateProfile(userId.value, patch)
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
    highContrast, language, isVisual, isMobility, rootClasses,
    apply, applyFromUser, fetchProfile, saveProfile, reset,
  }
})
