<template>
  <el-dialog
    v-model="visible"
    title="确认兑换"
    width="min(440px, 92vw)"
    append-to-body
    align-center
    destroy-on-close
    class="redeem-confirm-dialog"
    @closed="onClosed"
  >
    <!-- 商品概要 -->
    <div class="confirm-product">
      <span class="confirm-thumb">
        <ProductCover
          :src="product?.image_url || ''"
          :title="product?.title"
          :category="category"
          variant="mini"
        />
      </span>
      <span class="confirm-info">
        <span class="confirm-title">{{ product?.title || '未命名商品' }}</span>
        <span v-if="merchantName" class="confirm-merchant">{{ merchantName }}</span>
      </span>
    </div>

    <!-- 积分结算：免费券与付费券文案分叉 -->
    <div class="confirm-points" :class="{ free: isFree }">
      <template v-if="isFree">
        <p class="points-free">此商品免费兑换，无需消耗积分</p>
      </template>
      <template v-else>
        <div class="points-row">
          <span class="points-label">消耗积分</span>
          <span class="points-value minus">- {{ cost }} 分</span>
        </div>
        <div class="points-row">
          <span class="points-label">当前积分</span>
          <span class="points-value">{{ balance }} 分</span>
        </div>
        <div class="points-divider" aria-hidden="true"></div>
        <div class="points-row">
          <span class="points-label">兑换后剩余</span>
          <span class="points-value strong" :class="{ danger: !enough }">{{ Math.max(remaining, 0) }} 分</span>
        </div>
      </template>
    </div>

    <p class="confirm-expire">核销码有效期 {{ expireDays }} 天，过期未核销将自动退还积分</p>
    <p v-if="stockWarning" class="confirm-warn">{{ stockWarning }}</p>
    <p v-else-if="!enough && !isFree" class="confirm-warn">
      积分不足，还差 {{ cost - balance }} 分
    </p>

    <!-- 兑换失败提示：请求已带 skipErrorToast，错误只在这里出现（不弹两次） -->
    <el-alert
      v-if="errorMessage"
      class="confirm-error"
      type="error"
      :title="errorMessage"
      :closable="false"
      show-icon
    />

    <template #footer>
      <div class="confirm-actions">
        <el-button :disabled="submitting" @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" :disabled="blocked" @click="submit">
          确认兑换
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref } from 'vue'
import ProductCover from './ProductCover.vue'
import { redeemProduct } from '../api/merchant'

/**
 * 兑换确认弹窗（只负责「确认」这一步，不含核销码展示）。
 *
 * 为什么不做成「确认 → 成功 → 核销码」的双态弹窗：
 * 核销码展示要独立出现在「我的兑换」页（那里没有确认这一步），
 * 合并后那一页就得传个假 product 进来。故本组件只负责确认，
 * 成功后 emit success，由父页面拉起 RedeemCodeDialog。
 *
 * 拦截器双弹规避：redeemProduct 内部已带 skipErrorToast，
 * 错误文案在本弹窗内以 el-alert 呈现，不弹全局 toast。
 */
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  product: { type: Object, default: null },
  merchantName: { type: String, default: '' },
  // 当前积分余额（父页面从 profileStore.points 传入）
  balance: { type: Number, default: 0 },
  // 商品所属分类（父页面从 merchant.category 传入）：决定封面渐变与图标，
  // 与「新」Tab / 店铺详情页同口径；不传则回落中性灰渐变
  category: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue', 'success'])

// 与 .env 的 REDEMPTION_CODE_EXPIRE_DAYS 对应；
// 兑换成功后核销码弹窗会用后端返回的 expires_at 显示真实日期，这里只作事前告知。
const expireDays = 30

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const submitting = ref(false)
const errorMessage = ref('')

const cost = computed(() => Math.max(0, Number(props.product?.points_cost) || 0))
// 免费券：0 积分，后端会跳过扣分与流水
const isFree = computed(() => cost.value === 0)
const enough = computed(() => isFree.value || props.balance >= cost.value)
const remaining = computed(() => props.balance - cost.value)

const stockWarning = computed(() => {
  const stock = props.product?.stock
  if (stock === undefined || stock === null) return ''
  return Number(stock) <= 0 ? '该商品已兑完' : ''
})

const blocked = computed(() => !enough.value || Boolean(stockWarning.value))

