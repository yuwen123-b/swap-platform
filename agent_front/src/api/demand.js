import request from './request'

// 公开需求墙（首页 / 需求墙页共用）。
// 与「我的需求」（src/api/user.js 里的 /user/demands*）刻意分文件：
// 它不属于个人中心，路径也独立（后端单独挂 /demands 前缀）。
//
// params: { limit?: number, category?: string }  limit 默认 6、上限 20
// 后端只返回 status=1（进行中）的需求；登录后会自动排除「自己发布的需求」；
// 返回体只含昵称与楼栋，不含手机号等隐私字段。
export const getDemandWall = (params, config = {}) => request.get('/demands', { params, ...config })
