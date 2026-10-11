import request from './request'

// 个人中心：助老模式 / 无障碍模式 / 行动能力 / 高对比度 / 语言
export const getProfile = (userId) => request.get(`/user/profile/${userId}`)
export const updateProfile = (userId, data) => request.put(`/user/profile/${userId}`, data)
