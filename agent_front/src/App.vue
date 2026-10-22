<template>
  <el-config-provider :locale="zhCn">
    <!-- 商家工作台是独立布局（自带顶栏 + 侧边栏），不能再套 AppNav / footer /
         悬浮按钮；其余所有路由（含 /merchant 积分商城、/merchant/apply）继续用 MainLayout。 -->
    <MerchantLayout v-if="isMerchantLayout">
      <RouterView />
    </MerchantLayout>
    <MainLayout v-else />
  </el-config-provider>
</template>
<script setup>
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import MainLayout from './layouts/MainLayout.vue'
import MerchantLayout from './layouts/MerchantLayout.vue'

const route = useRoute()
const isMerchantLayout = computed(() => route.meta.layout === 'merchant')
</script>
