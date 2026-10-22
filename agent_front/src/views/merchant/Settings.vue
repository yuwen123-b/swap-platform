<template>
  <section class="mw-page mw-settings">
    <div class="mw-page-head">
      <div>
        <h1 class="mw-page-title">店铺设置</h1>
        <p class="mw-page-desc">维护店铺资料，查看佣金与结算自查</p>
      </div>
      <div class="head-actions">
        <span class="status-tag" :class="shopStatusClass">{{ shopStatusLabel }}</span>
        <button type="button" class="mw-btn" :disabled="loading" @click="load">
          {{ loading ? '刷新中…' : '刷新' }}
        </button>
      </div>
    </div>

    <!-- 被拒：把原因放在最上面，商家一眼就知道要改什么 -->
    <p v-if="shopStatus === 2" class="mw-error" role="alert">
      入驻申请未通过：{{ info?.audit_reason || '平台未填写具体原因，请联系客服了解详情' }}
      <br />
      请到入驻页重新提交申请。
    </p>

    <!-- ===== 店铺资料（可编辑，依赖 PUT /merchant/info） ===== -->
    <div class="mw-card">
      <div class="mw-card-head">
        <h2 class="mw-card-title">店铺资料</h2>
        <span class="card-sub">只保存改动的项，留空即清空该项</span>
      </div>

      <div class="shop-head">
        <span class="shop-logo" aria-hidden="true">{{ categoryIcon }}</span>
        <span class="shop-head-main">
          <span class="shop-head-name">{{ info?.name || '未命名店铺' }}</span>
          <span class="shop-head-sub">{{ info?.category || '未设置类型' }}</span>
        </span>
      </div>

      <div class="form-item">
        <label class="form-label" for="set-name">店铺名<span class="req" aria-hidden="true">*</span></label>
        <el-input id="set-name" v-model="form.name" maxlength="100" show-word-limit />
      </div>

      <div class="form-item">
        <label class="form-label" for="set-category">店铺类型</label>
        <el-select
          id="set-category"
          v-model="form.category"
          class="full"
          clearable
          placeholder="请选择（可留空）"
          aria-label="店铺类型"
        >
          <el-option v-for="name in CATEGORIES" :key="name" :label="name" :value="name" />
        </el-select>
      </div>

      <div class="form-item">
        <label class="form-label" for="set-contact">联系方式</label>
        <el-input id="set-contact" v-model="form.contact" maxlength="100" placeholder="手机号 / 微信" />
      </div>

      <div class="form-item">
        <label class="form-label" for="set-address">地址</label>
        <el-input id="set-address" v-model="form.address" maxlength="200" placeholder="如：小区北门 1 号商铺" />
      </div>

      <div class="form-item">
        <label class="form-label" for="set-desc">店铺简介</label>
        <el-input
          id="set-desc"
          v-model="form.description"
          type="textarea"
          :rows="4"
          maxlength="2000"
          show-word-limit
        />
      </div>

      <p v-if="saveError" class="form-error" role="alert">{{ saveError }}</p>
      <p v-if="saveTip" class="save-tip" role="status">{{ saveTip }}</p>

      <div class="form-actions">
        <el-button type="primary" size="large" :loading="saving" @click="save">保存修改</el-button>
        <button type="button" class="mw-btn" :disabled="saving" @click="prefill">还原</button>
      </div>
    </div>

    <!-- ===== 佣金与结算（只读） ===== -->
    <div class="mw-card">
      <div class="mw-card-head">
        <h2 class="mw-card-title">佣金与结算</h2>
        <span class="card-sub">数据只读，出账由平台按月执行</span>
      </div>

      <p v-if="summaryError" class="mw-error" role="alert">
        结算数据加载失败，请点击右上角「刷新」重试。
      </p>

      <div class="settle-grid">
        <div class="settle-cell">
          <span class="settle-value">{{ summary?.redemption_count ?? '—' }}</span>
          <span class="settle-label">累计核销单数</span>
        </div>
        <div class="settle-cell">
          <span class="settle-value">{{ summary?.points_total ?? '—' }}</span>
          <span class="settle-label">累计消耗积分</span>
        </div>
        <div class="settle-cell">
          <span class="settle-value strong">{{ money(summary?.gross_amount) }}</span>
          <span class="settle-label">应得金额</span>
        </div>
        <div class="settle-cell">
          <span class="settle-value">{{ money(summary?.settled_amount) }}</span>
          <span class="settle-label">已结算金额</span>
        </div>
        <div class="settle-cell">
          <span class="settle-value accent">{{ money(summary?.pending_amount) }}</span>
          <span class="settle-label">待结算金额</span>
        </div>
        <div class="settle-cell">
          <span class="settle-value">{{ money(summary?.commission_amount) }}</span>
          <span class="settle-label">平台佣金（累计）</span>
        </div>
      </div>

      <dl class="readonly-list">
        <div class="readonly-row">
          <dt>佣金比例</dt>
          <dd>{{ rateText }}</dd>
        </div>
        <div class="readonly-row">
          <dt>积分汇率</dt>
          <dd>
            {{ summary?.points_to_yuan != null ? `${summary.points_to_yuan} 元 / 积分` : '—' }}
          </dd>
        </div>
        <div class="readonly-row">
          <dt>商家实得</dt>
          <dd>{{ money(summary?.net_amount) }}</dd>
        </div>
        <div class="readonly-row">
          <dt>已结算批次</dt>
          <dd>
            {{ summary?.settled_count ?? '—' }} 批
            <template v-if="summary?.last_settled_at">
              · 最近 {{ formatDate(summary.last_settled_at) }}
            </template>
          </dd>
        </div>
      </dl>

      <p class="settle-hint">
        佣金比例以店铺实际配置为准（当前 {{ rateText }}），平台可对单店单独调整；
        「应得金额」= 累计核销积分 × 积分汇率，「待结算」= 应得 − 已结算。
      </p>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getSettlementSummary, updateMerchantInfo } from '../../api/merchant'
