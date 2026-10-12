<template>
  <section class="page convention-page">
    <div class="page-head">
      <div class="eyebrow">社区规范</div>
      <h1 class="page-title">社区<span class="gradient-text">公约</span></h1>
      <p class="page-sub muted">简单几条约定，让每一次交换都安心、温暖</p>
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
      <p class="promise-text">遵守公约的居民将获得更高的社区信用分与更多曝光机会。如遇违反公约的行为，可在物品详情页举报，社区管理员将在 24 小时内处理。</p>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const RULE_ICONS = ['📋', '💬', '⚖️', '🌿', '🔒', '♻️']

const RULE_DATA = [
  { title: '真实描述物品', text: '如实填写物品的成色、瑕疵与使用年限，不夸大、不隐瞒，附上实物照片，让邻居看得明白、换得放心。' },
  { title: '友善沟通', text: '以礼相待、耐心回应。无论交换是否达成，都请保持友善——邻里之间的温度，比物品本身更珍贵。' },
  { title: '诚信交换', text: '承诺与描述一致的物品进行交换，不临时加价、不中途反悔；约定好的时间请准时赴约。' },
  { title: '爱护环境', text: '优先选择面交或拼车配送，减少包装浪费；无法交换的物品请做好分类回收，共同守护社区环境。' },
  { title: '尊重隐私', text: '面交请选择社区广场、物业大厅等公共场所；不泄露、不打探他人隐私信息，谨慎保护个人联系方式。' },
  { title: '及时交接', text: '物品交换完成后请及时确认并完成评价；长期未响应的物品将被平台自动下架，把机会留给需要的邻居。' },
]

const rules = computed(() =>
  RULE_ICONS.map((icon, index) => ({
    no: index + 1,
    icon,
    title: RULE_DATA[index].title,
    text: RULE_DATA[index].text,
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
