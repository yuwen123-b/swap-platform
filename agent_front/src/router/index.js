import { createRouter, createWebHistory } from 'vue-router'
import { useMerchantStore } from '../store/merchant'
import Home from '../views/Home.vue'
import Login from '../views/Login.vue'
import Register from '../views/Register.vue'
import ItemList from '../views/ItemList.vue'
import ItemDetail from '../views/ItemDetail.vue'
import Review from '../views/Review.vue'
import Pricing from '../views/Pricing.vue'
import Recognition from '../views/Recognition.vue'
import Assistant from '../views/Assistant.vue'
import Message from '../views/Message.vue'
import About from '../views/About.vue'
import Convention from '../views/Convention.vue'
import Help from '../views/Help.vue'
import Contact from '../views/Contact.vue'
import ElderlyMode from '../views/ElderlyMode.vue'
import AccessibleMode from '../views/AccessibleMode.vue'
import Profile from '../views/Profile.vue'
import AccountView from '../views/profile/AccountView.vue'
import LocationView from '../views/profile/LocationView.vue'
import NotificationsView from '../views/profile/NotificationsView.vue'
import AccessibilityView from '../views/profile/AccessibilityView.vue'
import FeedbackView from '../views/profile/FeedbackView.vue'
import ItemsView from '../views/profile/ItemsView.vue'
import CarbonView from '../views/profile/CarbonView.vue'
import FavoritesView from '../views/profile/FavoritesView.vue'
import DemandsView from '../views/profile/DemandsView.vue'
import ExchangesView from '../views/profile/ExchangesView.vue'
import RedemptionsView from '../views/profile/RedemptionsView.vue'
import RecycleView from '../views/profile/RecycleView.vue'
import DemandWall from '../views/DemandWall.vue'
import MerchantList from '../views/MerchantList.vue'
import MerchantDetail from '../views/MerchantDetail.vue'
// 商家工作台（阶段三）：独立布局 + 4 个页面 + 入驻页
import MerchantApply from '../views/merchant/Apply.vue'
import MerchantDashboard from '../views/merchant/Dashboard.vue'
import MerchantProducts from '../views/merchant/Products.vue'
import MerchantVerify from '../views/merchant/Verify.vue'
import MerchantSettings from '../views/merchant/Settings.vue'

