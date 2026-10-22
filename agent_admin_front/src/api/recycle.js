import request from './request'

// ============================================================
// 平台回收（二期）· 管理端接口
// 后端挂载于 /api/admin/recycle，响应外壳 code=200（拦截器已统一处理）。
// 「平台库存」页不新增接口：= GET /recycle/list?status=2。
// ============================================================

// 回收单列表（可按状态筛选：1待取件 2已入库 3已售出 4已取消）
export const getRecycleList = (params) => request.get('/recycle/list', { params })

// 标记入库（仅待取件）
export const receiveRecycle = (id) => request.put(`/recycle/${id}/receive`, {})

// 批量卖给回收商
export const sellToRecycler = (data) => request.post('/recycle/sell', data)

// 销售记录
export const getSaleList = (params) => request.get('/recycle/sales', { params })

// 运营数据看板
export const getRecycleStats = () => request.get('/recycle/stats')

// 回收商下拉数据源（merchant.category='回收' 且已通过审核）
export const getRecyclers = () => request.get('/recycle/recyclers')
