import request from './request'
export const getReviews = (params) => request.get('/reviews', { params })
export const getReviewSummary = (params) => request.get('/reviews/summary', { params })
export const createReview = (data) => request.post('/reviews', data)
