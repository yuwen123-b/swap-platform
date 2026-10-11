<template>
  <section class="page">
    <div class="eyebrow">{{ t('review.eyebrow') }}</div>
    <h1 class="page-title">
      {{ t('review.titleLead') }}<br />
      <span class="gradient-text">{{ t('review.titleAccent') }}</span>
    </h1>

    <el-tabs v-model="activeTab" class="review-tabs">
      <!-- Tab1：交换评价 -->
      <el-tab-pane :label="t('review.tabExchange')" name="exchange">
        <div class="review-layout">
          <!-- 提交评价 -->
          <el-card class="panel form-card" shadow="never">
            <h2 class="panel-title">{{ t('review.exchange.formTitle') }}</h2>
            <el-form label-position="top" @submit.prevent="submit">
              <el-form-item :label="t('review.exchange.orderIdLabel')">
                <el-input-number v-model="form.order_id" :min="1" controls-position="right" />
              </el-form-item>
              <el-form-item :label="t('review.exchange.revieweeIdLabel')">
                <el-input-number v-model="form.to_user_id" :min="1" controls-position="right" />
              </el-form-item>
              <el-form-item :label="t('review.exchange.ratingLabel')">
                <el-rate v-model="form.rating" />
              </el-form-item>
              <el-form-item :label="t('review.exchange.contentLabel')">
                <el-input
                  v-model="form.content"
                  type="textarea"
                  :rows="4"
                  :placeholder="t('review.exchange.contentPlaceholder')"
                />
              </el-form-item>
              <el-button type="primary" native-type="submit" class="full">
                {{ t('review.exchange.submit') }}
              </el-button>
            </el-form>
          </el-card>

          <!-- 统计与列表 -->
          <div>
            <div class="summary glass-card">
              <div class="summary-left">
                <strong>{{ Number(summary.average_rating).toFixed(1) }}</strong>
                <el-rate :model-value="Number(summary.average_rating)" disabled />
              </div>
              <span class="muted">{{ t('review.exchange.summaryCount', { count: summary.total }) }}</span>
            </div>

            <div class="review-list glass-card">
              <div v-for="review in reviews" :key="review.id" class="review-row">
                <span class="review-avatar">{{ review.from_user_id || t('review.avatarFallback') }}</span>
                <div class="review-body">
                  <el-rate :model-value="review.rating" disabled />
                  <p>{{ review.content }}</p>
                  <small class="muted">{{ t('review.exchange.orderLabel', { id: review.order_id }) }}</small>
                </div>
              </div>
              <el-empty v-if="!reviews.length" :description="t('review.exchange.empty')" />
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab2：评价程序 -->
      <el-tab-pane :label="t('review.tabPlatform')" name="platform">
        <div class="review-layout">
          <!-- 提交程序评价 -->
          <el-card class="panel form-card" shadow="never">
            <h2 class="panel-title">{{ t('review.feedback.formTitle') }}</h2>
            <p class="panel-desc muted">
              {{ t('review.feedback.formDesc') }}
            </p>
            <el-form label-position="top" @submit.prevent="submitFeedback">
              <el-form-item :label="t('review.feedback.ratingLabel')">
                <el-rate v-model="fbForm.rating" />
              </el-form-item>
              <el-form-item :label="t('review.feedback.contentLabel')">
                <el-input
                  v-model="fbForm.content"
                  type="textarea"
                  :rows="4"
                  maxlength="500"
                  show-word-limit
                  :placeholder="t('review.feedback.contentPlaceholder')"
                />
              </el-form-item>
              <el-button type="primary" native-type="submit" class="full" :loading="fbLoading">
                {{ t('review.feedback.submit') }}
              </el-button>
            </el-form>
          </el-card>

          <!-- 情感统计与列表 -->
          <div>
            <div class="summary glass-card">
              <div class="fb-stats">
                <div class="fb-stat">
                  <strong>{{ fbStats.total }}</strong>
                  <span class="muted">{{ t('review.feedback.statTotal') }}</span>
                </div>
                <div class="fb-stat">
                  <strong class="tone-pos">{{ fbStats.positive }}</strong>
                  <span class="muted">{{ t('review.feedback.statPositive') }}</span>
                </div>
                <div class="fb-stat">
                  <strong class="tone-neu">{{ fbStats.neutral }}</strong>
                  <span class="muted">{{ t('review.feedback.statNeutral') }}</span>
                </div>
                <div class="fb-stat">
                  <strong class="tone-neg">{{ fbStats.negative }}</strong>
                  <span class="muted">{{ t('review.feedback.statNegative') }}</span>
                </div>
              </div>
              <span class="muted">{{ t('review.feedback.avgRating', { value: Number(fbStats.avg_rating).toFixed(1) }) }}</span>
            </div>

            <div class="review-list glass-card">
              <div v-for="fb in feedbacks" :key="fb.id" class="review-row">
                <span class="review-avatar">{{ fb.user_id || t('review.avatarFallback') }}</span>
                <div class="review-body">
                  <div class="fb-meta">
                    <el-rate :model-value="fb.rating" disabled />
                    <el-tag size="small" :type="sentimentType(fb.sentiment)" effect="light">
                      {{ sentimentText(fb.sentiment) }}
                    </el-tag>
                  </div>
                  <p>{{ fb.content }}</p>
                  <small class="muted">{{ formatTime(fb.created_at) }}</small>
                </div>
              </div>
              <el-empty v-if="!feedbacks.length" :description="t('review.feedback.empty')" />
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from '../i18n'
import { createReview, getReviews, getReviewSummary } from '../api/review'
import { createFeedback, getFeedbackList } from '../api/feedback'

