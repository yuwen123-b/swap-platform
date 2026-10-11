import request from './request'

export const getAiLogs = (params) => request.get('/ai/logs', { params })
export const getAiStats = () => request.get('/ai/stats')
export const getAiAlerts = (params) => request.get('/ai/alerts', { params })
