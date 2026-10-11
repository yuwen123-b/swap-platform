import { defineStore } from 'pinia'

export const useAdminStore = defineStore('admin', {
  state: () => ({
    token: localStorage.getItem('admin_token') || '',
    adminInfo: JSON.parse(localStorage.getItem('admin_info') || 'null'),
  }),
  getters: {
    role: (state) => state.adminInfo?.role ?? 0,
    isLogin: (state) => Boolean(state.token),
  },
  actions: {
    setLogin(data) {
      this.token = data.token
      this.adminInfo = {
        admin_id: data.admin_id,
        username: data.username,
        real_name: data.real_name,
        role: data.role,
      }
      localStorage.setItem('admin_token', data.token)
      localStorage.setItem('admin_info', JSON.stringify(this.adminInfo))
    },
    logout() {
      this.token = ''
      this.adminInfo = null
      localStorage.removeItem('admin_token')
      localStorage.removeItem('admin_info')
    },
  },
})
