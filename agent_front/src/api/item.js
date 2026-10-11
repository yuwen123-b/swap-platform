import request from './request'
export const getItems = (params, config = {}) => request.get('/items', { params, ...config })
export const getItem = (id) => request.get(`/items/${id}`)
// 语义化别名：获取物品详情
export const getItemDetail = (id) => getItem(id)
export const getCategories = () => request.get('/categories')

// 传入 FormData（multipart）后由 Axios 自动补充 boundary；提交后物品进入待审核。
export const uploadItem = (formData) => request.post('/items', formData)
