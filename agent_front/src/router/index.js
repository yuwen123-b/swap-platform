import { createRouter, createWebHistory } from 'vue-router'
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

const router = createRouter({ history: createWebHistory(), routes: [
  { path: '/', component: Home }, { path: '/login', component: Login }, { path: '/register', component: Register },
  { path: '/items', component: ItemList }, { path: '/items/:id', component: ItemDetail },
  { path: '/reviews', component: Review, meta: { requiresAuth: true } }, { path: '/pricing', component: Pricing, meta: { requiresAuth: true } },
  { path: '/recognition', component: Recognition, meta: { requiresAuth: true } },
  { path: '/assistant', component: Assistant, meta: { requiresAuth: true } },
  { path: '/messages', component: Message, meta: { requiresAuth: true } },
  { path: '/profile', component: Profile, meta: { requiresAuth: true } },
  { path: '/about', component: About }, { path: '/convention', component: Convention },
  { path: '/help', component: Help }, { path: '/contact', component: Contact },
  { path: '/elderly', component: ElderlyMode },
  { path: '/accessible', component: AccessibleMode },
] })
router.beforeEach((to) => { if (to.meta.requiresAuth && !localStorage.getItem('token')) return { path: '/login', query: { redirect: to.fullPath } } })
export default router
