import { createRouter, createWebHistory } from 'vue-router'

import { useAdminStore } from '@/store/admin'

const routes = [
  { path: '/login', name: 'Login', component: () => import('@/views/Login.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('@/layout/AdminLayout.vue'),
    redirect: '/dashboard',
    children: [
      { path: 'dashboard', name: 'Dashboard', component: () => import('@/views/Dashboard.vue'), meta: { title: '数据看板', roles: [1, 2, 3] } },
      { path: 'users', name: 'UserList', component: () => import('@/views/user/UserList.vue'), meta: { title: '用户管理', roles: [1, 2, 3] } },
      { path: 'items', name: 'ItemList', component: () => import('@/views/item/ItemList.vue'), meta: { title: '物品管理', roles: [1, 2, 3] } },
      { path: 'items/audit', name: 'ItemAudit', component: () => import('@/views/item/ItemAudit.vue'), meta: { title: '物品审核', roles: [1, 2, 3] } },
      // 与「商家管理 → 兑换订单」区分：这里是用户之间的物品交换单
      { path: 'orders', name: 'OrderList', component: () => import('@/views/order/OrderList.vue'), meta: { title: '物品交换订单', roles: [1, 2, 3] } },
      // 商家管理：roles 用 [1,2,3] 与后端 read_roles 一致（role 3 能进能看），
      // 写操作（审核/结算）由页面按 role!==3 做按钮级控制，后端 write_roles=[1,2] 兜底 403
      { path: 'merchant/list', name: 'MerchantList', component: () => import('@/views/merchant/MerchantList.vue'), meta: { title: '商家列表', roles: [1, 2, 3] } },
      { path: 'merchant/orders', name: 'MerchantRedemptionList', component: () => import('@/views/merchant/RedemptionList.vue'), meta: { title: '兑换订单', roles: [1, 2, 3] } },
      { path: 'merchant/settlements', name: 'MerchantSettlementList', component: () => import('@/views/merchant/SettlementList.vue'), meta: { title: '结算管理', roles: [1, 2, 3] } },
      { path: 'recycle/list', name: 'RecycleList', component: () => import('@/views/recycle/RecycleList.vue'), meta: { title: '回收单管理', roles: [1, 2] } },
      { path: 'recycle/stock', name: 'RecycleStock', component: () => import('@/views/recycle/RecycleStock.vue'), meta: { title: '平台库存', roles: [1, 2] } },
      { path: 'recycle/sales', name: 'SaleList', component: () => import('@/views/recycle/SaleList.vue'), meta: { title: '销售记录', roles: [1, 2] } },
      { path: 'recycle/stats', name: 'RecycleDashboard', component: () => import('@/views/recycle/RecycleDashboard.vue'), meta: { title: '回收运营数据', roles: [1, 2] } },
      { path: 'community/posts', name: 'PostList', component: () => import('@/views/community/PostList.vue'), meta: { title: '帖子管理', roles: [1, 2, 3] } },
      { path: 'community/reports', name: 'ReportList', component: () => import('@/views/community/ReportList.vue'), meta: { title: '举报处理', roles: [1, 2, 3] } },
      { path: 'points', name: 'PointsList', component: () => import('@/views/points/PointsList.vue'), meta: { title: '积分管理', roles: [1, 2, 3] } },
      { path: 'ai-monitor', name: 'AiMonitor', component: () => import('@/views/ai/AiMonitor.vue'), meta: { title: 'AI 监控', roles: [1, 2] } },
      { path: 'feedback', name: 'FeedbackAnalysis', component: () => import('@/views/feedback/FeedbackAnalysis.vue'), meta: { title: '评价情感分析', roles: [1, 2] } },
      { path: 'admins', name: 'AdminList', component: () => import('@/views/admin/AdminList.vue'), meta: { title: '管理员账号', roles: [1] } },
      { path: 'system', name: 'SystemConfig', component: () => import('@/views/system/SystemConfig.vue'), meta: { title: '系统配置', roles: [1] } },
      { path: '403', name: 'Forbidden', component: () => import('@/views/Forbidden.vue'), meta: { title: '无权限', roles: [1, 2, 3] } },
    ],
  },
  { path: '/:pathMatch(.*)*', name: 'NotFound', component: () => import('@/views/NotFound.vue'), meta: { public: true } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const store = useAdminStore()
  if (to.meta.public) {
    if (to.path === '/login' && store.isLogin) {
      return '/dashboard'
    }
    return true
  }
  if (!store.isLogin) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.meta.roles && !to.meta.roles.includes(store.role)) {
    return '/403'
  }
  document.title = to.meta.title ? `${to.meta.title} - 社区旧物互换管理后台` : '社区旧物互换管理后台'
  return true
})

export default router
