<template>
  <div class="login-page">
    <el-card class="login-card">
      <div class="brand">
        <span class="brand-icon">♻</span>
        <h1>社区旧物互换管理后台</h1>
        <p>温暖 · 环保 · 邻里互助</p>
      </div>
      <el-form ref="formRef" :model="form" :rules="rules" size="large" @keyup.enter="onSubmit">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="管理员账号" prefix-icon="User" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码" prefix-icon="Lock" show-password />
        </el-form-item>
        <el-button type="primary" class="submit" :loading="loading" round @click="onSubmit">登 录</el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { login } from '@/api/auth'
import { useAdminStore } from '@/store/admin'

const route = useRoute()
const router = useRouter()
const store = useAdminStore()

const formRef = ref()
const loading = ref(false)
const form = reactive({ username: '', password: '' })
const rules = {
  username: [{ required: true, message: '请输入管理员账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function onSubmit() {
  await formRef.value.validate()
  loading.value = true
  try {
    const res = await login(form)
    store.setLogin(res.data)
    ElMessage.success('登录成功')
    router.push(route.query.redirect || '/dashboard')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #faf9f6 0%, #e5f2eb 100%);
}

.login-card {
  width: 400px;
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(47, 133, 90, 0.12);
}

.brand {
  text-align: center;
  margin-bottom: 28px;
}

.brand-icon {
  font-size: 40px;
  color: #2f855a;
}

.brand h1 {
  font-size: 20px;
  color: #2f855a;
  margin: 8px 0 4px;
}

.brand p {
  font-size: 12px;
  color: #9ca3af;
}

.submit {
  width: 100%;
  background: linear-gradient(90deg, #2f855a, #38a169);
  border: none;
}
</style>
