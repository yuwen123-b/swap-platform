import request from './request'

export const getOverview = () => request.get('/dashboard/overview')
export const getTrends = () => request.get('/dashboard/trends')
