<template>
  <section class="mw-page mw-verify">
    <div class="mw-page-head">
      <div>
        <h1 class="mw-page-title">核销订单</h1>
        <p class="mw-page-desc">输入邻居出示的 6 位核销码，满 6 位自动核销</p>
      </div>
      <button type="button" class="mw-btn" :disabled="historyLoading" @click="loadHistory">
        {{ historyLoading ? '刷新中…' : '刷新记录' }}
      </button>
    </div>

    <!-- ===== 输入区 ===== -->
    <div class="mw-card verify-card">
      <label class="verify-label" for="verify-input">核销码</label>
      <input
        id="verify-input"
        ref="inputEl"
        class="verify-input"
        type="text"
        inputmode="numeric"
        autocomplete="off"
        spellcheck="false"
        maxlength="7"
        :value="displayCode"
        :disabled="submitting"
        :aria-label="inputAriaLabel"
        placeholder="000 000"
        @input="onInput"
        @keydown.enter.prevent="submit"
      />
      <p class="verify-tip">
        {{ submitting ? '核销中，请稍候…' : '支持扫码枪扫入或手动输入，输入满 6 位自动提交' }}
      </p>

      <div class="verify-actions">
        <el-button
          type="primary"
          size="large"
          :loading="submitting"
          :disabled="raw.length !== 6"
          @click="submit"
        >
          核销
        </el-button>
        <button type="button" class="mw-btn" :disabled="!raw" @click="clearInput">清空重输</button>
      </div>
    </div>

    <!-- ===== 结果区 ===== -->
    <div v-if="result" class="mw-card result-card" :class="result.ok ? 'is-ok' : 'is-bad'">
      <span class="result-badge" aria-hidden="true">
        <svg v-if="result.ok" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4 12.5 9.5 18 20 6.5" />
        </svg>
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
          <path d="M6 6l12 12M18 6 6 18" />
        </svg>
      </span>

      <h2 class="result-title" role="status">{{ result.ok ? '核销成功' : '核销失败' }}</h2>

      <template v-if="result.ok">
        <dl class="result-list">
          <div class="result-row"><dt>商品</dt><dd>{{ result.product_title || '——' }}</dd></div>
          <div class="result-row"><dt>用户</dt><dd>{{ result.user_nickname || '社区邻居' }}</dd></div>
          <div class="result-row"><dt>核销时间</dt><dd>{{ formatDateTime(result.redeemed_at) || '——' }}</dd></div>
          <div class="result-row"><dt>消耗积分</dt><dd>{{ result.points_cost || 0 }} 积分</dd></div>
        </dl>
        <div class="result-actions">
          <el-button type="primary" size="large" @click="clearInput">继续核销</el-button>
        </div>
      </template>

      <template v-else>
        <!-- 四种失败原因由后端给中文原文，这里原样透出，不自造文案 -->
        <p class="result-message" role="alert">{{ result.message }}</p>
        <ul class="reason-list">
          <li>核销码不存在：请核对邻居出示的 6 位数字</li>
          <li>已核销过：一张码只能用一次</li>
          <li>已过期：超过有效期的码不能再核销</li>
          <li>不属于本店：别家的核销码在本店无法核销</li>
        </ul>
        <div class="result-actions">
          <el-button type="primary" size="large" @click="clearInput">重新输入</el-button>
        </div>
      </template>
    </div>

    <!-- ===== 历史核销记录 ===== -->
    <div class="mw-card">
      <div class="mw-card-head">
        <h2 class="mw-card-title">最近核销记录</h2>
        <span class="card-sub">最新 10 条已核销订单</span>
      </div>

      <p v-if="historyLoading && !history.length" class="mw-empty">加载中…</p>

      <div v-else-if="history.length" class="hist-list">
        <div v-for="item in history" :key="item.id" class="hist-row">
          <span class="hist-thumb" aria-hidden="true">🎟️</span>
          <span class="hist-main">
            <span class="hist-title">{{ item.product_title || '未命名商品' }}</span>
            <span class="hist-sub">
              {{ item.user_nickname || '社区邻居' }} · 核销码 {{ prettyCode(item.code) }}
            </span>
            <span class="hist-time">{{ formatDateTime(item.redeemed_at) || '——' }}</span>
          </span>
          <!-- 商家侧兑换单状态：第四套 ms-* -->
          <span class="status-tag" :class="redemptionStatusClass(item.status)">{{ item.status_label }}</span>
        </div>
      </div>

      <p v-else class="mw-empty">还没有核销记录，核销成功后这里会自动出现</p>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { getMerchantRedemptions, verifyRedemption } from '../../api/merchant'