const { t } = useI18n()

const activeTab = ref('exchange')

// ---------- 交换评价（原有逻辑） ----------
const form = reactive({
  order_id: 1,
  to_user_id: 1,
  rating: 5,
  content: '',
})

const summary = ref({ average_rating: 0, total: 0 })
const reviews = ref([])

async function load() {
  try {
    const [s, r] = await Promise.all([
      getReviewSummary(),
      getReviews({ page: 1, size: 10 }),
    ])
    summary.value = s
    reviews.value = r.items || []
  } catch {
    // 未登录或接口异常时保持空态
  }
}

async function submit() {
  if (!form.content) {
    return ElMessage.warning(t('review.exchange.contentRequired'))
  }
  try {
    await createReview(form)
    ElMessage.success(t('review.exchange.submitSuccess'))
    form.content = ''
    load()
  } catch {
    // 错误提示已由请求拦截器处理
  }
}

// ---------- 评价程序（情感分析） ----------
const fbForm = reactive({ rating: 5, content: '' })
const fbLoading = ref(false)
const feedbacks = ref([])
const fbStats = ref({ total: 0, positive: 0, neutral: 0, negative: 0, avg_rating: 0 })

const SENTIMENT_TYPE = { positive: 'success', neutral: 'info', negative: 'danger' }

// 情感文案在渲染时经 t() 取值，切换语言可响应式更新
function sentimentText(s) {
  if (s === 'positive') return t('review.feedback.statPositive')
  if (s === 'negative') return t('review.feedback.statNegative')
  return t('review.feedback.statNeutral')
}

function sentimentType(s) {
  return SENTIMENT_TYPE[s] || 'info'
}

function formatTime(t) {
  return t ? String(t).replace('T', ' ').slice(0, 16) : ''
}

async function loadFeedback() {
  try {
    const data = await getFeedbackList()
    feedbacks.value = data.items || []
    fbStats.value = data.stats || fbStats.value
  } catch {
    // 保持空态
  }
}

async function submitFeedback() {
  if (!fbForm.content.trim()) {
    return ElMessage.warning(t('review.feedback.contentRequired'))
  }
  fbLoading.value = true
  try {
    const result = await createFeedback({ rating: fbForm.rating, content: fbForm.content.trim() })
    ElMessage.success(t('review.feedback.submitSuccess', { sentiment: result.sentiment_cn }))
    fbForm.content = ''
    loadFeedback()
  } catch {
    // 错误提示已由请求拦截器处理
  } finally {
    fbLoading.value = false
  }
}

onMounted(() => {
  load()
  loadFeedback()
})
</script>

<style scoped>
.review-tabs {
  margin-top: 20px;
}

.review-layout {
  display: grid;
  grid-template-columns: 360px 1fr;
  gap: 24px;
  margin-top: 16px;
}

.panel-title {
  font-size: 19px;
  margin-bottom: 16px;
}

.panel-desc {
  font-size: 13px;
  line-height: 1.7;
  margin: 0 0 18px;
}

.full {
  width: 100%;
}

.summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px 26px;
  margin-bottom: 18px;
  background: linear-gradient(120deg, #fff, var(--peach-soft));
}

.summary-left strong {
  display: block;
  font-size: 42px;
  font-weight: 700;
  color: var(--peach-deep);
  margin-bottom: 6px;
}

/* 程序反馈统计 */
.fb-stats {
  display: flex;
  gap: 26px;
}

.fb-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.fb-stat strong {
  font-size: 24px;
  font-weight: 700;
}

.tone-pos { color: var(--green-primary, #2f855a); }
.tone-neu { color: #6b7280; }
.tone-neg { color: #dc2626; }

.review-list {
  padding: 8px 26px;
}

.review-row {
  display: flex;
  gap: 14px;
  padding: 20px 0;
  border-bottom: 1px solid var(--border-soft);
}

.review-row:last-child {
  border-bottom: none;
}

.review-avatar {
  flex: none;
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--green-primary), var(--teal));
  color: #fff;
  font-weight: 600;
  font-size: 14px;
}

.fb-meta {
  display: flex;
  align-items: center;
  gap: 10px;
}

.review-body p {
  margin: 9px 0 5px;
  font-size: 14px;
  line-height: 1.7;
}

.review-body small {
  font-size: 11px;
}

@media (max-width: 750px) {
  .review-layout {
    grid-template-columns: 1fr;
  }
}
</style>
