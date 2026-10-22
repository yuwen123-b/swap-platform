<template>
  <div class="mw-shell" :class="profileStore.rootClasses">
    <!-- ===== 顶栏：品牌 + 店铺身份 + 两个出口 ===== -->
    <header class="mw-topbar">
      <div class="mw-brand">
        <span class="mw-brand-mark" aria-hidden="true">🏪</span>
        <span class="mw-brand-text">
          <span class="mw-brand-name">闲物焕新</span>
          <span class="mw-brand-sub">商家工作台</span>
        </span>
      </div>

      <div class="mw-topbar-right">
        <span class="mw-shop">
          <span class="mw-shop-name">{{ shopName }}</span>
          <!-- 店铺状态：第四套 ms-* 状态类名（语义命名，不数字命名） -->
          <span class="status-tag" :class="shopStatusClass">{{ shopStatusLabel }}</span>
        </span>
        <button type="button" class="mw-ghost" @click="router.push('/merchant')">
          返回积分商城
        </button>
        <button type="button" class="mw-ghost mw-exit" @click="onLogout">退出</button>
      </div>
    </header>

    <div class="mw-body">
      <!-- ===== 侧边栏：4 个菜单 ===== -->
      <nav class="mw-side" aria-label="商家工作台菜单">
        <RouterLink
          v-for="item in MENU"
          :key="item.path"
          :to="item.path"
          class="mw-nav-item"
          active-class="active"
        >
          <span class="mw-nav-icon" aria-hidden="true">{{ item.icon }}</span>
          <span class="mw-nav-label">{{ item.label }}</span>
        </RouterLink>
      </nav>

      <!-- ===== 内容区 ===== -->
      <div class="mw-main">
        <slot />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { useMerchantStore } from '../store/merchant'
import { useProfileStore } from '../store/profile'
import { useUserStore } from '../store/user'

/**
 * 商家工作台独立布局。
 *
 * 【为什么是「独立布局 + App.vue 按 meta.layout 切换」而不是嵌套路由】
 * 项目现有 32 条路由全是平铺的，且 `/merchant` 已被积分商城首页占用
 * （它必须留在带 AppNav 的 MainLayout 里）。若把 /merchant 改成带 children
 * 的父路由，阶段二验证过的商城首页与导航都要跟着迁路径。
 * 因此照「布局由路由 meta 决定」来做：App.vue 见 meta.layout==='merchant'
 * 就渲染本布局并把 <RouterView/> 塞进 slot，其余路由继续走 MainLayout。
 *
 * 【为什么这里要自己调 hydrate()】
 * 助老模式 / 高对比度的类名是挂在 <html> 上的（profileStore.syncDom()），
 * 而原先只有 MainLayout 里调用了 userStore.hydrate()（内部会 applyFromUser +
 * 后台同步档案）。绕开 MainLayout 后若不补这一句，直接刷新 /merchant/dashboard
 * 时主题类名不会挂上 —— 助老与高对比度对工作台整体失效。
 * hydrate() 是幂等的（读本地缓存 + 后台同步），代价可忽略。
 */
const router = useRouter()
const merchantStore = useMerchantStore()
const profileStore = useProfileStore()
const userStore = useUserStore()

userStore.hydrate()
// 兜底：守卫已经取过一次（走缓存）；这里是直连/刷新时补齐顶栏店铺名。
// 失败保持静默 —— 错误提示由守卫或页面负责，布局层不抢镜。
if (!merchantStore.loaded) merchantStore.fetchInfo().catch(() => {})

const MENU = [
  { path: '/merchant/dashboard', label: '数据看板', icon: '📊' },
  { path: '/merchant/products', label: '商品管理', icon: '🎁' },
  { path: '/merchant/verify', label: '核销订单', icon: '✅' },
  { path: '/merchant/settings', label: '店铺设置', icon: '⚙️' },
]

const shopName = computed(() => merchantStore.info?.name || '我的店铺')

// 店铺状态 → 标签文案与 ms-* 类名（与 applicant 页同一套语义）
const SHOP_STATUS = {
  0: { label: '审核中', cls: 'ms-pending' },
  1: { label: '已通过', cls: 'ms-approved' },
  2: { label: '已拒绝', cls: 'ms-rejected' },
  3: { label: '已停业', cls: 'ms-closed' },
}

