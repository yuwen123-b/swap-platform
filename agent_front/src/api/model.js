import request from './request'

// 3D 模型：触发生成（JSON body）与查询状态（GET 返回签名后的 model_url）
export const triggerModel = (itemId) => request.post('/model/generate', { item_id: itemId })
export const getModel = (itemId) => request.get(`/model/${itemId}`)
