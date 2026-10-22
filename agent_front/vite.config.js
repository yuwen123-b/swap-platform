import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  // base 改为环境变量驱动：
  //   部署在站点根（现状）→ 不设，默认 '/'
  //   部署在子目录（如 https://x.com/h5/）→ 构建时 VITE_BASE=/h5/ npm run build
  // 默认值与改造前完全一致，不影响现有部署方式。
  // 注意：走子目录时还需路由配合，已改为 createWebHistory(import.meta.env.BASE_URL)。
  const env = loadEnv(mode, process.cwd(), '')
  const base = env.VITE_BASE || '/'

  return {
    base,
    plugins: [vue()],
    build: {
      // 移动端基线：iOS 14 / Safari 14 / Chrome 87 起完整支持本项目用到的
      // ES2020 语法与 CSS 特性。显式声明（而非依赖默认 'modules'）是为了
      // 未来升级 Vite 时行为不漂移。
      target: ['chrome87', 'safari14', 'ios14'],
      cssTarget: ['chrome87', 'safari14', 'ios14'],
    },
    server: {
      // 0.0.0.0 = 允许同一局域网内的手机直接访问，真机自测必备
      host: '0.0.0.0',
      port: 5173,
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
  }
})