const shopStatusLabel = computed(() => SHOP_STATUS[merchantStore.status]?.label || '未知')
const shopStatusClass = computed(() => SHOP_STATUS[merchantStore.status]?.cls || 'ms-closed')

function onLogout() {
  userStore.logout()
  merchantStore.reset()
  router.push('/login')
}
</script>

<style scoped>
/* ============================================================
   局部设计令牌：所有工作台页面通过 CSS 变量继承复用
   （自定义属性会沿 DOM 树继承，页面的 scoped 样式里可直接 var()）
   ============================================================ */
.mw-shell {
  --mw-green: var(--green-primary, #2f855a);
  --mw-text: var(--text-primary, #1f2d3d);
  --mw-text-sub: var(--text-secondary, #6b7280);
  --mw-bg: #f4f6f5;
  --mw-card: #ffffff;
  --mw-border: #e5e7eb;
  --mw-track: #e5e7eb;
  --mw-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  --mw-shadow-hover: 0 4px 16px rgba(0, 0, 0, 0.08);
  /* 工作台根元素不用 <main>：global.css 的 main { width: min(1180px, 88vw) }
     会把「侧边栏 + 内容区」整体压窄，工作台自带宽度更合适 */
  min-height: 100vh;
  background: var(--mw-bg);
  color: var(--mw-text);
}

/* ---------- 顶栏 ---------- */
.mw-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 12px 22px;
  background: var(--mw-card);
  border-bottom: 1px solid var(--mw-border);
}

.mw-brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.mw-brand-mark {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  font-size: 20px;
  background: linear-gradient(135deg, var(--green-softer, #e8f5e9), var(--teal-soft, #e0f2f1));
  border: 1px solid var(--mw-border);
  border-radius: 12px;
}

.mw-brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
}

.mw-brand-name {
  font-size: 17px;
  font-weight: 800;
  letter-spacing: -0.2px;
  color: var(--mw-text);
}

.mw-brand-sub {
  font-size: 12px;
  font-weight: 600;
  color: var(--mw-green);
}

.mw-topbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.mw-shop {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--mw-text);
}

.mw-shop-name {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mw-ghost {
  min-height: 34px;
  padding: 6px 14px;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  color: var(--mw-text-sub);
  background: var(--mw-card);
  border: 1px solid var(--mw-border);
  border-radius: 999px;
  cursor: pointer;
  transition: color 0.2s ease, border-color 0.2s ease;
}

.mw-ghost:hover {
  color: var(--mw-green);
  border-color: var(--mw-green);
}

.mw-ghost:focus-visible {
  outline: 3px solid var(--mw-green);
  outline-offset: 2px;
}

/* ---------- 主体：侧栏 + 内容 ---------- */
.mw-body {
  display: flex;
  align-items: stretch;
  gap: 0;
  width: min(1240px, 96vw);
  margin: 0 auto;
  padding: 22px 0 40px;
}

.mw-side {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 0 0 190px;
  align-self: flex-start;
  position: sticky;
  top: 18px;
  padding: 10px;
  background: var(--mw-card);
  border: 1px solid var(--mw-border);
  border-radius: 16px;
  box-shadow: var(--mw-shadow);
}

.mw-nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 46px;
  padding: 10px 14px;
  font-size: 15px;
  font-weight: 600;
  color: var(--mw-text-sub);
  text-decoration: none;
  border-radius: 12px;
  transition: color 0.2s ease, background 0.2s ease;
}

.mw-nav-item:hover {
  color: var(--mw-green);
  background: var(--mw-bg);
}

.mw-nav-item.active {
  color: #fff;
  background: var(--mw-green);
}

.mw-nav-item:focus-visible {
  outline: 3px solid var(--mw-green);
  outline-offset: 2px;
}

.mw-nav-icon {
  font-size: 18px;
}

.mw-main {
  flex: 1 1 auto;
  min-width: 0;
  padding-left: 22px;
}

/* 窄屏：侧栏变横向滚动条，内容占满 */
@media (max-width: 860px) {
  .mw-body {
    flex-direction: column;
    gap: 14px;
    padding-top: 14px;
  }

  .mw-side {
    position: static;
    flex: 0 0 auto;
    flex-direction: row;
    overflow-x: auto;
    width: 100%;
  }

  .mw-nav-item {
    flex: 0 0 auto;
  }

  .mw-main {
    padding-left: 0;
  }
}
</style>

<!-- ============================================================
     非 scoped：
     1) 第四套状态类名 ms-*（语义命名）——工作台内所有页面共用
     2) 根级主题（html.theme-high-contrast / html.mode-elderly）必须非 scoped
     全部以 .mw-shell 前缀隔离，不污染其它页面。
     ============================================================ -->
