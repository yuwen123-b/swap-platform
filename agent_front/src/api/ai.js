import request from './request'

// AI 智能定价：后端 /ai/pricing 只接受 JSON（PricingRequest），
// 不接受 multipart / image / description。
// 因此图片不再随估价一起提交——图片先走识别接口回填表单，估价始终走纯 JSON。
export const pricing = (data) => request.post('/ai/pricing', data)
export const pricingHistory = (params) => request.get('/ai/pricing/history', { params })

// AI 物体识别：multipart 图片上传，字段名固定为 image。
// 超时单独放大到 60s：多模态识别冷启动常超过 axios 默认的 10s，
// 沿用默认值会把「服务正常但稍慢」误判成失败。
export const recognitionImage = (formData, options = {}) => request.post('/ai/recognition', formData, {
  headers: { 'Content-Type': 'multipart/form-data' },
  timeout: 60000,
  ...options,
})

// 把选中的图片文件包成识别接口需要的 FormData（定价页 P1 串联用）
export const recognitionFormData = (file) => {
  const formData = new FormData()
  formData.append('image', file)
  return formData
}

// 一步完成「File → 识别结果」，供定价页在估价前自动识别并回填表单
export const recognizeFile = (file, options = {}) => recognitionImage(recognitionFormData(file), options)