async function submit() {
  if (blocked.value || submitting.value) return
  errorMessage.value = ''
  submitting.value = true
  try {
    const result = await redeemProduct(props.product.id)
    // 先通知父页面（刷新余额/库存、拉起核销码弹窗），再关自己
    emit('success', result)
    visible.value = false
  } catch (err) {
    // 后端把业务错误放在响应体的 message（HTTP 状态码 = code）
    errorMessage.value =
      err?.response?.data?.message || err?.message || '兑换失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}

function onClosed() {
  // 关闭即清错，避免下次打开还挂着上一次的失败提示
  errorMessage.value = ''
  submitting.value = false
}
</script>

<style scoped>
.confirm-product {
  display: flex;
  align-items: center;
  gap: 14px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--pc-border, #e5e7eb);
}

/* 封面容器：只负责尺寸与裁切，画面交给 ProductCover（真图优先，否则分类渐变 + 图标） */
.confirm-thumb {
  display: block;
  flex-shrink: 0;
  width: 64px;
  height: 64px;
  overflow: hidden;
  border: 1px solid var(--pc-border, #e5e7eb);
  border-radius: 12px;
}

.confirm-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.confirm-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--pc-text, var(--text-primary));
  word-break: break-all;
}

.confirm-merchant {
  margin-top: 4px;
  font-size: 13px;
  color: var(--pc-text-sub, var(--text-secondary));
}

/* ---------- 积分结算 ---------- */
.confirm-points {
  padding: 14px 0 4px;
}

/* 免费券：整块变浅绿提示条，不再出现 0 分/剩余 X 分的算式 */
.confirm-points.free {
  padding: 12px 14px;
  margin: 14px 0 4px;
  background: var(--green-softer, #f1f8f3);
  border: 1px solid var(--green-soft, #e6f4ec);
  border-radius: 12px;
}

.points-free {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--green-active, #22543d);
}

.points-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  min-height: 28px;
  font-size: 14px;
}

.points-label {
  color: var(--pc-text-sub, var(--text-secondary));
}

.points-value {
  font-weight: 600;
  color: var(--pc-text, var(--text-primary));
  font-variant-numeric: tabular-nums;
}

.points-value.minus {
  color: #dc2626;
}

.points-value.strong {
  font-size: 18px;
  font-weight: 800;
  color: var(--green-primary);
}

.points-value.danger {
  color: #dc2626;
}

.points-divider {
  height: 1px;
  margin: 8px 0;
  background: var(--pc-border, #e5e7eb);
}

.confirm-expire {
  margin: 10px 0 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--pc-text-sub, var(--text-secondary));
}

.confirm-warn {
  margin: 8px 0 0;
  font-size: 14px;
  font-weight: 600;
  color: #dc2626;
}

.confirm-error {
  margin-top: 12px;
}

.confirm-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
}
</style>

<style>
/* 高对比度：黑底白字 */
html.theme-high-contrast .redeem-confirm-dialog.el-dialog {
  background: #000000 !important;
  border: 1px solid #ffffff !important;
}

html.theme-high-contrast .redeem-confirm-dialog .el-dialog__title,
html.theme-high-contrast .redeem-confirm-dialog .confirm-title,
html.theme-high-contrast .redeem-confirm-dialog .points-value {
  color: #ffffff !important;
}

html.theme-high-contrast .redeem-confirm-dialog .confirm-merchant,
html.theme-high-contrast .redeem-confirm-dialog .points-label,
html.theme-high-contrast .redeem-confirm-dialog .confirm-expire {
  color: #f2f2f2 !important;
}

html.theme-high-contrast .redeem-confirm-dialog .confirm-thumb {
  border-color: #ffffff;
}

html.theme-high-contrast .redeem-confirm-dialog .confirm-points.free {
  background: #000000;
  border-color: #4ade80;
}

html.theme-high-contrast .redeem-confirm-dialog .points-free {
  color: #4ade80;
}

html.theme-high-contrast .redeem-confirm-dialog .points-value.minus,
html.theme-high-contrast .redeem-confirm-dialog .points-value.danger,
html.theme-high-contrast .redeem-confirm-dialog .confirm-warn {
  color: #fca5a5 !important;
}

html.theme-high-contrast .redeem-confirm-dialog .points-divider {
  background: #ffffff;
}

/* 助老模式：字号与点击目标整体放大 */
html.mode-elderly .redeem-confirm-dialog .confirm-title {
  font-size: 22px;
}

html.mode-elderly .redeem-confirm-dialog .confirm-merchant,
html.mode-elderly .redeem-confirm-dialog .points-row,
html.mode-elderly .redeem-confirm-dialog .confirm-expire,
html.mode-elderly .redeem-confirm-dialog .confirm-warn {
  font-size: 18px;
}

html.mode-elderly .redeem-confirm-dialog .points-free {
  font-size: 20px;
}

html.mode-elderly .redeem-confirm-dialog .points-value.strong {
  font-size: 24px;
}

html.mode-elderly .redeem-confirm-dialog .el-button {
  min-height: 60px;
  padding: 12px 26px;
  font-size: 18px;
}
</style>