/**
 * 核销页（商家端最核心的页面）。
 *
 * 【★ 核销码全程按字符串处理，绝不 Number()】
 * 后端生成的是 6 位数字码，可能以 0 开头（如 `012345`）。
 * 任何一次 Number() 转换都会把它变成 `12345`（5 位）→ 核销必失败，
 * 或者显示成 `12 345`（分组错位）。阶段二已在用户侧实测坐实这一点。
 *
 * 【分组显示怎么做】
 * 用原生 `<input>` 而不是 el-input：需要「受控重写 + 光标归位」——
 * 用户每输入 4 个数字就被插入一个空格，若不管光标，第二次输入就会跳到开头。
 * 因此 input 事件里过滤数字 → 写回 state → nextTick 把 DOM 值与光标统统拉到末尾。
 *
 * 【满 6 位自动提交 + 提交期硬锁】
 * 自动提交必须配 `submitting` 锁：否则用户连点时后端虽有条件更新兜底，
 * 前端仍会白发多个重复请求。锁定期间输入框 disabled。
 */
const raw = ref('')
const inputEl = ref(null)
const submitting = ref(false)
const result = ref(null)

const history = ref([])
const historyLoading = ref(false)

/* 3 + 3 分组展示（字符串切片，不做数值运算） */
const displayCode = computed(() => {
  const s = raw.value
  if (s.length <= 3) return s
  return `${s.slice(0, 3)} ${s.slice(3)}`
})

// 视障模式逐位朗读，避免读成一个数字
const inputAriaLabel = computed(() => {
  if (!raw.value) return '核销码，请输入 6 位数字'
  return `已输入 ${raw.value.length} 位：${raw.value.split('').join(' ')}`
})

function onInput(event) {
  const digits = String(event.target.value || '').replace(/\D/g, '').slice(0, 6)
  raw.value = digits
  // 提交/失败态下重输视为「新一轮核销」，先清掉上一次结果
  result.value = null
  // 受控重写：把分组后的文本写回原生 input，并把光标固定到末尾
  nextTick(() => {
    const el = inputEl.value
    if (!el) return
    el.value = displayCode.value
    const end = displayCode.value.length
    if (typeof el.setSelectionRange === 'function') el.setSelectionRange(end, end)
  })
  if (digits.length === 6 && !submitting.value) submit()
}

function clearInput() {
  raw.value = ''
  result.value = null
  nextTick(() => {
    const el = inputEl.value
    if (!el) return
    el.value = ''
    el.focus()
  })
}

async function submit() {
  if (submitting.value) return
  const code = raw.value
  if (code.length !== 6) return

  submitting.value = true
  result.value = null
  try {
    const data = await verifyRedemption(code)
    result.value = { ok: true, ...data }
    raw.value = ''
    nextTick(() => {
      if (inputEl.value) inputEl.value.value = ''
    })
    loadHistory()
  } catch (error) {
    // verifyRedemption 带 skipErrorToast：失败原因在本页显著展示，不弹全局 toast。
    // 后端 4 种失败都给中文原文（404 不存在 / 400 已使用 / 400 已过期 / 403 不属于本店），
    // 这里原样透出，不再自造文案，避免与后端判断口径不一致。
    result.value = {
      ok: false,
      message: error?.response?.data?.message || error?.message || '核销失败，请稍后重试',
    }
    nextTick(() => {
      const el = inputEl.value
      if (!el) return
      el.focus()
      if (typeof el.setSelectionRange === 'function') el.setSelectionRange(0, el.value.length)
    })
  } finally {
    submitting.value = false
  }
}

/* ---------- 历史记录 ---------- */
async function loadHistory() {
  historyLoading.value = true
  try {
    const data = await getMerchantRedemptions({ status: 2, page: 1, size: 10 })
    history.value = data?.list || []
  } catch {
    // 错误提示由请求拦截器统一处理
    history.value = []
  } finally {
    historyLoading.value = false
  }
}

/* ---------- 展示工具 ---------- */
function redemptionStatusClass(status) {
  const map = {
    1: 'ms-redeem-wait',
    2: 'ms-redeem-done',
    3: 'ms-redeem-expired',
    4: 'ms-redeem-cancelled',
  }
  return map[Number(status)] || 'ms-redeem-cancelled'
}

function prettyCode(code) {
  const s = String(code ?? '').replace(/\s+/g, '')
  if (!s) return '——'
  if (s.length === 6) return `${s.slice(0, 3)} ${s.slice(3)}`
  const mid = Math.ceil(s.length / 2)
  return `${s.slice(0, mid)} ${s.slice(mid)}`
}

function formatDateTime(value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.toLocaleDateString('zh-CN')} ${d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
}

onMounted(() => {
  loadHistory()
  nextTick(() => inputEl.value?.focus())
})
</script>

<style scoped>
/* ---------- 输入区 ---------- */
.verify-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.verify-label {
  margin-bottom: 12px;
  font-size: 15px;
  font-weight: 700;
  color: var(--mw-text);
}

