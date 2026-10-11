import request from './request'

// AI 智能定价
export const pricing = (data) => request.post('/ai/pricing', data)
export const pricingHistory = (params) => request.get('/ai/pricing/history', { params })

// AI 物体识别：multipart 图片上传
export const recognitionImage = (formData) => request.post('/ai/recognition', formData, {
  headers: { 'Content-Type': 'multipart/form-data' },
})
