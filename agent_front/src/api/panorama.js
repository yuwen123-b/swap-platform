import request from './request'

// 360° 视图：触发生成（JSON body）与查询结果
export const triggerPanorama = (itemId) => request.post('/panorama/generate', { item_id: itemId })
export const getPanorama = (itemId) => request.get(`/panorama/${itemId}`)
