import request from './request'

// 商家管理（管理端）· 8 个接口，全部挂在 `/api/admin/merchant`。
// 响应外壳是管理端的 ok()（code:200），request.js 拦截器已解包，
// 因此调用方直接拿 `res.data`，不需要再判 code。
//
// 注意：审核是 **PUT**（写成 POST 会 405，与 api/item.js 的 auditItem 不同）。

// 商家列表（status: 0待审核 1已通过 2已拒绝 3已停业；keyword 命中 name/contact/address）
export const getMerchantList = (params) => request.get('/merchant/list', { params })

// 审核入驻：{ approved: boolean, reason?: string }，拒绝时 reason 必填
export const auditMerchant = (id, data) => request.put(`/merchant/${id}/audit`, data)

// 全部兑换订单（status / merchant_id / keyword，无日期参数）
export const getRedemptionOrders = (params) => request.get('/merchant/orders', { params })

// 结算记录（merchant_id / period / status）
export const getSettlements = (params) => request.get('/merchant/settlements', { params })

// 结算预览（只读）：按 settle_merchant 同口径返回每个已通过商家的
// {redemption_count, points_total, commission_amount, settled, settled_at}
export const getSettlementPreview = (params) =>
  request.get('/merchant/settlements/preview', { params })

// 结算全部已通过商家（不可逆，仅超管可见，不进主 UI）
export const triggerSettle = (data) => request.post('/merchant/settle', data)

// 按行结算指定商家
export const triggerSettleOne = (id, data) => request.post(`/merchant/settle/${id}`, data)

// 平台总览：商家分状态 / 兑换单分状态 / 消耗积分 / 已结算佣金 / 排行 / 趋势
export const getMerchantStats = () => request.get('/merchant/stats')
