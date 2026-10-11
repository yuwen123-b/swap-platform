import request from './request'

export const getPosts = (params) => request.get('/posts', { params })
export const updatePost = (id, data) => request.put(`/posts/${id}`, data)
export const deletePost = (id) => request.delete(`/posts/${id}`)
export const getReports = (params) => request.get('/reports', { params })
export const handleReport = (id, data) => request.post(`/reports/${id}/handle`, data)
