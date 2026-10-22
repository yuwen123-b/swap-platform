<template>
  <ProfileSubLayout title="无障碍设置" desc="选择适合你的交互方式，配置会保存到账号并全局生效">
    <section class="profile-card">
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

    <!-- 交互向导入口（原个人中心主页的向导移入此处） -->
    <section class="profile-card">
      <h2 class="card-title">交互向导</h2>
      <p class="card-hint">打开对应的独立交互页面，获得完整的语音与无障碍体验。</p>
      <div class="wizard-row">
        <RouterLink to="/elderly" class="wizard-entry">
          <span class="wizard-name">进入助老模式</span>
          <span class="wizard-desc">打开大字语音交互页面</span>
        </RouterLink>
        <RouterLink to="/accessible" class="wizard-entry">
          <span class="wizard-name">进入无障碍模式</span>
          <span class="wizard-desc">打开语音标签与交接方式演示页</span>
        </RouterLink>
      </div>
    </section>
  </ProfileSubLayout>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { ElMessage } from 'element-plus'
import ProfileSubLayout from '../../layouts/ProfileSubLayout.vue'
import { useProfileStore } from '../../store/profile'

const profileStore = useProfileStore()

const saving = ref(false)
const form = reactive({
  elderlyMode: false,
  accessibilityMode: 'normal',
  mobilityLevel: 'free',
  highContrast: false,
})

// 全局档案 -> 本地表单（登录后档案异步就绪时也会同步）
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

async function onSave() {
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
/* 交互向导：两列自适应卡片 */
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
  border: 1px solid var(--pc-border, #e5e7eb);
  border-radius: 12px;
  background: var(--pc-bg, #f7f8f7);
  transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
}

.wizard-entry:hover {
  transform: translateY(-2px);
  border-color: var(--pc-green, var(--green-primary));
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
}

.wizard-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--pc-green, var(--green-primary));
}

.wizard-desc {
  font-size: 13px;
  line-height: 1.6;
  color: var(--pc-text-sub, var(--text-secondary));
}
</style>
