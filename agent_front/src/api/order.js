import request from './request'

// 我的交换（用户侧订单接口）
// baseURL 为 /api/v1；后端由 app/main.py 双挂载到 /api/orders 与 /api/v1/orders。
//
// skipErrorToast 的作用（重要）：
// request.js 的响应拦截器对失败请求会统一 ElMessage.error。
// 但「我要换」弹窗与列表页的动作按钮都要**按错误类型**给更具体的中文提示，
// 若不静默，用户会先看到一个拦截器弹框、再看到页面弹框（同一错误弹两次）。
// 因此凡是调用方自己要提示的请求，一律传 skipErrorToast: true。
// 只有列表查询（getOrders）交给拦截器统一提示。

// 发起交换：message 可选（后端为空/全空白时不发私信）
export const createOrder = (itemId, message) =>
  request.post('/orders', { item_id: itemId, message: message || null }, { skipErrorToast: true })

// 订单列表：params = { role: 'buyer' | 'seller' | 'all', status?, page?, size? }
export const getOrders = (params) => request.get('/orders', { params })

// 订单详情（含时间线 + 消息记录）
export const getOrderDetail = (orderId) =>
  request.get(`/orders/${orderId}`, { skipErrorToast: true })

// 卖家确认交换（1 待确认 → 2 交换中）
export const confirmOrder = (orderId) =>
  request.put(`/orders/${orderId}/confirm`, null, { skipErrorToast: true })

// 确认完成（2 交换中 → 3 已完成）：后端会发分、累加碳减排量并把物品下架
export const completeOrder = (orderId) =>
  request.put(`/orders/${orderId}/complete`, null, { skipErrorToast: true })

// 取消订单（1/2 → 4 已取消）；卖家在「待确认」阶段调用即等价于「拒绝」
export const cancelOrder = (orderId) =>
  request.put(`/orders/${orderId}/cancel`, null, { skipErrorToast: true })
