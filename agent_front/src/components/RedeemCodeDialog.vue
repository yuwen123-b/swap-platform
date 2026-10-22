<template>
  <el-dialog
    v-model="visible"
    width="min(420px, 92vw)"
    append-to-body
    align-center
    :show-close="true"
    class="redeem-code-dialog"
    :class="{ 'is-redeemed': isRedeemed, 'is-expired': isExpired }"
  >
    <!-- 标题区：状态图标 + 一句话结论 -->
    <div class="code-head">
      <span class="code-badge" :class="{ done: isRedeemed, expired: isExpired }" aria-hidden="true">
        <svg v-if="isRedeemed" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4 12.5 9.5 18 20 6.5" />
        </svg>
        <svg v-else-if="isExpired" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7.5v5.5l3.5 2" />
        </svg>
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4 12.5 9.5 18 20 6.5" />
        </svg>
      </span>
      <h3 class="code-title">{{ title }}</h3>
      <p v-if="productTitle" class="code-product">{{ productTitle }}</p>
      <p v-if="merchantName" class="code-merchant">{{ merchantName }}</p>
    </div>

    <!-- 核销码：3+3 空格分组，大字展示 -->
    <div class="code-box" role="group" :aria-label="`核销码 ${spokenCode}`">
      <span class="code-value" aria-hidden="true">{{ prettyCode }}</span>
    </div>

    <p class="code-hint">{{ hint }}</p>
    <p v-if="expiryText" class="code-expiry">{{ expiryText }}</p>

    <template #footer>
      <div class="code-actions">
        <el-button v-if="showListButton" @click="goList">查看我的兑换</el-button>
        <el-button type="primary" @click="visible = false">完成</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed } from 'vue'

/**
 * 核销码放大展示弹窗（纯展示，无请求）。
 *
 * 被两处复用：
 *  1) RedeemConfirmDialog —— 兑换成功后紧接着展示（stay-open，不关窗）
 *  2) RedemptionsView     —— 点某条兑换记录后放大展示
 *
 * 状态文案按 status 分叉：1 待核销 / 2 已核销 / 3 已过期。
 * ⚠ 不在这里做「过期判定」——过期由后端每小时定时任务刷状态，
 *   前端只展示后端给的 status，避免同一单两处判断不一致。
 */
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  code: { type: [String, Number], default: '' },
  productTitle: { type: String, default: '' },
  merchantName: { type: String, default: '' },
  expiresAt: { type: String, default: '' },
  redeemedAt: { type: String, default: '' },
  status: { type: [Number, String], default: 1 },
  // 兑换成功时展示「查看我的兑换」；从我的兑换页点进来时不需要（已在那一页）
  showListButton: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'view-list'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const statusNum = computed(() => Number(props.status) || 1)
const isRedeemed = computed(() => statusNum.value === 2)
const isExpired = computed(() => statusNum.value === 3)

/* 核销码是 6 位字符串，可能以 0 开头（如 "012345"）——
   这里全程按字符串处理，绝不 Number() 转换，否则前导 0 会丢。 */
const rawCode = computed(() => String(props.code ?? '').replace(/\s+/g, ''))

// 展示成 "123 456"（3 + 3）；位数不是 6 位时按实际长度折半分组，绝不截断
const prettyCode = computed(() => {
  const s = rawCode.value
  if (!s) return '—— ——'
  if (s.length === 6) return `${s.slice(0, 3)} ${s.slice(3)}`
  const mid = Math.ceil(s.length / 2)
  return `${s.slice(0, mid)} ${s.slice(mid)}`
})

// 视障模式逐位朗读，避免屏幕阅读器把 "482913" 念成一个数字
const spokenCode = computed(() => rawCode.value.split('').join(' ') || '暂无')

const title = computed(() => {
  if (isRedeemed.value) return '已核销'
  if (isExpired.value) return '已过期'
  return '兑换成功'
})

const hint = computed(() => {
  if (isRedeemed.value) return '该核销码已使用，不能重复核销'
  if (isExpired.value) return '该核销码已过期，兑换积分已原额退还'
  return '向商家出示此码完成核销'
})

const expiryText = computed(() => {
  if (isRedeemed.value) return props.redeemedAt ? `核销时间 ${formatDateTime(props.redeemedAt)}` : ''
  if (isExpired.value) return props.expiresAt ? `已于 ${formatDate(props.expiresAt)} 过期` : ''
  return props.expiresAt ? `有效期至 ${formatDate(props.expiresAt)}` : ''
})

