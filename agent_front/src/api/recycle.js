import request from './request'

// ============================================================
// 平台回收（二期）
// 估价是**服务端唯一真源**：前端只调 /recycle/estimate 展示，
// 绝不本地复算 —— 用户看到多少、实际到账就是多少。
// ============================================================

// 估价预览（提交前弹窗展示，随成色变化实时刷新）
export const getRecycleEstimate = (conditionLevel, config = {}) =>
  request.get('/recycle/estimate', { params: { condition_level: conditionLevel }, ...config })

// 我的回收单（可按状态筛选：1待取件 2已入库 3已售出 4已取消）
export const getMyRecycles = (params, config = {}) =>
  request.get('/recycle/my', { params, ...config })

// 提交平台回收（物品先发布，再拿 id 提交回收）
export const submitRecycle = (itemId, data, config = {}) =>
  request.put(`/items/${itemId}/recycle`, data, config)

// 取消回收（仅待取件可取消，积分原额退回）
export const cancelRecycle = (recycleId, config = {}) =>
  request.put(`/recycle/${recycleId}/cancel`, {}, config)
