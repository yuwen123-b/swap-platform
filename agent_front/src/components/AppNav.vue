<template>
  <header class="topbar">
    <RouterLink to="/" class="brand">
      <span class="brand-mark">
        <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M20 4C20 4 8.5 4 5 7.5C2.5 10 4 13.5 4 13.5C4 13.5 7.5 15 10 12.5C13.5 9 20 4 20 4Z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M4 20C4 20 6 14.5 10 12.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
        </svg>
      </span>
      <span>闲物<span class="cyan">焕新</span></span>
    </RouterLink>

    <!-- 桌面端主导航（≤767px 由样式整体隐藏，见 style 内 .is-mobile 区） -->
    <nav class="topnav">
      <RouterLink v-for="link in NAV_LINKS" :key="link.path" :to="link.path">
        {{ link.label }}
      </RouterLink>
    </nav>

    <div class="account">
      <template v-if="userStore.isLoggedIn">
        <!-- 私信入口：已从主导航移到此处（图标 + 未读角标），仅登录后显示 -->
        <RouterLink
          to="/messages"
          class="msg-entry"
          :aria-label="unreadCount > 0 ? `我的私信，${unreadCount} 条未读` : '我的私信'"
          title="我的私信"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
               stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="3" y="5" width="18" height="14" rx="2.5" />
            <path d="m3.6 7.2 8.4 5.8 8.4-5.8" />
          </svg>
          <span v-if="unreadCount > 0" class="msg-badge">{{ badgeText }}</span>
        </RouterLink>
        <span class="user-name">{{ userStore.user?.nickname || '居民' }}</span>
        <el-button link class="logout-btn" @click="userStore.logout">退出</el-button>

        <!-- 移动端：头像入口（点进个人中心）。桌面端 display:none -->
        <RouterLink to="/profile" class="avatar-dot" :aria-label="`个人中心，${userStore.user?.nickname || '居民'}`">
          {{ avatarText }}
        </RouterLink>
      </template>
      <template v-else>
        <RouterLink to="/login" class="login-link">登录</RouterLink>
        <RouterLink to="/register" class="signup">加入社区</RouterLink>
      </template>

      <!-- 移动端「更多」小菜单：收纳低频但重的工具入口（识别/定价/评价） -->
      <div class="more-wrap">
        <button
          type="button"
          class="more-btn"
          :aria-expanded="moreOpen ? 'true' : 'false'"
          aria-controls="nav-more-panel"
          aria-label="更多功能"
          @click="moreOpen = !moreOpen"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
               stroke-linecap="round" aria-hidden="true">
            <path d="M5 12h.01M12 12h.01M19 12h.01" />
          </svg>
        </button>

        <!-- 遮罩：点空白处收起（比全局监听 document 更省事，也顺手挡住穿透点击） -->
        <div v-if="moreOpen" class="more-mask" @click="moreOpen = false" />

        <div v-if="moreOpen" id="nav-more-panel" class="more-panel" role="menu">
          <RouterLink
            v-for="item in MORE_LINKS"
            :key="item.path"
            :to="item.path"
            class="more-item"
            role="menuitem"
            @click="moreOpen = false"
          >
            {{ item.label }}
          </RouterLink>
          <button
            v-if="userStore.isLoggedIn"
            type="button"
            class="more-item is-danger"
            role="menuitem"
            @click="onLogout"
          >
            退出登录
          </button>
        </div>
      </div>
    </div>
  </header>

  <!-- ============================================================
       移动端底部 Tab 栏（仅 ≤767px 显示）
       ① 只放 4 个最高频入口，保证单指可达；
       ② 识别/定价/评价收进顶栏「更多」，不塞进 Tab 以免挤成 6 项；
       ③ 用 isTabActive 做前缀匹配——vue-router 的 router-link-active
          按「路由记录父子关系」判定，/profile/exchanges 这类平铺子路由
          不会让 /profile 高亮，必须自己判。
       ============================================================ -->
  <nav class="mobile-tabbar" aria-label="移动端主导航">
    <RouterLink
      v-for="tab in TABS"
      :key="tab.path"
      :to="tab.path"
      class="tab-item"
      :class="{ 'is-active': isTabActive(tab.path) }"
      :aria-current="isTabActive(tab.path) ? 'page' : undefined"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
           stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path v-for="(d, i) in tab.icon" :key="i" :d="d" />
      </svg>
      <span>{{ tab.label }}</span>
      <span v-if="tab.path === '/profile' && unreadCount > 0" class="tab-dot" aria-hidden="true" />
    </RouterLink>
  </nav>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { getSessionList } from '../api/message'
import { useUserStore } from '../store/user'