function toDate(value) {
  if (!value) return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d
}

function formatDate(value) {
  const d = toDate(value)
  return d ? d.toLocaleDateString('zh-CN') : ''
}

function formatDateTime(value) {
  const d = toDate(value)
  if (!d) return ''
  return `${d.toLocaleDateString('zh-CN')} ${d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
}

function goList() {
  emit('view-list')
  visible.value = false
}
</script>

<style scoped>
.code-head {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  text-align: center;
}

/* 状态徽标：绿底白勾 / 灰底（已核销）/ 橙底（已过期） */
.code-badge {
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  margin-bottom: 4px;
  border-radius: 50%;
  background: #16a34a;
  color: #fff;
}

.code-badge.done {
  background: #8a8a8a;
}

.code-badge.expired {
  background: #f59e0b;
}

.code-badge svg {
  width: 26px;
  height: 26px;
}

.code-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--pc-text, var(--text-primary));
}

.code-product {
  margin: 2px 0 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--pc-text, var(--text-primary));
  word-break: break-all;
}

.code-merchant {
  margin: 0;
  font-size: 13px;
  color: var(--pc-text-sub, var(--text-secondary));
}

/* 核销码容器：虚线描边 + 浅底，像一张票券 */
.code-box {
  display: grid;
  place-items: center;
  margin: 18px 0 12px;
  padding: 16px 12px;
  background: var(--pc-bg, #f7f8f7);
  border: 2px dashed var(--pc-border, #e5e7eb);
  border-radius: 14px;
}

.code-value {
  font-family: var(--font-sans);
  font-size: clamp(34px, 9vw, 52px);
  font-weight: 800;
  line-height: 1.15;
  letter-spacing: 0.08em;
  color: var(--pc-green, var(--green-primary));
  /* 等宽数字：两位数字宽度一致，3+3 分组不会左右晃 */
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.code-hint {
  margin: 0;
  font-size: 14px;
  line-height: 1.7;
  text-align: center;
  color: var(--pc-text, var(--text-primary));
}

.code-expiry {
  margin: 6px 0 0;
  font-size: 13px;
  text-align: center;
  color: var(--pc-text-sub, var(--text-secondary));
}

.code-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
}
</style>

<!-- ============================================================
     非 scoped：弹窗挂在 body 下（append-to-body），
     根级主题选择器必须非 scoped 才能命中。
     ============================================================ -->
<style>
/* 高对比度：黑底白字 + 浅色核销码，虚线框改白色 */
html.theme-high-contrast .redeem-code-dialog.el-dialog {
  background: #000000 !important;
  border: 1px solid #ffffff !important;
}

html.theme-high-contrast .redeem-code-dialog .code-title,
html.theme-high-contrast .redeem-code-dialog .code-product,
html.theme-high-contrast .redeem-code-dialog .code-hint {
  color: #ffffff !important;
}

html.theme-high-contrast .redeem-code-dialog .code-merchant,
html.theme-high-contrast .redeem-code-dialog .code-expiry {
  color: #f2f2f2 !important;
}

html.theme-high-contrast .redeem-code-dialog .code-box {
  background: #000000;
  border-color: #ffffff;
}

html.theme-high-contrast .redeem-code-dialog .code-value {
  color: #4ade80;
}

html.theme-high-contrast .redeem-code-dialog .code-badge {
  color: #000000;
}

html.theme-high-contrast .redeem-code-dialog .code-badge.done {
  background: #e5e5e5;
}

/* 助老模式：核销码与按钮整体放大，点击目标 ≥60px */
html.mode-elderly .redeem-code-dialog .code-value {
  font-size: clamp(44px, 11vw, 64px);
}

html.mode-elderly .redeem-code-dialog .code-title {
  font-size: 26px;
}

html.mode-elderly .redeem-code-dialog .code-product {
  font-size: 20px;
}

html.mode-elderly .redeem-code-dialog .code-hint,
html.mode-elderly .redeem-code-dialog .code-expiry {
  font-size: 18px;
}

html.mode-elderly .redeem-code-dialog .el-button {
  min-height: 60px;
  padding: 12px 26px;
  font-size: 18px;
}
</style>
