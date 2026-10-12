<template>
  <section class="page about-page">
    <div class="page-head">
      <div class="eyebrow">平台介绍</div>
      <h1 class="page-title">关于<span class="gradient-text">我们</span></h1>
      <p class="page-sub muted">让闲置流动起来，打造低碳有温度的社区</p>
    </div>

    <!-- 平台介绍 -->
    <div class="panel intro-panel">
      <p class="intro-text">「闲物焕新」是一个由社区居民共同参与的旧物互换智能体平台。我们相信，每一件被遗忘在角落的物品，都可能成为另一户人家的惊喜。借助 AI 物品识别与智能定价，我们让闲置物品在邻里之间重新流动——少一件丢弃，多一次相遇，让低碳生活成为一种日常的温暖。</p>
      <div class="intro-stats">
        <div class="stat">
          <span class="stat-num">12</span>
          <span class="stat-label">覆盖社区</span>
        </div>
        <div class="stat">
          <span class="stat-num">320</span>
          <span class="stat-label">注册居民</span>
        </div>
        <div class="stat">
          <span class="stat-num">486</span>
          <span class="stat-label">成功互换</span>
        </div>
        <div class="stat">
          <span class="stat-num">1250<span class="unit">kg</span></span>
          <span class="stat-label">累计减碳</span>
        </div>
      </div>
    </div>

    <!-- 使命与愿景 -->
    <div class="two-col">
      <div class="panel">
        <div class="panel-icon">🌱</div>
        <h2 class="panel-title">我们的使命</h2>
        <p class="panel-text">让闲置物品流动起来。我们希望通过便捷的互换体验与可信的社区机制，减少资源浪费与碳排放，让每个家庭都能以更轻盈的方式获得所需，用一份信任连接彼此。</p>
      </div>
      <div class="panel">
        <div class="panel-icon">🏡</div>
        <h2 class="panel-title">平台愿景</h2>
        <p class="panel-text">成为中国最值得信赖的社区低碳生活平台。我们期待在每一个社区里，交换旧物像串门一样自然；邻里之间不只是物品的流转，更有温情、故事与可持续的生活方式在流淌。</p>
      </div>
    </div>

    <!-- 团队介绍 -->
    <div class="section-gap">
      <h2 class="section-title">团队介绍</h2>
      <p class="muted section-desc">一支热爱生活、深耕社区的技术小团队</p>
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
const team = [
  { name: '林晓', role: '产品发起人', bio: '在社区一线做了八年公益，相信好的产品能让邻里更亲近。发起「闲物焕新」，想让每一件旧物都被温柔以待。' },
  { name: '陈默', role: '技术负责人', bio: '全栈工程师，主导 AI 物品识别与智能定价能力的搭建。热衷旧物改造，家里书架上一半的书都是换来的。' },
  { name: '苏晴', role: '社区运营', bio: '熟悉社区里的每一位热心居民，策划一场场线下交换市集，把线上的约定变成广场上的笑脸相迎。' },
]
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
