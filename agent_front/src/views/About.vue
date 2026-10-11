<template>
  <section class="page about-page">
    <div class="page-head">
      <div class="eyebrow">{{ t('about.eyebrow') }}</div>
      <h1 class="page-title">{{ t('about.titleLead') }}<span class="gradient-text">{{ t('about.titleHighlight') }}</span></h1>
      <p class="page-sub muted">{{ t('about.pageSub') }}</p>
    </div>

    <!-- 平台介绍 -->
    <div class="panel intro-panel">
      <p class="intro-text">{{ t('about.intro') }}</p>
      <div class="intro-stats">
        <div class="stat">
          <span class="stat-num">12</span>
          <span class="stat-label">{{ t('about.stats.communities') }}</span>
        </div>
        <div class="stat">
          <span class="stat-num">320</span>
          <span class="stat-label">{{ t('about.stats.residents') }}</span>
        </div>
        <div class="stat">
          <span class="stat-num">486</span>
          <span class="stat-label">{{ t('about.stats.swaps') }}</span>
        </div>
        <div class="stat">
          <span class="stat-num">1250<span class="unit">kg</span></span>
          <span class="stat-label">{{ t('about.stats.carbon') }}</span>
        </div>
      </div>
    </div>

    <!-- 使命与愿景 -->
    <div class="two-col">
      <div class="panel">
        <div class="panel-icon">🌱</div>
        <h2 class="panel-title">{{ t('about.missionTitle') }}</h2>
        <p class="panel-text">{{ t('about.missionText') }}</p>
      </div>
      <div class="panel">
        <div class="panel-icon">🏡</div>
        <h2 class="panel-title">{{ t('about.visionTitle') }}</h2>
        <p class="panel-text">{{ t('about.visionText') }}</p>
      </div>
    </div>

    <!-- 团队介绍 -->
    <div class="section-gap">
      <h2 class="section-title">{{ t('about.teamTitle') }}</h2>
      <p class="muted section-desc">{{ t('about.teamDesc') }}</p>
      <div class="team-grid">
        <div v-for="member in team" :key="member.name" class="panel team-card">
          <span class="team-avatar">{{ member.name.charAt(0) }}</span>
          <h3 class="team-name">{{ member.name }}</h3>
          <span class="team-role">{{ member.role }}</span>
          <p class="team-bio">{{ member.bio }}</p>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from '../i18n'

const { t } = useI18n()

// 团队成员：文案来自 i18n 分片，切换语言时自动更新
const team = computed(() =>
  ['member1', 'member2', 'member3'].map((id) => ({
    name: t(`about.team.${id}.name`),
    role: t(`about.team.${id}.role`),
    bio: t(`about.team.${id}.bio`),
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

/* ---------- 通用绿色卡片：白底 / 16px 圆角 / 浅绿边框 ---------- */
.panel {
  padding: 30px 28px;
  background: #fff;
  border: 1px solid rgba(76, 175, 80, 0.22);
  border-radius: 16px;
  transition: transform 0.25s ease, box-shadow 0.25s ease;
}

.panel:hover {
  transform: translateY(-3px);
  box-shadow: 0 14px 30px rgba(46, 125, 50, 0.12);
}

.intro-panel {
  margin-top: 34px;
}

.intro-text {
  margin: 0;
  font-size: 15.5px;
  line-height: 2;
  color: #3c5a48;
}

.intro-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-top: 26px;
  padding-top: 24px;
  border-top: 1px dashed rgba(76, 175, 80, 0.35);
}

.stat {
  text-align: center;
}

.stat-num {
  display: block;
  font-size: 30px;
  font-weight: 800;
  color: #4caf50;
}

.stat-num .unit {
  margin-left: 2px;
  font-size: 14px;
}

.stat-label {
  margin-top: 6px;
  font-size: 13px;
  color: #63786d;
}

.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
  margin-top: 18px;
}

.panel-icon {
  font-size: 34px;
}

.panel-title {
  margin: 12px 0 10px;
  font-size: 19px;
  color: #2e7d32;
}

.panel-text {
  margin: 0;
  font-size: 14.5px;
  line-height: 1.9;
  color: #55705f;
}

/* ---------- 团队 ---------- */
.section-gap {
  margin-top: 46px;
}

.section-title {
  margin: 0;
  font-size: 22px;
  color: #2e7d32;
}

.section-desc {
  margin: 8px 0 0;
  font-size: 14px;
}

.team-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 18px;
  margin-top: 20px;
}

.team-card {
  text-align: center;
}

.team-avatar {
  display: grid;
  place-items: center;
  width: 64px;
  height: 64px;
  margin: 0 auto;
  border-radius: 50%;
  background: linear-gradient(135deg, #4caf50, #2e7d32);
  color: #fff;
  font-size: 24px;
  font-weight: 700;
}

.team-name {
  margin: 14px 0 4px;
  font-size: 16px;
  color: #1b3a26;
}

.team-role {
  display: inline-block;
  padding: 3px 12px;
  border-radius: 999px;
  background: #e8f5e9;
  color: #2e7d32;
  font-size: 12.5px;
}

.team-bio {
  margin: 12px 0 0;
  font-size: 13.5px;
  line-height: 1.8;
  color: #63786d;
}

@media (max-width: 800px) {
  .intro-stats,
  .team-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .two-col {
    grid-template-columns: 1fr;
  }
}
</style>
