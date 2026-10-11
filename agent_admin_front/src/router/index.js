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
      { path: 'orders', name: 'OrderList', component: () => import('@/views/order/OrderList.vue'), meta: { title: '订单管理', roles: [1, 2, 3] } },
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
