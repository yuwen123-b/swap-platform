import request from './request'

export const getOrders = (params) => request.get('/orders', { params })
export const getOrderDetail = (id) => request.get(`/orders/${id}`)
export const updateOrderStatus = (id, status) => request.put(`/orders/${id}/status`, { status })
export const deleteOrder = (id) => request.delete(`/orders/${id}`)