<style>
/* ---------- ms-* 状态标签（第四套） ----------
   项目已有三套：s-*（物品/需求）、os-*（交换单）、rs-*（兑换单，用户侧）。
   工作台用第四套 ms-*，语义命名而非数字命名：
   数字类名跨文件复用时极易错位（阶段二就踩过「已核销显示成灰色」）。
   ⚠ 入驻页（/merchant/apply）不在本布局内，它自带一份**同类名**的规则，
     两处都以各自页面前缀隔离，不会互相影响。 */
/* ============================================================
   工作台通用骨架（4 个页面共用；非 scoped 才能让页面直接写类名）
   页面自己的 scoped 样式负责细节，骨架类只保证「同一套卡片 / 标题 / 按钮」。
   ============================================================ */
.mw-shell .mw-page {
  display: block;
}

.mw-shell .mw-page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 18px;
}

.mw-shell .mw-page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 800;
  letter-spacing: -0.3px;
  color: var(--mw-text);
}

.mw-shell .mw-page-desc {
  margin: 6px 0 0;
  font-size: 14px;
  line-height: 1.7;
  color: var(--mw-text-sub);
}

.mw-shell .mw-card {
  padding: 20px;
  background: var(--mw-card);
  border: 1px solid var(--mw-border);
  border-radius: 16px;
  box-shadow: var(--mw-shadow);
}

.mw-shell .mw-card + .mw-card {
  margin-top: 18px;
}

.mw-shell .mw-card-title {
  margin: 0 0 14px;
  font-size: 16px;
  font-weight: 700;
  color: var(--mw-text);
}

.mw-shell .mw-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.mw-shell .mw-card-head .mw-card-title {
  margin: 0;
}

.mw-shell .mw-empty {
  padding: 26px 12px;
  font-size: 14px;
  line-height: 1.8;
  text-align: center;
  color: var(--mw-text-sub);
}

.mw-shell .mw-error {
  padding: 12px 14px;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
  color: #b91c1c;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 10px;
}

/* 原生按钮：工作台里 el-button 与原生按钮混用会视觉不一致，
   统一用 el-button 做主操作，次要操作用 .mw-btn */
.mw-shell .mw-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 36px;
  padding: 7px 16px;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  color: var(--mw-text);
  background: var(--mw-card);
  border: 1px solid var(--mw-border);
  border-radius: 999px;
  cursor: pointer;
  white-space: nowrap;
  transition: color 0.2s ease, border-color 0.2s ease, background 0.2s ease;
}

.mw-shell .mw-btn:hover:not(:disabled) {
  color: var(--mw-green);
  border-color: var(--mw-green);
}

.mw-shell .mw-btn:focus-visible {
  outline: 3px solid var(--mw-green);
  outline-offset: 2px;
}

.mw-shell .mw-btn:disabled {
  cursor: default;
  opacity: 0.55;
}

.mw-shell .mw-btn.primary {
  color: #fff;
  background: var(--mw-green);
  border-color: var(--mw-green);
}

.mw-shell .mw-btn.danger {
  color: #b91c1c;
  border-color: #fecaca;
}

.mw-shell .mw-btn.danger:hover:not(:disabled) {
  color: #fff;
  background: #dc2626;
  border-color: #dc2626;
}

.mw-shell .status-tag {
  display: inline-block;
  flex-shrink: 0;
  padding: 2px 10px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.7;
  color: #fff;
  border-radius: 999px;
  white-space: nowrap;
}

/* ============================================================
   高对比度：局部令牌改纯黑 + 白描边；状态标签改浅底黑字
   ============================================================ */
.mw-shell .ms-pending {
  background: #f59e0b; /* 待审核：暖色，提示「等结果」 */
}