import { useMerchantStore } from '../../store/merchant'

/**
 * 店铺设置。
 *
 * 【可编辑靠本阶段新增的 PUT /merchant/info】
 * 后端只覆盖**显式传入**的字段（exclude_unset），所以这里把 5 个可编辑字段全部显式传出：
 * 表单是从服务端回填的，把原值原样传回不会改变任何东西，
 * 而用户清空的字段会以空串送出 → 后端落 NULL（真的被清掉）。
 *
 * ⚠ 刻意**不传 logo_url**：读回来的值可能是带 HMAC 签名的本地图片地址，
 * 回写会污染相对路径。本阶段也不做上传，因此这一项只展示不编辑。
 *
 * 【只读区】
 * 佣金比例来自 `merchant.commission_rate`（以表行为准），
 * 结算数字来自本阶段新增的 `GET /merchant/settlement/summary`（只读，不改状态）。
 */
const merchantStore = useMerchantStore()

const CATEGORIES = ['打印', '便利店', '理发', '回收', '家政']

const CATEGORY_ICONS = {
  打印: '🖨️',
  便利店: '🏪',
  理发: '💇',
  回收: '♻️',
  家政: '🧹',
}

const form = reactive({ name: '', category: '', contact: '', address: '', description: '' })
const saving = ref(false)
const loading = ref(false)
const saveError = ref('')
const saveTip = ref('')

const summary = ref(null)
const summaryError = ref(false)

const info = computed(() => merchantStore.info)
const shopStatus = computed(() => merchantStore.status)

const SHOP_STATUS = {
  0: { label: '审核中', cls: 'ms-pending' },
  1: { label: '已通过', cls: 'ms-approved' },
  2: { label: '已拒绝', cls: 'ms-rejected' },
  3: { label: '已停业', cls: 'ms-closed' },
}

const shopStatusLabel = computed(() => SHOP_STATUS[shopStatus.value]?.label || '未知')
const shopStatusClass = computed(() => SHOP_STATUS[shopStatus.value]?.cls || 'ms-closed')

const categoryIcon = computed(() => CATEGORY_ICONS[info.value?.category] || '🏬')

const rateText = computed(() => {
  const rate = summary.value?.commission_rate ?? info.value?.commission_rate
  return rate == null ? '—' : `${Number(rate).toFixed(2)}%`
})

function prefill() {
  const m = info.value
  form.name = m?.name || ''
  form.category = m?.category || ''
  form.contact = m?.contact || ''
  form.address = m?.address || ''
  form.description = m?.description || ''
  saveError.value = ''
  saveTip.value = ''
}

async function load() {
  loading.value = true
  summaryError.value = false
  try {
    await merchantStore.fetchInfo(true)
  } catch {
    // 静默：下面 still 尝试拉结算；错误由拦截器/页面提示兜底
  }
  prefill()

  try {
    summary.value = await getSettlementSummary()
  } catch {
    summaryError.value = true
  } finally {
    loading.value = false
  }
}

