<template>
  <div class="app-shell" :class="profileStore.rootClasses">
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

      <nav class="topnav">
        <RouterLink to="/items">探索物品</RouterLink>
        <RouterLink to="/recognition">物品识别</RouterLink>
        <RouterLink to="/pricing">智能定价</RouterLink>
        <RouterLink to="/reviews">社区评价</RouterLink>
        <RouterLink to="/assistant">智能体助手</RouterLink>
        <RouterLink to="/messages">我的私信</RouterLink>
      </nav>

      <div class="account">
        <template v-if="userStore.isLoggedIn">
          <RouterLink to="/profile" class="profile-link">个人中心</RouterLink>
          <span class="user-name">{{ userStore.user?.nickname || '居民' }}</span>
          <el-button link @click="userStore.logout">退出</el-button>
        </template>
        <template v-else>
          <RouterLink to="/login">登录</RouterLink>
          <RouterLink to="/register" class="signup">加入社区</RouterLink>
        </template>
      </div>
    </header>

    <main>
      <RouterView />
    </main>

    <footer v-if="route.path !== '/'" class="site-footer">
      闲物焕新计划 · 让每件物品抵达下一段故事
    </footer>

    <!-- 助老模式：全局悬浮语音入口（个人中心开启助老模式后显示） -->
    <RouterLink
      v-if="profileStore.elderlyMode && route.path !== '/elderly'"
      to="/elderly"
      class="voice-fab"
      role="button"
      aria-label="语音助手"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <rect x="9" y="3" width="6" height="11" rx="3" />
        <path d="M5 11a7 7 0 0 0 14 0" />
        <path d="M12 18v3" />
      </svg>
      <span>语音助手</span>
    </RouterLink>

    <!-- 全局悬浮返回首页按钮（首页本身不显示） -->
    <button
      v-if="route.path !== '/'"
      class="back-home"
      type="button"
      title="返回首页"
      aria-label="返回首页"
      @click="router.push('/')"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path d="M3 10.5 12 3l9 7.5" />
        <path d="M5 9.5V21h14V9.5" />
      </svg>
      <span>首页</span>
    </button>
  </div>
</template>

<script setup>
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { useUserStore } from '../store/user'
import { useProfileStore } from '../store/profile'

const userStore = useUserStore()
const profileStore = useProfileStore()
const route = useRoute()
const router = useRouter()
userStore.hydrate()
</script>

<style scoped>
.profile-link {
  padding: 4px 12px;
  border-radius: 999px;
  border: 1px solid rgba(47, 133, 90, 0.35);
  color: var(--green-primary, #2f855a);
  font-size: 13px;
  white-space: nowrap;
}

.voice-fab {
  position: fixed;
  left: 26px;
  bottom: 30px;
  z-index: 60;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-width: 64px;
  padding: 10px 14px;
  border-radius: 999px;
  background: var(--green-primary, #2f855a);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  box-shadow: 0 10px 24px rgba(47, 133, 90, 0.35);
  transition: transform 0.25s, box-shadow 0.25s;
}

.voice-fab:hover {
  transform: translateY(-4px);
  box-shadow: 0 14px 28px rgba(47, 133, 90, 0.45);
}

.voice-fab svg {
  width: 22px;
  height: 22px;
}

.back-home {
  position: fixed;
  right: 26px;
  bottom: 30px;
  z-index: 60;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  width: 52px;
  height: 52px;
  padding: 0;
  border: 1px solid rgba(47, 133, 90, 0.25);
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(8px);
  color: var(--green-primary, #2f855a);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 8px 22px rgba(31, 45, 61, 0.14);
  transition: transform 0.25s, box-shadow 0.25s, background 0.25s;
}

.back-home svg {
  width: 18px;
  height: 18px;
}

.back-home:hover {
  transform: translateY(-4px);
  background: var(--green-primary, #2f855a);
  color: #fff;
  box-shadow: 0 12px 26px rgba(47, 133, 90, 0.35);
}

@media (max-width: 1100px) {
  .topnav {
    gap: 14px;
  }
}

@media (max-width: 900px) {
  .topnav {
    gap: 8px;
    flex-wrap: wrap;
  }
}
</style>
