import request from './request'

export const getItems = (params) => request.get('/items', { params })
export const getItemDetail = (id) => request.get(`/items/${id}`)
export const updateItem = (id, data) => request.put(`/items/${id}`, data)
export const deleteItem = (id) => request.delete(`/items/${id}`)
export const getAuditItems = (params) => request.get('/items/audit/list', { params })
export const auditItem = (id, data) => request.post(`/items/${id}/audit`, data)
