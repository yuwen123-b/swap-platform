import axios from 'axios'
import { ElMessage } from 'element-plus'

const request = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL, timeout: 30000 })
request.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  // ngrok 免费版会对「像浏览器」的请求返回 200+HTML 拦截页（无 CORS 头），
  // XHR 拿到它就会报 No 'Access-Control-Allow-Origin' + ERR_FAILED，此头强制放行
  config.headers['ngrok-skip-browser-warning'] = 'true'
  return config
})
request.interceptors.response.use((response) => {
  const body = response.data
  if (body.code === 0) return body.data
  if (body.code === 501) ElMessage.info('功能开发中')
  return Promise.reject(new Error(body.message || '请求失败'))
}, (error) => {
  if (error.response?.status === 401) {
    localStorage.removeItem('token')
    // 防重入：/login 页自身触发的 401（如登录接口被打到错误地址）不再硬跳转，
    // 否则会形成「登录 → 401 → 整页刷新 → 再登录」的死循环（EdgeOne 部署时踩过）
    if (!window.location.pathname.startsWith('/login')) {
      window.location.href = `/login?redirect=${encodeURIComponent(window.location.pathname)}`
    }
  }
  if (!error.config?.skipErrorToast) {
    ElMessage.error(error.response?.data?.message || error.message || '请求失败')
  }
  return Promise.reject(error)
})
export default request