/* 大字输入框：核销员要一眼看清数字 */
.verify-input {
  width: min(420px, 100%);
  padding: 16px 12px;
  font-family: inherit;
  /* 基准 34px 起，助老模式再放大一档 */
  font-size: clamp(30px, 7vw, 40px);
  font-weight: 800;
  letter-spacing: 0.14em;
  text-align: center;
  color: var(--mw-text);
  background: var(--mw-card);
  border: 2px solid var(--mw-border);
  border-radius: 16px;
  font-variant-numeric: tabular-nums;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.verify-input::placeholder {
  color: var(--mw-text-sub);
  opacity: 0.5;
  letter-spacing: 0.14em;
}

.verify-input:focus {
  outline: none;
  border-color: var(--mw-green);
  box-shadow: 0 0 0 4px rgba(47, 133, 90, 0.18);
}

.verify-input:disabled {
  opacity: 0.6;
}

.verify-tip {
  margin: 12px 0 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--mw-text-sub);
}

.verify-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: center;
  margin-top: 18px;
}

/* ---------- 结果区 ---------- */
.result-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.result-badge {
  display: grid;
  place-items: center;
  width: 64px;
  height: 64px;
  margin-bottom: 10px;
  color: #fff;
  border-radius: 50%;
}

.result-card.is-ok .result-badge {
  background: #16a34a;
}

.result-card.is-bad .result-badge {
  background: #dc2626;
}

.result-badge svg {
  width: 34px;
  height: 34px;
}

.result-title {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 800;
  color: var(--mw-text);
}

.result-message {
  margin: 0 0 12px;
  font-size: 16px;
  font-weight: 700;
  line-height: 1.7;
  color: #b91c1c;
}

.result-list {
  display: grid;
  gap: 0;
  width: min(420px, 100%);
  margin: 10px 0 0;
  text-align: left;
}

.result-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 0;
  border-top: 1px solid var(--mw-border);
}

.result-row:first-child {
  border-top: none;
}

.result-row dt {
  flex: 0 0 84px;
  font-size: 14px;
  color: var(--mw-text-sub);
}

.result-row dd {
  flex: 1 1 auto;
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  text-align: right;
  color: var(--mw-text);
  word-break: break-all;
}

.reason-list {
  width: min(460px, 100%);
  margin: 4px 0 0;
  padding-left: 20px;
  font-size: 13px;
  line-height: 1.9;
  text-align: left;
  color: var(--mw-text-sub);
}

.result-actions {
  margin-top: 18px;
}

/* ---------- 历史记录 ---------- */
.card-sub {
  font-size: 12px;
  color: var(--mw-text-sub);
}

.hist-list {
  display: flex;
  flex-direction: column;
}

.hist-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 13px 8px;
  border-top: 1px solid var(--mw-border);
}

.hist-row:first-child {
  border-top: none;
}

.hist-thumb {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 46px;
  height: 46px;
  font-size: 22px;
  background: var(--mw-bg);
  border: 1px solid var(--mw-border);
  border-radius: 12px;
}

.hist-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1 1 auto;
  min-width: 0;
}

.hist-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--mw-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hist-sub {
  font-size: 13px;
  color: var(--mw-text-sub);
}

.hist-time {
  font-size: 12.5px;
  color: var(--mw-text-sub);
}
</style>

<!-- ============================================================
     非 scoped：高对比度 / 助老模式
     ============================================================ -->
<style>
html.theme-high-contrast .mw-shell .verify-input {
  color: #ffffff;
  background: #000000;
  border-color: #ffffff;
}

html.theme-high-contrast .mw-shell .verify-input:focus {
  border-color: #4ade80;
  box-shadow: 0 0 0 4px rgba(74, 222, 128, 0.35);
}

html.theme-high-contrast .mw-shell .result-card.is-ok .result-badge,
html.theme-high-contrast .mw-shell .result-card.is-bad .result-badge {
  color: #000000;
  background: #ffffff;
}

html.theme-high-contrast .mw-shell .result-message {
  color: #fca5a5;
}

html.theme-high-contrast .mw-shell .hist-thumb {
  background: #000000;
  border-color: #ffffff;
}

html.mode-elderly .mw-shell .verify-input {
  font-size: clamp(40px, 9vw, 56px);
  padding: 20px 12px;
}

html.mode-elderly .mw-shell .verify-label,
html.mode-elderly .mw-shell .result-title {
  font-size: 26px;
}

html.mode-elderly .mw-shell .verify-tip,
html.mode-elderly .mw-shell .reason-list,
html.mode-elderly .mw-shell .result-message,
html.mode-elderly .mw-shell .result-row dt,
html.mode-elderly .mw-shell .hist-sub,
html.mode-elderly .mw-shell .hist-time,
html.mode-elderly .mw-shell .card-sub {
  font-size: 18px;
}

html.mode-elderly .mw-shell .result-row dd,
html.mode-elderly .mw-shell .hist-title {
  font-size: 20px;
}

html.mode-elderly .mw-shell .hist-row {
  padding: 18px 8px;
}

html.mode-elderly .mw-shell .hist-thumb {
  width: 60px;
  height: 60px;
  font-size: 28px;
}
</style>
