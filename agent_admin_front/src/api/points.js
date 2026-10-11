import request from './request'

export const getPointsLogs = (params) => request.get('/points/logs', { params })
export const adjustPoints = (data) => request.post('/points/adjust', data)
export const getPointsRules = () => request.get('/points/rules')
export const updatePointsRules = (data) => request.put('/points/rules', data)
