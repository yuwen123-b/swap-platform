import request from './request'

// 个人中心：基础信息 / 助老模式 / 无障碍模式 / 行动能力 / 高对比度 / 语言
// user_id 一律由后端从 JWT 解析，前端不再传参（避免越权读改他人资料）
export const getProfile = () => request.get('/user/profile')
export const updateProfile = (data) => request.put('/user/profile', data)

// 头像上传：multipart，由 Axios 自动补充 boundary
export const uploadAvatar = (formData) => request.post('/user/avatar', formData)

// ========== 账户安全 ==========
export const changePassword = (data) => request.put('/user/password', data)
export const sendPhoneCode = (data) => request.post('/user/phone/send-code', data)
export const rebindPhone = (data) => request.put('/user/phone', data)
export const sendEmailCode = (data) => request.post('/user/email/send-code', data)
export const rebindEmail = (data) => request.put('/user/email', data)

// ========== 通知设置 ==========
export const getNotifications = () => request.get('/user/notifications')
export const updateNotifications = (data) => request.put('/user/notifications', data)

// ========== 意见反馈 ==========
export const submitFeedback = (data) => request.post('/user/feedback', data)

// ========== 地址解析（文本地址 → 坐标/小区/楼栋） ==========
export const searchAddress = (data, config = {}) => request.post('/user/location/search-address', data, config)

// ========== 我的物品（第二区） ==========
// params: { status?: 1|2|3|4, page?: number, size?: number }
export const getMyItems = (params) => request.get('/user/items', { params })
// 下架自己的物品（后端仅允许「在售/审核中」变为「已下架」，user_id 从 JWT 解析）
export const removeMyItem = (itemId) => request.put(`/user/items/${itemId}/remove`)

// ========== 碳积分（第四区） ==========
export const getCarbonSummary = () => request.get('/user/carbon/summary')
// params: { limit?: number }  默认 10，上限 50
export const getCarbonLogs = (params) => request.get('/user/carbon/logs', { params })
export const getCarbonRank = () => request.get('/user/carbon/rank')

// ========== 我的收藏 ==========
// params: { page?: number, size?: number }  默认每页 10，上限 50
export const getFavorites = (params) => request.get('/user/favorites', { params })
// 收藏 / 取消收藏：均为幂等操作，重复调用不报错
export const addFavorite = (itemId) => request.post(`/user/favorites/${itemId}`)
export const removeFavorite = (itemId) => request.delete(`/user/favorites/${itemId}`)
// 详情页加载时调用，决定心形图标初始为空心还是实心
export const checkFavorite = (itemId) => request.get(`/user/favorites/check/${itemId}`)

// ========== 我想要的（需求） ==========
// params: { status?: 1|2|3, page?: number, size?: number }  默认每页 10，上限 50
export const getMyDemands = (params) => request.get('/user/demands', { params })
// 发布需求：{ title, description?, category? }
export const createDemand = (data) => request.post('/user/demands', data)
// 编辑需求：仅「进行中」可编辑，只传需要修改的字段
export const updateDemand = (id, data) => request.put(`/user/demands/${id}`, data)
// 撤销（1→3）/ 标记完成（1→2）：均为状态流转，仅本人可操作
export const cancelDemand = (id) => request.put(`/user/demands/${id}/cancel`)
export const completeDemand = (id) => request.put(`/user/demands/${id}/complete`)
// 公开需求墙（首页展示）走独立文件：src/api/demand.js