async function save() {
  saveError.value = ''
  saveTip.value = ''
  const name = form.name.trim()
  if (!name) {
    saveError.value = '店铺名不能为空'
    return
  }

  saving.value = true
  try {
    // 5 个可编辑字段全部显式送出（空串 → 后端落 NULL）；不带 logo_url
    await updateMerchantInfo({
      name,
      category: form.category || '',
      contact: form.contact || '',
      address: form.address || '',
      description: form.description || '',
    })
    saveTip.value = '店铺资料已保存'
    ElMessage.success('店铺资料已保存')
    await merchantStore.fetchInfo(true)
    prefill()
  } catch (error) {
    // updateMerchantInfo 带 skipErrorToast：错误在卡片内展示
    saveError.value = error?.response?.data?.message || error?.message || '保存失败，请稍后重试'
  } finally {
    saving.value = false
  }
}

/* ---------- 展示工具 ---------- */
function money(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return `¥${n.toFixed(2)}`
}

function formatDate(value) {
  if (!value) return ''
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('zh-CN')
}

onMounted(load)
</script>

<style scoped>
.head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.card-sub {
  font-size: 12px;
  color: var(--mw-text-sub);
}

/* ---------- 店招 ---------- */
.shop-head {
  display: flex;
  align-items: center;
  gap: 14px;
  padding-bottom: 16px;
  margin-bottom: 18px;
  border-bottom: 1px solid var(--mw-border);
}

.shop-logo {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 58px;
  height: 58px;
  font-size: 28px;
  background: var(--mw-bg);
  border: 1px solid var(--mw-border);
  border-radius: 14px;
}

.shop-head-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.shop-head-name {
  font-size: 18px;
  font-weight: 800;
  color: var(--mw-text);
}

.shop-head-sub {
  font-size: 13px;
  color: var(--mw-text-sub);
}

/* ---------- 表单 ---------- */
.form-item {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--mw-text);
}

.req {
  margin-left: 2px;
  color: #dc2626;
}

.full {
  width: 100%;
}

.form-error {
  margin: 0 0 12px;
  padding: 10px 12px;
  font-size: 14px;
  font-weight: 600;
  color: #b91c1c;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 10px;
}

.save-tip {
  margin: 0 0 12px;
  font-size: 13px;
  font-weight: 600;
  color: var(--mw-green);
}

.form-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

/* ---------- 结算数字 ---------- */
.settle-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}

.settle-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 14px;
  background: var(--mw-bg);
  border: 1px solid var(--mw-border);
  border-radius: 12px;
}

.settle-value {
  font-size: 22px;
  font-weight: 800;
  line-height: 1.2;
  color: var(--mw-text);
  font-variant-numeric: tabular-nums;
}

.settle-value.strong {
  color: var(--mw-green);
}

.settle-value.accent {
  color: #b45309;
}

.settle-label {
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--mw-text-sub);
}

.readonly-list {
  display: grid;
  gap: 0;
  margin: 0 0 14px;
}

.readonly-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 0;
  border-top: 1px solid var(--mw-border);
}

.readonly-row:first-child {
  border-top: none;
}

.readonly-row dt {
  flex: 0 0 96px;
  font-size: 14px;
  color: var(--mw-text-sub);
}

.readonly-row dd {
  flex: 1 1 auto;
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  text-align: right;
  color: var(--mw-text);
}

.settle-hint {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.8;
  color: var(--mw-text-sub);
}
</style>

<!-- ============================================================
     非 scoped：高对比度 / 助老模式
     ============================================================ -->
<style>
html.theme-high-contrast .mw-shell .shop-logo,
html.theme-high-contrast .mw-shell .settle-cell {
  background: #000000;
  border-color: #ffffff;
}

html.theme-high-contrast .mw-shell .settle-value.strong {
  color: #4ade80;
}

html.theme-high-contrast .mw-shell .settle-value.accent {
  color: #fcd34d;
}

html.theme-high-contrast .mw-shell .save-tip {
  color: #4ade80;
}

html.theme-high-contrast .mw-shell .form-error {
  color: #fca5a5;
  background: #000000;
  border-color: #fca5a5;
}

html.mode-elderly .mw-shell .shop-head-name {
  font-size: 24px;
}

html.mode-elderly .mw-shell .shop-head-sub,
html.mode-elderly .mw-shell .settle-label,
html.mode-elderly .mw-shell .readonly-row dt,
html.mode-elderly .mw-shell .readonly-row dd,
html.mode-elderly .mw-shell .settle-hint,
html.mode-elderly .mw-shell .card-sub {
  font-size: 17px;
}

html.mode-elderly .mw-shell .settle-value {
  font-size: 28px;
}

html.mode-elderly .mw-shell .shop-logo {
  width: 72px;
  height: 72px;
  font-size: 34px;
}
</style>
