import axios from 'axios'
import { ElMessage } from 'element-plus'

import router from '@/router'

const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/admin',
  timeout: 15000,
})

request.interceptors.request.use((config) => {
  // ngrok 免费版对「像浏览器」的请求返回 200+HTML 拦截页（无 CORS 头），
  // 此头可跳过（生产环境走 _worker.js 同源代理时无副作用，双保险）
  config.headers['ngrok-skip-browser-warning'] = 'true'
  const token = localStorage.getItem('admin_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

request.interceptors.response.use(
  (response) => {
    const body = response.data
    if (body && typeof body === 'object' && 'code' in body) {
      if (body.code === 200) {
        return body
      }
      ElMessage.error(body.message || '请求失败')
      return Promise.reject(new Error(body.message || '请求失败'))
    }
    return body
  },
  (error) => {
    const status = error.response?.status
    const message = error.response?.data?.message || error.message || '网络异常'
    if (status === 401) {
      localStorage.removeItem('admin_token')
      localStorage.removeItem('admin_info')
      ElMessage.error('登录已过期，请重新登录')
      router.push('/login')
    } else if (status === 403) {
      ElMessage.error('无权限执行该操作')
    } else {
      ElMessage.error(message)
    }
    return Promise.reject(error)
  },
)

export default request
