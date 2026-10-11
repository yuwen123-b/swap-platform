import request from './request'

// 程序平台评价（带情感分析）
export const createFeedback = (data) => request.post('/feedback', data)
export const getFeedbackList = () => request.get('/feedback')
