<template>
  <el-dialog
    v-model="visible"
    title="修改密码"
    width="440px"
    :close-on-click-modal="false"
    @closed="resetForm"
  >
    <el-form label-position="top" @submit.prevent>
      <el-form-item label="原密码">
        <el-input
          v-model="form.oldPassword"
          type="password"
          show-password
          maxlength="64"
          placeholder="请输入当前密码"
        />
      </el-form-item>
      <el-form-item label="新密码">
        <el-input
          v-model="form.newPassword"
          type="password"
          show-password
          maxlength="32"
          placeholder="8-32 位，需同时包含字母和数字"
        />
      </el-form-item>
      <el-form-item label="确认新密码">
        <el-input
          v-model="form.confirmPassword"
          type="password"
          show-password
          maxlength="32"
          placeholder="请再次输入新密码"
          @keyup.enter="onSubmit"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="loading" @click="onSubmit">确认修改</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { changePassword } from '../../api/user'
import { useUserStore } from '../../store/user'

const visible = defineModel({ type: Boolean, default: false })

const router = useRouter()
const userStore = useUserStore()

const loading = ref(false)
const form = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: '',
})

function resetForm() {
  form.oldPassword = ''
  form.newPassword = ''
  form.confirmPassword = ''
}

// 前端先做一轮校验，后端会再校验一次（双保险）
function validate() {
  if (!form.oldPassword) return '请输入原密码'
  if (!form.newPassword) return '请输入新密码'
  if (!form.confirmPassword) return '请再次输入新密码'
  if (form.newPassword.length < 8 || form.newPassword.length > 32) return '新密码长度需为 8-32 位'
  if (!/[A-Za-z]/.test(form.newPassword) || !/\d/.test(form.newPassword)) return '新密码需同时包含字母和数字'
  if (form.newPassword === form.oldPassword) return '新密码不能与原密码相同'
  if (form.newPassword !== form.confirmPassword) return '两次输入不一致'
  return ''
}

async function onSubmit() {
  const message = validate()
  if (message) {
    ElMessage.warning(message)
    return
  }
  loading.value = true
  try {
    await changePassword({
      old_password: form.oldPassword,
      new_password: form.newPassword,
    })
    visible.value = false
    ElMessage.success('密码修改成功，请重新登录')
    // 本项目 JWT 无版本号/黑名单，服务端无法立即吊销旧 token；
    // 这里强制本地登出，确保用户用新密码重新获取 token。
    userStore.logout()
    router.push({ path: '/login', query: { redirect: '/profile' } })
  } catch {
    // 错误提示由请求拦截器统一处理（如「原密码错误」）
  } finally {
    loading.value = false
  }
}
</script>