// 主导航项：顺序即展示顺序，新增页面只需在此追加一项。
// 注意：「我的私信」已从主导航移到右侧 .account 区（图标入口 + 未读角标）——
// 原先的 8 项在 ≤1100px 就接近换行临界点，且私信是高频入口，
// 放图标比放文字更省空间（详见 .account 区）。
// 展示顺序按「先逛逛 → 工具 → 助手 → 商城 → 社区 → 我的」编排：
// 低频但重的工具（识别/定价）紧跟探索物品，商城与社区评价靠后，
// 个人中心固定收尾（惯例位置，用户扫视习惯最右）。
const NAV_LINKS = [
  { path: '/items', label: '探索物品' },
  { path: '/recognition', label: '物品识别' },
  { path: '/pricing', label: '智能定价' },
  { path: '/assistant', label: '智能体助手' },
  { path: '/merchant', label: '积分商城' },
  { path: '/reviews', label: '社区评价' },
  { path: '/profile', label: '个人中心' },
]

/* ---------- 移动端专用配置 ---------- */

// 底部 Tab：4 项。再多就会挤到 60px 以下，拇指也点不准。
// icon 用 path 数组，模板里 v-for 展开，避免为每个图标写一段 SVG 模板。
const TABS = [
  { path: '/items', label: '探索', icon: ['M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14Z', 'm20 20-3.6-3.6'] },
  { path: '/assistant', label: '助手', icon: ['M21 12a8 8 0 0 1-11.7 7.1L4 21l1.9-5.3A8 8 0 1 1 21 12Z'] },
  { path: '/merchant', label: '商城', icon: ['M6 8h12l-1.2 12H7.2L6 8Z', 'M9 8V6a3 3 0 0 1 6 0v2'] },
  { path: '/profile', label: '我的', icon: ['M12 4.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Z', 'M5 20c1.4-3.4 3.9-5 7-5s5.6 1.6 7 5'] },
]

// 「更多」只收桌面端有、但没进 Tab 的三项 + 退出登录
const MORE_LINKS = [
  { path: '/recognition', label: '物品识别' },
  { path: '/pricing', label: '智能定价' },
  { path: '/reviews', label: '社区评价' },
]

const userStore = useUserStore()
const route = useRoute()

const moreOpen = ref(false)

// 头像用昵称首字（无昵称兜底「居」），避免无头像资源时出现空白圆
const avatarText = computed(() => {
  const name = String(userStore.user?.nickname || '居民').trim()
  return name ? name.slice(0, 1) : '居'
})

// 前缀匹配：/profile/exchanges 也要让「我的」高亮
function isTabActive(path) {
  return route.path === path || route.path.startsWith(path + '/')
}

function onLogout() {
  moreOpen.value = false
  userStore.logout()
}

/* 未读角标：会话列表接口已返回 unread_count，前端求和即可（零后端改动） */
const unreadCount = ref(0)
// 超过 99 统一显示 99+，避免角标被数字撑破
const badgeText = computed(() => (unreadCount.value > 99 ? '99+' : String(unreadCount.value)))

async function loadUnread() {
  if (!userStore.isLoggedIn) {
    unreadCount.value = 0
    return
  }
  try {
    // skipErrorToast：角标是附属信息，接口抖动时不应弹错误提示打扰用户
    const sessions = await getSessionList({ skipErrorToast: true })
    const list = Array.isArray(sessions) ? sessions : sessions?.list || []
    unreadCount.value = list.reduce((sum, s) => sum + Number(s.unread_count || 0), 0)
  } catch {
    // 静默：拉取失败时保持上次的角标值，不影响导航
  }
}

// 登录态就绪后拉取；退出登录立即清零（避免角标残留）
watch(() => userStore.isLoggedIn, (logged) => {
  if (logged) loadUnread()
  else unreadCount.value = 0
}, { immediate: true })

// 离开私信页后刷新：在会话页读过消息，返回导航时角标应同步减少
watch(() => route.path, (path, from) => {
  if (from === '/messages' && path !== '/messages') loadUnread()
  // 路由一跳就收起「更多」，否则面板会悬在新页面上
  moreOpen.value = false
})

// 轻量轮询：长时间停留页面时角标也能更新（60s 一次，成本可忽略）
let timer = null
onMounted(() => {
  timer = window.setInterval(loadUnread, 60000)
})
onBeforeUnmount(() => {
  if (timer) window.clearInterval(timer)
})
</script>

<style scoped>
/* 导航项样式统一由 styles/global.css 提供（.topbar / nav.topnav / .account 等），
   此处仅保留原布局中特有的局部样式。
   私信入口（.msg-entry / .msg-badge）同样在 global.css 中定义，
   以便助老模式与高对比度主题能统一改写。 */

/* ============================================================
   移动端新增元素：默认全部隐藏，只在 ≤767px 显示。
   这样 PC 端 DOM 多几个节点，但不参与布局、不影响任何既有样式。
   ============================================================ */
.more-wrap,
.avatar-dot,
.login-link,
.mobile-tabbar {
  display: none;
}

