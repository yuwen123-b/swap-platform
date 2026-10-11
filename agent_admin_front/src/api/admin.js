import request from './request'

export const getAccounts = (params) => request.get('/accounts', { params })
export const createAccount = (data) => request.post('/accounts', data)
export const updateAccount = (id, data) => request.put(`/accounts/${id}`, data)
export const deleteAccount = (id) => request.delete(`/accounts/${id}`)
export const resetPassword = (id, newPassword) =>
  request.post(`/accounts/${id}/reset-password`, { new_password: newPassword })