.mw-shell .ms-approved {
  background: #16a34a; /* 已通过 */
}

.mw-shell .ms-rejected {
  background: #dc2626; /* 已拒绝：红色，需处理 */
}

.mw-shell .ms-closed {
  background: #8a8a8a; /* 已停业：中性 */
}

/* 商品状态 */
.mw-shell .ms-online {
  background: #16a34a; /* 上架中 */
}

.mw-shell .ms-offline {
  background: #8a8a8a; /* 已下架 */
}

/* 商家侧兑换单状态（区别于用户侧 rs-* 的实心胶囊：这里是小圆点 + 文字） */
.mw-shell .ms-redeem-wait {
  background: #f59e0b;
}

.mw-shell .ms-redeem-done {
  background: #16a34a;
}

.mw-shell .ms-redeem-expired {
  background: #8a8a8a;
}

.mw-shell .ms-redeem-cancelled {
  background: #6b7280;
}

/* ============================================================
   高对比度：局部令牌改纯黑 + 白描边；状态标签改浅底黑字
   ============================================================ */
html.theme-high-contrast .mw-shell {
  --mw-card: #000000;
  --mw-bg: #000000;
  --mw-border: #ffffff;
  --mw-track: rgba(255, 255, 255, 0.35);
  --mw-shadow: none;
  --mw-shadow-hover: none;
}

html.theme-high-contrast .mw-shell .status-tag {
  color: #000000;
}

html.theme-high-contrast .mw-shell .ms-pending {
  background: #fcd34d;
}

html.theme-high-contrast .mw-shell .ms-approved,
html.theme-high-contrast .mw-shell .ms-online,
html.theme-high-contrast .mw-shell .ms-redeem-done {
  background: #4ade80;
}

html.theme-high-contrast .mw-shell .ms-rejected {
  background: #fca5a5;
}

html.theme-high-contrast .mw-shell .ms-closed,
html.theme-high-contrast .mw-shell .ms-offline,
html.theme-high-contrast .mw-shell .ms-redeem-expired,
html.theme-high-contrast .mw-shell .ms-redeem-cancelled {
  background: #e5e5e5;
}

/* emoji 占位块 / 品牌块在纯黑底上必须描边才看得见 */
html.theme-high-contrast .mw-shell .mw-brand-mark {
  background: #000000;
  border-color: #ffffff;
}

html.theme-high-contrast .mw-shell .mw-error {
  color: #fca5a5;
  background: #000000;
  border-color: #fca5a5;
}

html.theme-high-contrast .mw-shell .mw-btn.danger {
  color: #fca5a5;
  border-color: #fca5a5;
}

html.theme-high-contrast .mw-shell .mw-btn.danger:hover:not(:disabled) {
  color: #000000;
  background: #fca5a5;
  border-color: #fca5a5;
}

html.theme-high-contrast .mw-shell .mw-nav-item.active {
  color: #000000;
  background: #4ade80;
}

/* ============================================================
   助老模式：字号与点击目标整体放大（≥60px）
   ============================================================ */
html.mode-elderly .mw-shell .mw-brand-name {
  font-size: 22px;
}

html.mode-elderly .mw-shell .mw-brand-sub,
html.mode-elderly .mw-shell .mw-shop,
html.mode-elderly .mw-shell .status-tag {
  font-size: 18px;
}

html.mode-elderly .mw-shell .mw-ghost,
html.mode-elderly .mw-shell .mw-nav-item {
  min-height: 60px;
  padding: 12px 20px;
  font-size: 18px;
}

html.mode-elderly .mw-shell .mw-side {
  flex-basis: 220px;
}

html.mode-elderly .mw-shell .mw-nav-icon {
  font-size: 22px;
}

html.mode-elderly .mw-shell .mw-page-title {
  font-size: 30px;
}

html.mode-elderly .mw-shell .mw-page-desc,
html.mode-elderly .mw-shell .mw-empty,
html.mode-elderly .mw-shell .mw-error {
  font-size: 18px;
}

html.mode-elderly .mw-shell .mw-card-title {
  font-size: 22px;
}

html.mode-elderly .mw-shell .mw-btn,
html.mode-elderly .mw-shell .el-button {
  min-height: 60px;
  padding: 12px 24px;
  font-size: 18px;
}
</style>
