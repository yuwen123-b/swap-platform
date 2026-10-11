<template>
  <section class="page help-page">
    <div class="page-head">
      <div class="eyebrow">Help Center</div>
      <h1 class="page-title">{{ t('help.titleLead') }}<span class="gradient-text">{{ t('help.titleHighlight') }}</span></h1>
      <p class="page-sub muted">{{ t('help.subtitle') }}</p>
    </div>

    <el-collapse v-model="activeNames" class="faq-panel">
      <el-collapse-item
        v-for="faq in faqs"
        :key="faq.name"
        :title="faq.q"
        :name="faq.name"
      >
        <p class="faq-answer">{{ faq.a }}</p>
      </el-collapse-item>
    </el-collapse>

    <div class="panel more-help">
      <span class="more-icon">📮</span>
      <div>
        <h2 class="more-title">{{ t('help.moreTitle') }}</h2>
        <p class="more-text">
          {{ t('help.moreTextLead') }}
          <router-link to="/contact" class="text-link">{{ t('help.contactLink') }}</router-link>
          {{ t('help.moreTextTail') }}
        </p>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useI18n } from '../i18n'

const { t } = useI18n()

// 折叠面板使用稳定 id 作为 name，保证切换语言时展开状态不受影响
const faqKeys = ['publish', 'points', 'recognition', 'contact', 'afterSwap', 'dispute']

const activeNames = ref(['publish'])

const faqs = computed(() =>
  faqKeys.map((name) => ({
    name,
    q: t(`help.faqs.${name}.q`),
    a: t(`help.faqs.${name}.a`),
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

/* ---------- FAQ 折叠面板：白底 / 16px 圆角 / 浅绿边框 ---------- */
.faq-panel {
  margin-top: 34px;
  padding: 8px 22px;
  background: #fff;
  border: 1px solid rgba(76, 175, 80, 0.22);
  border-radius: 16px;
}

.faq-panel :deep(.el-collapse-item__header) {
  height: 58px;
  font-size: 15.5px;
  font-weight: 600;
  color: #1b3a26;
  border-bottom-color: rgba(76, 175, 80, 0.16);
}

.faq-panel :deep(.el-collapse-item__header:hover) {
  color: #4caf50;
}

.faq-panel :deep(.el-collapse-item__header.is-active) {
  color: #2e7d32;
}

.faq-panel :deep(.el-collapse-item__wrap) {
  border-bottom-color: rgba(76, 175, 80, 0.16);
}

.faq-panel :deep(.el-collapse-item__content) {
  padding-bottom: 20px;
}

.faq-answer {
  margin: 0;
  font-size: 14px;
  line-height: 1.95;
  color: #55705f;
}

/* ---------- 更多帮助 ---------- */
.panel {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 22px;
  padding: 26px 28px;
  background: #f4fbf6;
  border: 1px solid rgba(76, 175, 80, 0.22);
  border-radius: 16px;
}

.more-icon {
  font-size: 32px;
}

.more-title {
  margin: 0 0 6px;
  font-size: 16px;
  color: #2e7d32;
}

.more-text {
  margin: 0;
  font-size: 14px;
  line-height: 1.85;
  color: #55705f;
}
</style>
