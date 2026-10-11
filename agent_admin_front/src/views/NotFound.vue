<template>
  <div class="error-page">
    <div class="code">404</div>
    <p>页面不存在</p>
    <el-button type="primary" round @click="$router.push('/dashboard')">返回看板</el-button>
  </div>
</template>

<style scoped>
.error-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
}

.code {
  font-size: 72px;
  font-weight: 700;
  color: #2f855a;
}

p {
  color: #6b7280;
}
</style>
