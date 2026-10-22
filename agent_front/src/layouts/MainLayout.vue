<template>
  <div class="app-shell" :class="profileStore.rootClasses">
    <AppNav />

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
import AppNav from '../components/AppNav.vue'
import { useUserStore } from '../store/user'
import { useProfileStore } from '../store/profile'

const userStore = useUserStore()
const profileStore = useProfileStore()
const route = useRoute()
const router = useRouter()
userStore.hydrate()
</script>

<style scoped>
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

/* ---------- 移动端：两个悬浮按钮与底部 Tab 栏避让 ----------
   ① .back-home 隐藏：底部 Tab 的「探索」就是主入口，Logo 也能回首页，
      再留一个悬浮"首页"会和 Tab 栏叠在一起，反而挡住内容。
   ② .voice-fab 上移到 Tab 栏之上（54px 栏高 + 12px 间隙），
      只在开启助老模式时出现，不挡内容区。 */
@media (max-width: 767px) {
  .back-home {
    display: none;
  }

  .voice-fab {
    left: 14px;
    bottom: calc(66px + env(safe-area-inset-bottom, 0px));
    min-width: 58px;
    padding: 8px 12px;
    font-size: 12px;
  }

  .voice-fab svg {
    width: 20px;
    height: 20px;
  }
}
</style>
