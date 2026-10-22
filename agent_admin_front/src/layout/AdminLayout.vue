<template>
  <el-container class="admin-layout">
    <el-aside width="220px" class="aside">
      <div class="logo">
        <span class="logo-icon">♻</span>
        <span class="logo-text">旧物互换管理端</span>
      </div>
      <el-menu :default-active="$route.path" router class="menu" background-color="#ffffff" text-color="#4b5563" active-text-color="#2f855a">
        <template v-for="item in visibleMenus" :key="item.path">
          <el-sub-menu v-if="item.children" :index="item.path">
            <template #title>
              <el-icon><component :is="item.icon" /></el-icon>
              <span>{{ item.title }}</span>
            </template>
            <el-menu-item v-for="child in item.children" :key="child.path" :index="child.path">
              {{ child.title }}
            </el-menu-item>
          </el-sub-menu>
          <el-menu-item v-else :index="item.path">
            <el-icon><component :is="item.icon" /></el-icon>
            <span>{{ item.title }}</span>
          </el-menu-item>
        </template>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div class="platform">{{ platformName }}</div>
        <div class="admin-info">
          <el-tag :type="roleTagType" size="small" effect="light">{{ roleName }}</el-tag>
          <span class="name">{{ store.adminInfo?.real_name || store.adminInfo?.username }}</span>
          <el-button link type="danger" @click="onLogout">退出登录</el-button>
        </div>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'

import { getSystemConfig } from '@/api/system'
import { useAdminStore } from '@/store/admin'

const store = useAdminStore()
const router = useRouter()
const platformName = ref('社区旧物互换平台')

const menus = [
  { path: '/dashboard', title: '数据看板', icon: 'DataAnalysis', roles: [1, 2, 3] },
  { path: '/users', title: '用户管理', icon: 'User', roles: [1, 2, 3] },
  {
    path: '/items',
    title: '物品管理',
    icon: 'Goods',
    roles: [1, 2, 3],
    children: [
      { path: '/items', title: '物品列表', roles: [1, 2, 3] },
      { path: '/items/audit', title: '物品审核', roles: [1, 2, 3] },
    ],
  },
  // 标题带「物品交换」以区别于「商家管理 → 兑换订单」（两套订单数据源与状态枚举完全不同）
  { path: '/orders', title: '物品交换订单', icon: 'Tickets', roles: [1, 2, 3] },
  {
    path: '/merchant',
    title: '商家管理',
    icon: 'Shop',
    roles: [1, 2, 3],
    children: [
      { path: '/merchant/list', title: '商家列表', roles: [1, 2, 3] },
      { path: '/merchant/orders', title: '兑换订单', roles: [1, 2, 3] },
      { path: '/merchant/settlements', title: '结算管理', roles: [1, 2, 3] },
    ],
  },
  {
    path: '/recycle',
    title: '平台回收',
    icon: 'RefreshLeft',
    roles: [1, 2],
    children: [
      { path: '/recycle/list', title: '回收单列表', roles: [1, 2] },
      { path: '/recycle/stock', title: '平台库存', roles: [1, 2] },
      { path: '/recycle/sales', title: '销售记录', roles: [1, 2] },
      { path: '/recycle/stats', title: '运营数据看板', roles: [1, 2] },
    ],
  },
  {
    path: '/community',
    title: '社区管理',
    icon: 'ChatDotRound',
    roles: [1, 2, 3],
    children: [
      { path: '/community/posts', title: '帖子管理', roles: [1, 2, 3] },
      { path: '/community/reports', title: '举报处理', roles: [1, 2, 3] },
    ],
  },
  { path: '/points', title: '积分管理', icon: 'Coin', roles: [1, 2, 3] },
  { path: '/ai-monitor', title: 'AI 监控', icon: 'Monitor', roles: [1, 2] },
  { path: '/feedback', title: '评价情感分析', icon: 'ChatLineSquare', roles: [1, 2] },
  { path: '/admins', title: '管理员账号', icon: 'Avatar', roles: [1] },
  { path: '/system', title: '系统配置', icon: 'Setting', roles: [1] },
]

const visibleMenus = computed(() =>
  menus
    .filter((m) => m.roles.includes(store.role))
    .map((m) =>
      m.children
        ? { ...m, children: m.children.filter((c) => c.roles.includes(store.role)) }
        : m,
    )
    .filter((m) => !m.children || m.children.length > 0),
)

const roleName = computed(() => ({ 1: '超级管理员', 2: '运营专员', 3: '审核员' }[store.role] || '未知'))
const roleTagType = computed(() => ({ 1: 'danger', 2: 'warning', 3: 'success' }[store.role] || 'info'))

async function onLogout() {
  await ElMessageBox.confirm('确定退出登录吗？', '提示', { type: 'warning' })
  store.logout()
  router.push('/login')
}

onMounted(async () => {
  if (store.role === 1) {
    try {
      const res = await getSystemConfig()
      if (res.data?.platform_name) platformName.value = res.data.platform_name
    } catch {
      /* 忽略，用默认名 */
    }
  }
})
</script>

<style scoped>
.admin-layout {
  height: 100%;
}

.aside {
  background: #fff;
  border-right: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border-bottom: 1px solid #f0f0f0;
}

.logo-icon {
  font-size: 22px;
  color: #2f855a;
}

.logo-text {
  font-size: 16px;
  font-weight: 600;
  color: #2f855a;
}

.menu {
  border-right: none;
  flex: 1;
}

.menu :deep(.el-menu-item.is-active) {
  background: #e5f2eb;
  border-right: 3px solid #2f855a;
}

.header {
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.platform {
  font-size: 15px;
  font-weight: 600;
  color: #374151;
}

.admin-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.name {
  color: #374151;
  font-size: 14px;
}

.main {
  background: #f4f7f5;
  padding: 20px;
  overflow-y: auto;
}
</style>
