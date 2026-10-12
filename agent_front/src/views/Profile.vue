<template>
  <div class="page profile-page">
    <p class="eyebrow">个人中心</p>
    <h1 class="page-title">个人中心</h1>
    <p class="lead">管理你的资料、语言与无障碍设置，配置会保存到账号</p>

    <!-- 基础信息 -->
    <section class="profile-card glass-card">
      <h2 class="card-title">基础信息</h2>
      <div class="basic-row">
        <div class="avatar-circle" aria-label="头像">
          {{ avatarText }}
        </div>
        <div class="basic-meta">
          <div class="meta-label">昵称</div>
          <div class="meta-value">{{ userStore.user?.nickname || '居民' }}</div>
        </div>
      </div>
    </section>

    <!-- 无障碍设置 -->
    <section class="profile-card glass-card">
      <h2 class="card-title">无障碍设置</h2>

      <!-- 助老模式 -->
      <div class="setting-item">
        <div class="setting-text">
          <div class="setting-name">助老模式</div>
          <div class="setting-desc">开启后界面放大、语音优先，适合老年用户</div>
        </div>
        <el-switch v-model="form.elderlyMode" size="large" aria-label="助老模式" />
      </div>

      <!-- 无障碍模式 -->
      <div class="setting-item column">
        <div class="setting-text">
          <div class="setting-name">无障碍模式</div>
          <div class="setting-desc">选择后系统自动调整交互方式和交接方式推荐</div>
        </div>
        <el-radio-group v-model="form.accessibilityMode" class="mode-group">
          <el-radio-button value="normal">普通</el-radio-button>
          <el-radio-button value="visually_impaired">视障模式</el-radio-button>
          <el-radio-button value="mobility_impaired">肢体障碍模式</el-radio-button>
        </el-radio-group>
      </div>

      <!-- 行动能力：仅肢体障碍模式显示 -->
      <div v-if="form.accessibilityMode === 'mobility_impaired'" class="setting-item column">
        <div class="setting-text">
          <div class="setting-name">行动能力</div>
        </div>
        <el-radio-group v-model="form.mobilityLevel" class="mode-group">
          <el-radio-button value="free">自如</el-radio-button>
          <el-radio-button value="limited">受限</el-radio-button>
          <el-radio-button value="assisted">需协助</el-radio-button>
        </el-radio-group>
      </div>

      <!-- 高对比度 -->
      <div class="setting-item">
        <div class="setting-text">
          <div class="setting-name">高对比度</div>
          <div class="setting-desc">黑底白字，更强对比，适合弱视用户</div>
        </div>
        <el-switch v-model="form.highContrast" size="large" aria-label="高对比度" />
      </div>

      <el-button type="primary" class="save-btn" :loading="saving" @click="onSave">
        保存设置
      </el-button>
    </section>

    <!-- 交互向导（原独立页面保留为向导，从个人中心进入） -->
    <section class="profile-card glass-card">
      <h2 class="card-title">交互向导</h2>
      <div class="wizard-row">
        <RouterLink to="/elderly" class="wizard-entry">
          <span class="wizard-name">语音助手向导</span>
          <span class="wizard-desc">打开大字语音交互页面</span>
        </RouterLink>
        <RouterLink to="/accessible" class="wizard-entry">
          <span class="wizard-name">无障碍交互向导</span>
          <span class="wizard-desc">打开语音标签与交接方式演示页</span>
        </RouterLink>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '../store/user'
import { useProfileStore } from '../store/profile'
const userStore = useUserStore()
const profileStore = useProfileStore()
const router = useRouter()

const saving = ref(false)

const form = reactive({
  elderlyMode: false,
  accessibilityMode: 'normal',
  mobilityLevel: 'free',
  highContrast: false,
})

// 头像兜底：昵称首字
const avatarText = computed(() => {
  const name = userStore.user?.nickname || ''
  return name ? name.charAt(0).toUpperCase() : '居民'.charAt(0)
})

// 全局档案 -> 本地表单（fetchProfile 返回后也会同步）
watch(
  () => [
    profileStore.elderlyMode,
    profileStore.accessibilityMode,
    profileStore.mobilityLevel,
    profileStore.highContrast,
  ],
  ([elderly, mode, mobility, contrast]) => {
    form.elderlyMode = elderly
    form.accessibilityMode = mode
    form.mobilityLevel = mobility
    form.highContrast = contrast
  },
  { immediate: true },
)

// 未登录不应到达此页（路由守卫也会拦截），双保险
if (!userStore.isLoggedIn) {
  ElMessage.warning('请先登录后再保存个人设置')
  router.replace({ path: '/login', query: { redirect: '/profile' } })
}

async function onSave() {
  if (!userStore.isLoggedIn) {
    ElMessage.warning('请先登录后再保存个人设置')
    router.push('/login')
    return
  }
  saving.value = true
  try {
    await profileStore.saveProfile({
      elderly_mode: form.elderlyMode ? 1 : 0,
      accessibility_mode: form.accessibilityMode,
      mobility_level: form.mobilityLevel,
      high_contrast: form.highContrast ? 1 : 0,
    })
    ElMessage.success('设置已保存')
  } catch {
    ElMessage.error('保存失败，请稍后再试')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.profile-page {
  max-width: 820px;
}

.profile-card {
  margin-top: 24px;
  padding: 28px 30px;
}

.card-title {
  font-size: 19px;
  font-weight: 700;
  margin-bottom: 20px;
  color: var(--text-primary);
}

.basic-row {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-bottom: 22px;
}

.avatar-circle {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 26px;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, var(--green-primary), var(--teal));
  flex-shrink: 0;
}

.meta-label {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.meta-value {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.form-row {
  display: flex;
  align-items: center;
  gap: 16px;
}

.form-label {
  font-size: 15px;
  color: var(--text-primary);
  font-weight: 500;
}

.setting-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 18px 0;
  border-top: 1px solid var(--border-soft);
}

.setting-item.column {
  flex-direction: column;
  align-items: flex-start;
  gap: 14px;
}

.setting-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.setting-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.mode-group {
  flex-wrap: wrap;
}

.save-btn {
  margin-top: 24px;
  min-width: 160px;
}

.wizard-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px;
}

.wizard-entry {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 20px;
  border: 1px solid var(--border-card);
  border-radius: var(--r-md);
  background: var(--green-softer);
  transition: transform 0.25s ease, border-color 0.25s ease;
}

.wizard-entry:hover {
  transform: translateY(-3px);
  border-color: rgba(47, 133, 90, 0.4);
}

.wizard-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--green-active);
}

.wizard-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}

@media (max-width: 600px) {
  .profile-card {
    padding: 22px 18px;
  }

  .setting-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
}
</style>
