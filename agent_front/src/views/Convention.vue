<template>
  <section class="page convention-page">
    <div class="page-head">
      <div class="eyebrow">{{ t('convention.eyebrow') }}</div>
      <h1 class="page-title">{{ t('convention.titleLead') }}<span class="gradient-text">{{ t('convention.titleHighlight') }}</span></h1>
      <p class="page-sub muted">{{ t('convention.pageSub') }}</p>
    </div>

    <div class="rules">
      <article v-for="rule in rules" :key="rule.no" class="rule-card">
        <span class="rule-no">{{ rule.no }}</span>
        <div class="rule-body">
          <h2 class="rule-title">{{ rule.title }}</h2>
          <p class="rule-text">{{ rule.text }}</p>
        </div>
        <span class="rule-icon">{{ rule.icon }}</span>
      </article>
    </div>

    <div class="panel promise">
      <span class="promise-icon">🤝</span>
      <p class="promise-text">{{ t('convention.promise') }}</p>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from '../i18n'

const { t } = useI18n()

// 序号与图标固定，标题与正文走 i18n 分片，切换语言时自动更新
const RULE_ICONS = ['📋', '💬', '⚖️', '🌿', '🔒', '♻️']

const rules = computed(() =>
  RULE_ICONS.map((icon, index) => ({
    no: index + 1,
    icon,
    title: t(`convention.rules.rule${index + 1}.title`),
    text: t(`convention.rules.rule${index + 1}.text`),
  })),
)
</script>

<style scoped>
.page-head {
  text-align: center;
}

.page-sub {
  margin: 6px 0 0;
  font-size: 15px;
}

.rules {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-top: 34px;
}

/* ---------- 规则卡片：白底 / 16px 圆角 / 浅绿边框 ---------- */
.rule-card {
  display: flex;
  align-items: flex-start;
  gap: 18px;
  padding: 24px 26px;
  background: #fff;
  border: 1px solid rgba(76, 175, 80, 0.22);
  border-radius: 16px;
  transition: transform 0.25s ease, box-shadow 0.25s ease;
}

.rule-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 14px 30px rgba(46, 125, 50, 0.12);
}

.rule-no {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: linear-gradient(135deg, #4caf50, #2e7d32);
  color: #fff;
  font-size: 18px;
  font-weight: 800;
}

.rule-body {
  flex: 1;
}

.rule-title {
  margin: 4px 0 8px;
  font-size: 17px;
  color: #2e7d32;
}

.rule-text {
  margin: 0;
  font-size: 14px;
  line-height: 1.9;
  color: #55705f;
}

.rule-icon {
  font-size: 26px;
  opacity: 0.85;
}

/* ---------- 承诺提示 ---------- */
.promise {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 22px;
  background: #f4fbf6;
}

.promise:hover {
  transform: none;
  box-shadow: none;
}

.promise-icon {
  font-size: 30px;
}

.promise-text {
  margin: 0;
  font-size: 14px;
  line-height: 1.9;
  color: #3c5a48;
}

@media (max-width: 600px) {
  .rule-card {
    flex-direction: column;
    gap: 12px;
  }
}
</style>
