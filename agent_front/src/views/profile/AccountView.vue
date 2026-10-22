<template>
  <ProfileSubLayout title="账户安全" desc="管理登录密码与手机号、邮箱等账号绑定信息">
    <!-- 修改密码 -->
    <section class="profile-card">
      <h2 class="card-title">修改密码</h2>
      <div class="setting-item">
        <div class="setting-text">
          <div class="setting-name">登录密码</div>
          <div class="setting-desc">建议使用 8-32 位、同时包含字母和数字的组合</div>
        </div>
        <el-button type="primary" @click="showPassword = true">修改密码</el-button>
      </div>
    </section>

    <!-- 换绑手机 -->
    <section class="profile-card">
      <h2 class="card-title">换绑手机</h2>
      <div class="setting-item">
        <div class="setting-text">
          <div class="setting-name">当前手机号</div>
          <div class="setting-desc">{{ phoneDisplay }}</div>
        </div>
        <el-button @click="showPhone = true">换绑手机</el-button>
      </div>
    </section>

    <!-- 换绑邮箱 -->
    <section class="profile-card">
      <h2 class="card-title">换绑邮箱</h2>
      <div class="setting-item">
        <div class="setting-text">
          <div class="setting-name">当前邮箱</div>
          <div class="setting-desc">{{ emailDisplay }}</div>
        </div>
        <el-button @click="showEmail = true">换绑邮箱</el-button>
      </div>
    </section>

    <ChangePasswordDialog v-model="showPassword" />
    <RebindPhoneDialog v-model="showPhone" @success="refreshContact" />
    <RebindEmailDialog v-model="showEmail" @success="refreshContact" />
  </ProfileSubLayout>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import ProfileSubLayout from '../../layouts/ProfileSubLayout.vue'
import ChangePasswordDialog from '../../components/account/ChangePasswordDialog.vue'
import RebindPhoneDialog from '../../components/account/RebindPhoneDialog.vue'
import RebindEmailDialog from '../../components/account/RebindEmailDialog.vue'
import { getMe } from '../../api/auth'
import { useUserStore } from '../../store/user'

const userStore = useUserStore()

const showPassword = ref(false)
const showPhone = ref(false)
const showEmail = ref(false)

const phoneDisplay = computed(() => maskPhone(userStore.user?.phone))
const emailDisplay = computed(() => maskEmail(userStore.user?.email))

// 脱敏展示：与后端 _mask_phone / _mask_email 保持同一规则
function maskPhone(phone) {
  if (!phone) return '未绑定'
  return phone.length >= 7 ? `${phone.slice(0, 3)}****${phone.slice(-4)}` : phone
}

function maskEmail(email) {
  if (!email) return '未绑定'
  const [name, domain] = email.split('@')
  if (!domain) return email
  return name.length <= 2 ? `${name.charAt(0)}***@${domain}` : `${name.slice(0, 2)}***@${domain}`
}

// 换绑成功后刷新本地会话（phone/email 来自登录态 user 对象）
async function refreshContact() {
  try {
    const me = await getMe()
    userStore.user = me
    localStorage.setItem('user', JSON.stringify(me))
  } catch {
    // 刷新失败不影响主流程，下次登录会重新拉取
  }
}

onMounted(refreshContact)
</script>
