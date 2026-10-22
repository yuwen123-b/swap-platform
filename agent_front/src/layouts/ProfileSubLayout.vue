<template>
  <div class="page sub-page">
    <!-- 顶部返回栏 -->
    <button type="button" class="back-bar" @click="goBack">
      <span class="back-arrow" aria-hidden="true">←</span>
      <span>返回个人中心</span>
    </button>

    <h1 class="sub-title">{{ title }}</h1>
    <p v-if="desc" class="sub-desc">{{ desc }}</p>

    <!-- 卡片式内容区 -->
    <div class="sub-body">
      <slot />
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

defineProps({
  title: { type: String, required: true },
  desc: { type: String, default: '' },
})

const router = useRouter()
// 子页面恒在个人中心体系内，返回按钮直接回 /profile，行为可预期
const goBack = () => router.push('/profile')
</script>

<style scoped>
.sub-page {
  max-width: 820px;
}

/* 返回栏：灰色文字按钮，hover 变主色 */
.back-bar {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  margin: 0 0 12px -12px;
  font: inherit;
  font-size: 14px;
  color: var(--text-secondary);
  background: transparent;
  border: none;
  border-radius: 10px;
  cursor: pointer;
  transition: color 0.2s ease, background 0.2s ease;
}

.back-bar:hover {
  color: var(--green-primary);
  background: var(--green-softer);
}

.back-bar:focus-visible {
  outline: 3px solid var(--green-primary);
  outline-offset: 2px;
}

.back-arrow {
  font-size: 16px;
  line-height: 1;
}

.sub-title {
  margin: 4px 0 8px;
  font-size: clamp(24px, 3.4vw, 32px);
  font-weight: 700;
  letter-spacing: -0.4px;
  color: var(--text-primary);
}

.sub-desc {
  margin: 0 0 4px;
  font-size: 15px;
  line-height: 1.8;
  color: var(--text-secondary);
}
</style>

<!-- ============================================================
     非 scoped：子页面共享的「卡片 / 设置项」样式
     以 .sub-page 前缀命名空间隔离，不与 Profile.vue 的 scoped 规则冲突。
     必须非 scoped 才能命中 html 根级选择器（html:has / mode-elderly / theme-high-contrast）。
     ============================================================ -->
<style>
/* ---------- 局部色板（与 Profile.vue 同构，值复用全局令牌） ---------- */
.sub-page {
  --pc-green: var(--green-primary);
  --pc-green-alt: color-mix(in srgb, var(--green-primary) 80%, #ffffff);
  --pc-text: var(--text-primary);
  --pc-text-sub: var(--text-secondary);
  --pc-bg: #f7f8f7;
  --pc-card: #ffffff;
  --pc-border: #e5e7eb;
  --pc-track: #e5e7eb;
  --pc-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  --pc-shadow-hover: 0 4px 16px rgba(0, 0, 0, 0.08);
}

/* ---------- 页面底色：仅子页面生效 ---------- */
html:has(.sub-page):not(.theme-high-contrast) body {
  background: #f7f8f7;
}

/* ---------- 卡片基础 ---------- */
.sub-page .profile-card {
  margin-top: 20px;
  padding: 20px;
  background: var(--pc-card);
  border: 1px solid var(--pc-border);
  border-radius: 16px;
  box-shadow: var(--pc-shadow);
  transition: box-shadow 0.2s ease;
}

.sub-page .profile-card:hover {
  box-shadow: var(--pc-shadow-hover);
}

/* 卡片标题：16px 粗体 + 左侧 4px 绿色竖线 */
.sub-page .card-title {
  position: relative;
  margin-bottom: 20px;
  padding-left: 12px;
  font-size: 16px;
  font-weight: 700;
  color: var(--pc-text);
}

.sub-page .card-title::before {
  content: "";
  position: absolute;
  left: 0;
  top: 50%;
  width: 4px;
  height: 16px;
  border-radius: 2px;
  background: var(--pc-green);
  transform: translateY(-50%);
}

/* 卡片标题右侧的补充说明 */
.sub-page .card-hint {
  margin: -12px 0 16px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--pc-text-sub);
}

/* ---------- 设置项 ---------- */
.sub-page .setting-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  min-height: 48px;
  padding: 12px;
  margin: 0 -12px;
  border-top: 1px solid var(--pc-border);
  border-radius: 8px;
  transition: background 0.2s ease;
}

.sub-page .setting-item:hover {
  background: var(--pc-bg);
}

.sub-page .card-title + .setting-item,
.sub-page .card-hint + .setting-item {
  border-top: none;
}

.sub-page .setting-item.column {
  flex-direction: column;
  align-items: flex-start;
  gap: 14px;
}

.sub-page .setting-name {
  margin-bottom: 4px;
  font-size: 15px;
  font-weight: 600;
  color: var(--pc-text);
}

.sub-page .setting-desc {
  font-size: 13px;
  line-height: 1.6;
  color: var(--pc-text-sub);
}

.sub-page .mode-group {
  flex-wrap: wrap;
}

/* ---------- 表单 ---------- */
.sub-page .form-item {
  margin-bottom: 18px;
}

.sub-page .form-label {
  display: block;
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--pc-text);
}

.sub-page .form-tip {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--pc-text-sub);
}

/* ---------- 操作区 ---------- */
.sub-page .form-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 8px;
}

.sub-page .save-btn {
  min-width: 160px;
}

/* ---------- 空态 ---------- */
.sub-page .empty-text {
  padding: 12px 0;
  font-size: 14px;
  color: var(--pc-text-sub);
}

/* ============================================================
   高对比度主题：重定义局部色板，保证子页面仍可读
   --pc-green / --pc-text 引用全局令牌，已随主题自动改写
   ============================================================ */
html.theme-high-contrast .sub-page {
  --pc-card: #000000;
  --pc-bg: #000000;
  --pc-border: #ffffff;
  --pc-track: rgba(255, 255, 255, 0.35);
  --pc-shadow: none;
  --pc-shadow-hover: none;
}

/* ============================================================
   助老模式：字号 / 间距 / 点击目标整体放大
   ============================================================ */
html.mode-elderly .sub-page .profile-card {
  margin-top: 24px;
  border-radius: 20px;
}

html.mode-elderly .sub-page .card-title {
  font-size: 22px;
}

html.mode-elderly .sub-page .card-hint,
html.mode-elderly .sub-page .setting-desc,
html.mode-elderly .sub-page .form-tip {
  font-size: 18px;
}

html.mode-elderly .sub-page .setting-name,
html.mode-elderly .sub-page .form-label {
  font-size: 20px;
}

html.mode-elderly .sub-page .back-bar,
html.mode-elderly .sub-page .sub-desc {
  font-size: 18px;
}

/* 所有可点击元素最小高度 60px */
html.mode-elderly .sub-page .el-button,
html.mode-elderly .sub-page .back-bar,
html.mode-elderly .sub-page .setting-item {
  min-height: 60px;
}
</style>