// base 传入 import.meta.env.BASE_URL：与 vite.config.js 的 base 保持一致。
// 部署在站点根时 BASE_URL='/'，行为与改造前完全相同；
// 部署到子目录（VITE_BASE=/h5/）时路由前缀才不会丢。
const router = createRouter({ history: createWebHistory(import.meta.env.BASE_URL), routes: [
  { path: '/', component: Home }, { path: '/login', component: Login }, { path: '/register', component: Register },
  { path: '/items', component: ItemList }, { path: '/items/:id', component: ItemDetail },
  // 积分商城：商家列表与店铺商品都免登录可浏览，只有兑换那一步要求登录
  { path: '/merchant', component: MerchantList },
  { path: '/merchant/:id', component: MerchantDetail },
  // 商家工作台：meta.layout='merchant' → App.vue 换成 MerchantLayout（无 AppNav）；
  // merchantOnly → 守卫校验「已通过审核」，否则一律送 /merchant/apply。
  // ⚠ /merchant/apply 刻意**不挂** merchantOnly：否则未入驻用户会被自己重定向成死循环；
  //   它也留在 MainLayout（未入驻用户看到的是一个普通表单页）。
  // ⚠ 静态段与 /merchant/:id 通配段不冲突：vue-router 4 按 score 排序，与声明顺序无关。
  { path: '/merchant/apply', component: MerchantApply, meta: { requiresAuth: true } },
  { path: '/merchant/dashboard', component: MerchantDashboard, meta: { requiresAuth: true, layout: 'merchant', merchantOnly: true } },
  { path: '/merchant/products', component: MerchantProducts, meta: { requiresAuth: true, layout: 'merchant', merchantOnly: true } },
  { path: '/merchant/verify', component: MerchantVerify, meta: { requiresAuth: true, layout: 'merchant', merchantOnly: true } },
  { path: '/merchant/settings', component: MerchantSettings, meta: { requiresAuth: true, layout: 'merchant', merchantOnly: true } },
  { path: '/reviews', component: Review, meta: { requiresAuth: true } }, { path: '/pricing', component: Pricing, meta: { requiresAuth: true } },
  { path: '/recognition', component: Recognition, meta: { requiresAuth: true } },
  { path: '/assistant', component: Assistant, meta: { requiresAuth: true } },
  { path: '/messages', component: Message, meta: { requiresAuth: true } },
  { path: '/profile', component: Profile, meta: { requiresAuth: true } },
  // 个人中心子页面：平铺路由，各子页内部以 ProfileSubLayout 为模板根
  { path: '/profile/account', component: AccountView, meta: { requiresAuth: true } },
  { path: '/profile/location', component: LocationView, meta: { requiresAuth: true } },
  { path: '/profile/notifications', component: NotificationsView, meta: { requiresAuth: true } },
  { path: '/profile/accessibility', component: AccessibilityView, meta: { requiresAuth: true } },
  { path: '/profile/feedback', component: FeedbackView, meta: { requiresAuth: true } },
  // 第二 / 四区：我的物品、碳积分明细
  { path: '/profile/items', component: ItemsView, meta: { requiresAuth: true } },
  { path: '/profile/carbon', component: CarbonView, meta: { requiresAuth: true } },
  // 我的收藏：详情页右上角收藏按钮的目的地列表
  { path: '/profile/favorites', component: FavoritesView, meta: { requiresAuth: true } },
  // 我想要的：个人需求管理（发布 / 编辑 / 撤销 / 完成）
  { path: '/profile/demands', component: DemandsView, meta: { requiresAuth: true } },
  // 我的交换：订单列表（筛选 / 分页 / 确认 / 完成 / 取消 / 详情）
  { path: '/profile/exchanges', component: ExchangesView, meta: { requiresAuth: true } },
  // 我的兑换：积分商城兑换记录（4 个状态 Tab + 核销码放大展示）
  { path: '/profile/redemptions', component: RedemptionsView, meta: { requiresAuth: true } },
  // 我的回收单：平台回收记录（4 个状态 Tab + 待取件可取消退分）
  { path: '/profile/recycle', component: RecycleView, meta: { requiresAuth: true } },
  // 公开需求墙：不要求登录（未登录可浏览，点私信时才引导登录）
  { path: '/demands', component: DemandWall },
  // 兼容旧入口：/orders 曾是占位页，现统一收敛到 /profile/exchanges
  { path: '/orders', redirect: '/profile/exchanges' },
  { path: '/about', component: About }, { path: '/convention', component: Convention },
  { path: '/help', component: Help }, { path: '/contact', component: Contact },
  { path: '/elderly', component: ElderlyMode },
  { path: '/accessible', component: AccessibleMode },
] })
router.beforeEach(async (to) => {
  // 未登录优先判：直接回登录页并带上 redirect，**不发请求**
  // （否则会先吃后端 401，再被拦截器 window.location.href 硬跳，redirect 会丢）
  if (to.meta.requiresAuth && !localStorage.getItem('token')) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  // 商家工作台：只有「已通过审核」（status=1）能进，其余状态一律送回入驻页
  // —— Apply 页内部再按 0待审核/2已拒绝/3已停业 分叉展示，避免多做一个提示页。
  if (to.meta.merchantOnly) {
    const merchantStore = useMerchantStore()
    try {
      const data = await merchantStore.fetchInfo()
      if (Number(data?.merchant?.status) !== 1) return { path: '/merchant/apply' }
    } catch {
      // 身份校验失败（网络抖动 / 500）**不当作「不是商家」**：
      // 误判会把真实商家踢回入驻页并可能白白丢一次申请，故放行进页面由页面自己提示。
    }
  }
  return true
})
export default router
