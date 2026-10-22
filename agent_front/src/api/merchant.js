import request from './request'

// ============================================================
// 积分商城（用户端）
// baseURL 为 /api/v1；后端由 app/main.py 双挂载到 /api/merchant 与 /api/v1/merchant。
// 本文件只包含**用户侧 4 个接口**：商家端 9 个（/merchant/products* 等）属商家工作台，
// 管理端 7 个（/api/admin/merchant/*）属管理后台，都不在这里封装。
// 详见 docs/API文档-商家端闭环.md
// ============================================================

// 商家列表（免登录可访问）
// params: { category?: string, page?: number, size?: number }
// ⚠ category 是**精确匹配**（后端 SQL 为 m.category=%s），必须传完整中文名
// 返回：{ total, page, size, list: [{ id, name, category, address, contact,
//         description, logo_url, product_count }] }
// 注意：返回体里**没有距离、没有销量**（merchant 表无坐标列）
export const getMerchantList = (params, config = {}) =>
  request.get('/merchant/shops', { params, ...config })

// 某商家的上架商品（免登录可访问；店铺不存在/未过审 → 404）
// ⚠ 返回的是对象 { merchant, list }，**不是数组**！调用方别当列表用。
// 商品数组按 id ASC，不分页。
export const getShopProducts = (id, config = {}) =>
  request.get(`/merchant/shops/${id}/products`, config)

// 语义别名：任务书里叫 getMerchantDetail，返回值形态同上（商家 + 商品）
export const getMerchantDetail = (id, config = {}) => getShopProducts(id, config)

// 兑换商品
// 必须 skipErrorToast：兑换失败要按错误类型在 Dialog 内给分叉文案
// （积分不足 / 库存不足 / 已下架 / 店铺未开放…），
// 不静默的话用户会先看到拦截器弹框、再看到 Dialog 弹框（同一错误弹两次）。
// 与 src/api/order.js 的既有约定一致。
// 返回：{ order_id, order_no, code, points_cost, product_title,
//         merchant_name, expires_at, points_balance }
// ⚠ 余额字段是 points_balance（不是 points）
export const redeemProduct = (productId) =>
  request.post('/merchant/redeem', { product_id: productId }, { skipErrorToast: true })

// 我的兑换记录
// params: { status?: 1 | 2 | 3, page?: number, size?: number }
//   1 待核销 / 2 已核销 / 3 已过期  （4 已取消无用户侧入口，后端也没有取消接口）
// 列表查询交给拦截器统一提示，故不传 skipErrorToast。
export const getMyRedemptions = (params, config = {}) =>
  request.get('/merchant/my-redemptions', { params, ...config })

// ============================================================
// 商家工作台（阶段三）
// 同一前缀 /api/v1/merchant 下的商家侧接口。全部要求登录，且身份由后端从 JWT
// 反查 merchant.user_id —— 前端**不传** merchant_id，传了也会被忽略。
//
// ⚠ 关于 skipErrorToast：
//   凡是「错误要在页面/Dialog 内自己分叉展示」的接口都必须带上，
//   否则会出现「拦截器弹一次 + 页面再弹一次」的双弹。这里除纯列表查询外全部带上。
// ============================================================

// 入驻申请（首次 INSERT / 待审核与被拒时 UPDATE 重提）
// body: { name, category, contact, address, description }
// ⚠ 可选字段**只在显式出现时**才被写入：重提时要把表单里所有字段都传出去
//   （含空串，空串表示清空该项），否则用户刚清空的地址不会被清掉。
export const applyMerchant = (data) =>
  request.post('/merchant/apply', data, { skipErrorToast: true })

// 当前账号的商家信息
// 未入驻时**不是 404**：返回 { merchant: null, enabled: true }
export const getMerchantInfo = (config = {}) => request.get('/merchant/info', config)

// 修改店铺资料（工作台「店铺设置」）
// body: { name?, category?, contact?, address?, description?, logo_url? }
// 只覆盖显式传入的字段；status / commission_rate 一律不可改（费率只有管理员能动）
export const updateMerchantInfo = (data) =>
  request.put('/merchant/info', data, { skipErrorToast: true })

// 商家自己的商品列表（含已下架）
// 返回：{ merchant_id, merchant_status, list: [...] }
export const getMerchantProducts = (config = {}) => request.get('/merchant/products', config)

// 上架新商品（要求店铺**已通过审核**）
// body: { title, description, image_url, points_cost, stock }
// image_url 本阶段填**图片 URL 或留空**（不做 multipart 上传，留空由前端用 emoji 占位）
export const createMerchantProduct = (data) =>
  request.post('/merchant/products', data, { skipErrorToast: true })

// 改商品（只传要改的字段；不含 status，上下架走下面两个专用接口）
export const updateMerchantProduct = (id, data) =>
  request.put(`/merchant/products/${id}`, data, { skipErrorToast: true })

// 下架 / 重新上架（软开关，不删行）
export const offlineMerchantProduct = (id) =>
  request.put(`/merchant/products/${id}/offline`, {}, { skipErrorToast: true })

export const onlineMerchantProduct = (id) =>
  request.put(`/merchant/products/${id}/online`, {}, { skipErrorToast: true })

// 本店兑换单列表
// params: { status?: 1待核销|2已核销|3已过期|4已取消, page, size }
export const getMerchantRedemptions = (params, config = {}) =>
  request.get('/merchant/redemptions', { params, ...config })

// 核销（输入 6 位核销码）
// ⚠ code 全程按**字符串**传：后端核销码可能以 0 开头（如 "012345"），
//   Number() 转换会把它变成 12345 而核销失败。
// 成功返回：{ success, order_id, order_no, product_title, points_cost,
//            user_nickname, redeemed_at }
export const verifyRedemption = (code) =>
  request.post('/merchant/redemptions/verify', { code: String(code) }, { skipErrorToast: true })

// 数据看板
// 返回：{ today_redemptions, total_redemptions, unique_users,
//         popular_products: [{title, sold_count}], trend: [{date, count}] }
// ⚠ **不含**「待核销订单数」，该卡需另调 getMerchantRedemptions({status:1,size:1}) 取 total
export const getMerchantDashboard = (config = {}) => request.get('/merchant/dashboard', config)

// 结算自查（只读）
// 返回：{ redemption_count, points_total, gross_amount, commission_amount, net_amount,
//         settled_amount, settled_commission, pending_amount, settled_count,
//         last_settled_at, commission_rate, points_to_yuan, period }
// 「已结算 / 待结算」都是**应得口径**（元），可直接与 gross_amount 相减对账。
export const getSettlementSummary = (config = {}) =>
  request.get('/merchant/settlement/summary', config)
