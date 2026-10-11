import request from './request'

export const getFeedbackList = (params) => request.get('/feedback/list', { params })
export const getFeedbackStats = () => request.get('/feedback/stats')