@media (max-width: 767px) {
  /* ---------- 顶栏：变成"Logo + 右侧图标"的单行紧凑条 ---------- */
  .topbar {
    height: 56px;
    min-height: 56px;
    margin: 0;
    padding: 0 14px;
    gap: 10px;
    flex-wrap: nowrap;
    border-radius: 0;
    border-left: none;
    border-right: none;
    border-top: none;
  }

  .brand {
    font-size: 17px;
    gap: 0;
  }

  .brand-mark {
    width: 28px;
    height: 28px;
    margin-right: 8px;
    border-radius: 9px;
  }

  .brand-mark svg {
    width: 16px;
    height: 16px;
  }

  /* 7 项文字导航整体隐藏，改由底部 Tab + 「更多」承接 */
  .topbar nav.topnav {
    display: none;
  }

  .account {
    gap: 8px;
    font-size: 14px;
  }

  /* 昵称与"退出"是低优先级信息：手机宽度留给更多/头像，
     退出登录已移进「更多」面板，不会丢功能。 */
  .user-name,
  .logout-btn {
    display: none;
  }

  .msg-entry {
    width: 34px;
    height: 34px;
  }

  .avatar-dot {
    display: grid;
    place-items: center;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: linear-gradient(135deg, var(--green-primary), var(--teal));
    color: #fff;
    font-size: 14px;
    font-weight: 600;
    line-height: 1;
    flex-shrink: 0;
  }

  .login-link {
    display: inline-block;
    padding: 6px 12px;
    border: 1px solid var(--green-primary);
    border-radius: 999px;
    color: var(--green-primary);
    font-size: 13px;
    font-weight: 500;
  }

  .signup {
    display: none;
  }

  /* ---------- 「更多」按钮 ---------- */
  .more-wrap {
    display: block;
    position: relative;
    flex-shrink: 0;
  }

  .more-btn {
    display: grid;
    place-items: center;
    width: 34px;
    height: 34px;
    padding: 0;
    border: none;
    border-radius: 50%;
    background: transparent;
    color: var(--text-secondary);
    cursor: pointer;
  }

  .more-btn svg {
    width: 22px;
    height: 22px;
  }

  .more-btn[aria-expanded='true'] {
    background: var(--green-soft);
    color: var(--green-primary);
  }

  .more-mask {
    position: fixed;
    inset: 0;
    z-index: 60;
    background: transparent;
  }

  .more-panel {
    position: absolute;
    top: calc(100% + 8px);
    right: 0;
    z-index: 61;
    min-width: 140px;
    padding: 6px;
    border: 1px solid rgba(35, 66, 54, 0.1);
    border-radius: 14px;
    background: #fff;
    box-shadow: 0 14px 34px rgba(31, 45, 61, 0.16);
  }

  .more-item {
    display: block;
    width: 100%;
    padding: 11px 12px;
    border: none;
    border-radius: 9px;
    background: transparent;
    color: var(--text-primary);
    font-size: 15px;
    text-align: left;
    cursor: pointer;
  }

  .more-item:active {
    background: var(--green-soft);
  }

  .more-item.is-danger {
    margin-top: 4px;
    border-top: 1px solid rgba(35, 66, 54, 0.08);
    border-radius: 0 0 9px 9px;
    color: #c53030;
  }

  /* ---------- 底部 Tab 栏 ---------- */
  .mobile-tabbar {
    display: flex;
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    /* 安全区：iPhone 底部小横条，不加会压住最后一行文字 */
    padding-bottom: env(safe-area-inset-bottom, 0px);
    z-index: 55;
    border-top: 1px solid rgba(35, 66, 54, 0.08);
    background: rgba(255, 255, 255, 0.94);
    backdrop-filter: blur(18px);
    -webkit-backdrop-filter: blur(18px);
  }

  .tab-item {
    position: relative;
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 3px;
    /* 44px 是 iOS HIG 的最小可点尺寸，低于它拇指容易点空 */
    min-height: 54px;
    padding: 7px 0 6px;
    color: var(--text-secondary);
    font-size: 11px;
    font-weight: 500;
    transition: color 0.2s;
  }

  .tab-item svg {
    width: 22px;
    height: 22px;
  }

  .tab-item.is-active {
    color: var(--green-primary);
    font-weight: 600;
  }

  /* 激活态用顶部短横线，比整块变色更克制，也不会遮挡内容 */
  .tab-item.is-active::before {
    content: '';
    position: absolute;
    top: 0;
    left: 50%;
    width: 22px;
    height: 2.5px;
    border-radius: 0 0 2px 2px;
    background: linear-gradient(90deg, var(--green-primary), var(--teal));
    transform: translateX(-50%);
  }

  .tab-item:active {
    background: var(--green-softer);
  }

  /* 我的 Tab 上的未读小红点（私信角标在顶栏已有一个，这里只做提示） */
  .tab-dot {
    position: absolute;
    top: 6px;
    right: calc(50% - 15px);
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #e53935;
  }
}
</style>
