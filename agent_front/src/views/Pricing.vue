<template>
  <section class="page">
    <div class="eyebrow">AI 智能定价</div>
    <h1 class="page-title">
      给物品一个<br />
      <span class="gradient-text">有依据的价格。</span>
    </h1>

    <div class="pricing-layout">
      <!-- 表单 -->
      <el-card class="form-card" shadow="never">
        <h2 class="panel-title">输入物品信息</h2>
        <el-form label-position="top" @submit.prevent="estimate">
          <el-form-item label="物品名称">
            <el-input v-model="form.item_name" placeholder="例如：九成新儿童自行车" />
          </el-form-item>

          <el-form-item label="物品分类">
            <el-input v-model="form.item_category" placeholder="例如：母婴玩具" />
          </el-form-item>

          <el-form-item label="成色等级">
            <el-rate
              v-model="form.condition_level"
              :texts="conditionTexts"
              show-text
            />
          </el-form-item>

          <el-form-item label="原价（元）">
            <el-input-number
              v-model="form.original_price"
              :min="1"
              :precision="2"
              controls-position="right"
            />
          </el-form-item>

          <el-button
            type="primary"
            native-type="submit"
            :loading="loading"
            class="full"
          >
            开始 AI 估价
          </el-button>
        </el-form>
      </el-card>

      <!-- 结果与历史 -->
      <div class="result-area">
        <div v-if="result" class="result glass-card">
          <div class="result-banner">
            <div class="eyebrow">建议售价</div>
            <div class="price">¥ {{ result.suggested_price }}</div>
            <span class="rate-chip chip">折旧率 {{ (Number(result.depreciation_rate) * 100).toFixed(1) }}%</span>
          </div>
          <p class="reason muted">{{ result.pricing_reason }}</p>
        </div>

        <div v-else class="empty-result glass-card">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 2v4M12 18v4M2 12h4M18 12h4"/>
            <circle cx="12" cy="12" r="4"/>
          </svg>
          <p>填写信息，获取一份透明的定价建议</p>
        </div>

        <div class="history" v-if="history.length">
          <h2 class="panel-title">最近定价记录</h2>
          <div v-for="record in history" :key="record.id" class="history-row">
            <span class="history-name">{{ record.item_name }}</span>
            <strong>¥ {{ record.suggested_price }}</strong>
            <small class="muted">{{ formatTime(record.created_at) }}</small>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { pricing, pricingHistory } from '../api/ai'

const form = reactive({
  item_name: '',
  item_category: '',
  condition_level: 4,
  original_price: 500,
})

const conditionTexts = computed(() => [
  '较差',
  '一般',
  '良好',
  '很新',
  '全新',
])

const result = ref(null)
const history = ref([])
const loading = ref(false)

function formatTime(value) {
  if (!value) return ''
  return String(value).replace('T', ' ').slice(0, 16)
}

async function loadHistory() {
  try {
    const data = await pricingHistory({ page: 1, size: 5 })
    history.value = data.items || []
  } catch {
    history.value = []
  }
}

async function estimate() {
  if (!form.item_name || !form.item_category || !form.original_price) {
    return
  }
  loading.value = true
  try {
    result.value = await pricing(form)
    loadHistory()
  } finally {
    loading.value = false
  }
}

onMounted(loadHistory)
</script>

<style scoped>
.pricing-layout {
  display: grid;
  grid-template-columns: 390px 1fr;
  gap: 24px;
  margin-top: 36px;
}

.panel-title {
  font-size: 19px;
  margin-bottom: 24px;
}

.full {
  width: 100%;
}

.result-area {
  min-height: 400px;
}

.result {
  overflow: hidden;
}

.result-banner {
  padding: 32px 34px 26px;
  background: linear-gradient(120deg, var(--teal-soft), var(--green-softer));
}

.price {
  font-size: 56px;
  font-weight: 700;
  color: var(--teal-deep);
  margin: 12px 0 14px;
}

.rate-chip {
  background: #fff;
}

.reason {
  padding: 24px 34px 30px;
  margin: 0;
  line-height: 1.8;
  font-size: 14.5px;
}

.empty-result {
  min-height: 260px;
  display: grid;
  place-items: center;
  text-align: center;
  padding: 30px;
}

.empty-result svg {
  width: 54px;
  height: 54px;
  color: var(--teal);
  opacity: 0.6;
  margin-bottom: 14px;
}

.empty-result p {
  color: var(--text-secondary);
  font-size: 14px;
}

.history {
  margin-top: 30px;
}

.history-row {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 18px;
  align-items: center;
  padding: 13px 2px;
  border-bottom: 1px solid var(--border-soft);
  font-size: 13.5px;
}

.history-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-row strong {
  color: var(--teal-deep);
}

.history-row small {
  font-size: 12px;
}

@media (max-width: 750px) {
  .pricing-layout {
    grid-template-columns: 1fr;
  }

  .price {
    font-size: 44px;
  }
}
</style>
