import request from './request'

// 360° 视图：触发生成（multipart）与查询结果
export const generatePanorama = (formData) => request.post('/panorama/generate', formData)
export const getPanorama = (itemId) => request.get(`/panorama/${itemId}`)
