import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { getMe } from '../api/auth'
import { useProfileStore } from './profile'

export const useUserStore = defineStore('user', () => {
  const token = ref(localStorage.getItem('token') || '')
  const user = ref(JSON.parse(localStorage.getItem('user') || 'null'))
  const isLoggedIn = computed(() => Boolean(token.value))

  function setSession(data) {
    token.value = data.token
    user.value = data.user
    localStorage.setItem('token', data.token)
    localStorage.setItem('user', JSON.stringify(data.user))
    // 登录返回中已带持久化的模式/语言配置，立即应用，并在后台拉取最新档案
    const profileStore = useProfileStore()
    profileStore.applyFromUser(data.user)
    profileStore.fetchProfile().catch(() => {})
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    useProfileStore().reset()
  }

  async function hydrate() {
    if (!token.value) return
    const profileStore = useProfileStore()
    if (user.value) {
      // 本地缓存会话：先用缓存字段即时应用，再后台同步最新档案
      profileStore.applyFromUser(user.value)
      profileStore.fetchProfile().catch(() => {})
      return
    }
    try {
      user.value = await getMe()
      localStorage.setItem('user', JSON.stringify(user.value))
      profileStore.applyFromUser(user.value)
      profileStore.fetchProfile().catch(() => {})
    } catch {
      logout()
    }
  }

  return { token, user, isLoggedIn, setSession, logout, hydrate }
})
