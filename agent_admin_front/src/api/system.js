import request from './request'

export const getSystemConfig = () => request.get('/system/config')
export const updateSystemConfig = (data) => request.put('/system/config', data)
