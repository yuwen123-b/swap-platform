<template>
  <section class="page help-page">
    <div class="page-head">
      <div class="eyebrow">Help Center</div>
      <h1 class="page-title">帮助<span class="gradient-text">中心</span></h1>
      <p class="page-sub muted">常见问题都在这里，点击展开查看答案</p>
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
        <h2 class="more-title">没有找到想要的答案？</h2>
        <p class="more-text">
          欢迎前往
          <router-link to="/contact" class="text-link">联系客服</router-link>
          页面留言，或加入社区微信群与邻居们交流，我们会尽快为你解答。
        </p>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue'

const faqs = [
  { name: 'publish', q: '如何发布物品？', a: '登录后进入「探索物品」页面，点击右上角「上传物品」按钮，填写物品名称、描述、分类并上传实物照片，提交后等待审核通过即可展示。发布时请真实描述物品成色与瑕疵，方便邻居快速了解。' },
  { name: 'points', q: '如何获取积分？', a: '发布物品、成功完成一次交换、收到邻居好评都可以获得积分。此外，选择「免费送出」的物品会获得双倍积分奖励。积分可用于兑换社区好物，或在智能定价中作为议价参考。' },
  { name: 'recognition', q: '物品识别怎么用？', a: '进入「物品识别」页面，用手机拍摄或上传物品照片，AI 会自动识别物品类别、品牌与成色，并生成参考定价与推荐分类，几秒钟即可完成发布前的准备，再也不用纠结怎么描述啦。' },
  { name: 'contact', q: '如何联系发布者？', a: '在物品详情页点击「联系发布者」按钮：若发布者公开了联系方式，可直接查看并复制；若未公开，可通过智能体助手给对方留言，约好在社区广场当面交换。' },
  { name: 'afterSwap', q: '交换完成后需要做什么？', a: '请及时在「社区评价」页面完成互评，分享本次交换的体验。真实评价不仅能提升社区信用分，也会帮助后续的邻居更好地了解物品与交换对象。' },
  { name: 'dispute', q: '遇到纠纷怎么办？', a: '请在物品详情页或评价页面提交举报，说明情况并附上聊天截图。社区管理员会在 24 小时内介入核实，视情节给予提醒、扣分或封禁处理，保障大家的交换体验。' },
]

const activeNames = ref(['publish'])
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
