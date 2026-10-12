import axios from 'axios'
import { ElMessage } from 'element-plus'

const request = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL, timeout: 10000 })
request.interceptors.request.use((config) => { const token = localStorage.getItem('token'); if (token) config.headers.Authorization = `Bearer ${token}`; return config })
request.interceptors.response.use((response) => {
  const body = response.data
  if (body.code === 0) return body.data
  if (body.code === 501) ElMessage.info('功能开发中')
  return Promise.reject(new Error(body.message || '请求失败'))
}, (error) => {
  if (error.response?.status === 401) {
    localStorage.removeItem('token')
    window.location.href = `/login?redirect=${encodeURIComponent(window.location.pathname)}`
  }
  if (!error.config?.skipErrorToast) {
    ElMessage.error(error.response?.data?.message || error.message || '请求失败')
  }
  return Promise.reject(error)
})
export default request
