<template>
  <section class="page merchant-apply-page">
    <div class="heading-row">
      <div>
        <div class="eyebrow">商家入驻</div>
        <h1 class="page-title">
          加入<span class="gradient-text">积分商城</span>
        </h1>
        <p class="lead">开一家社区小店，让邻居用碳积分兑换你的服务</p>
      </div>
    </div>

    <!-- 总开关关闭：商家端整体不可用 -->
    <section v-if="!merchantStore.enabled" class="apply-card">
      <h2 class="card-title">商家端暂未开放</h2>
      <p class="card-hint">平台已暂时关闭商家入驻与服务兑换，请稍后再来。</p>
      <div class="form-actions">
        <el-button size="large" @click="router.push('/merchant')">返回积分商城</el-button>
      </div>
    </section>

    <!-- 身份校验中 -->
    <section v-else-if="view === 'loading'" class="apply-card">
      <p class="state-text">正在校验商家身份…</p>
    </section>

    <!-- 校验失败：不静默吞掉，给重试出口 -->
    <section v-else-if="view === 'error'" class="apply-card">
      <h2 class="card-title">身份校验失败</h2>
      <p class="card-hint">网络异常或服务暂时不可用，请重试。</p>
      <div class="form-actions">
        <el-button type="primary" size="large" :loading="refreshing" @click="refresh">
          重试
        </el-button>
      </div>
    </section>

    <!-- ===== 已通过审核 ===== -->
    <section v-else-if="view === 'approved'" class="apply-card">
      <div class="state-head">
        <span class="state-badge ok" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 12.5 9.5 18 20 6.5" />
          </svg>
        </span>
        <h2 class="state-title">您已入驻积分商城</h2>
        <span class="status-tag ms-approved">{{ merchantStore.info?.status_label || '已通过' }}</span>
      </div>
      <dl class="info-list">
        <div class="info-row"><dt>店铺名</dt><dd>{{ merchantStore.info?.name || '——' }}</dd></div>
        <div class="info-row"><dt>店铺类型</dt><dd>{{ merchantStore.info?.category || '未填写' }}</dd></div>
      </dl>
      <p class="state-desc">直接进入商家工作台，管理商品、核销订单、查看数据。</p>
      <div class="form-actions">
        <el-button type="primary" size="large" @click="router.push('/merchant/dashboard')">
          进入商家工作台
        </el-button>
        <el-button size="large" @click="router.push('/merchant')">返回积分商城</el-button>
      </div>
    </section>

    <!-- ===== 待审核 / 已拒绝 / 已停业 ===== -->
    <section v-else-if="view !== 'form'" class="apply-card">
      <div class="state-head">
        <span class="state-badge" :class="stateBadgeClass" aria-hidden="true">{{ stateIcon }}</span>
        <h2 class="state-title">{{ stateTitle }}</h2>
        <span class="status-tag" :class="stateTagClass">{{ merchantStore.info?.status_label }}</span>
      </div>

      <!-- 被拒：原因必须显著展示，否则商家不知道该改什么 -->
      <p v-if="view === 'rejected'" class="reason-box" role="alert">
        <span class="reason-label">未通过原因</span>
        <span class="reason-text">{{ merchantStore.info?.audit_reason || '平台未填写具体原因，请联系客服了解详情' }}</span>
      </p>

      <dl class="info-list">
        <div class="info-row"><dt>店铺名</dt><dd>{{ merchantStore.info?.name || '——' }}</dd></div>
        <div class="info-row"><dt>店铺类型</dt><dd>{{ merchantStore.info?.category || '未填写' }}</dd></div>
        <div class="info-row"><dt>联系方式</dt><dd>{{ merchantStore.info?.contact || '未填写' }}</dd></div>
        <div class="info-row"><dt>地址</dt><dd>{{ merchantStore.info?.address || '未填写' }}</dd></div>
        <div class="info-row"><dt>店铺简介</dt><dd>{{ merchantStore.info?.description || '未填写' }}</dd></div>
        <div class="info-row"><dt>提交时间</dt><dd>{{ formatDateTime(merchantStore.info?.created_at) || '——' }}</dd></div>
      </dl>

      <p class="state-desc">{{ stateDesc }}</p>

      <div class="form-actions">
        <template v-if="view === 'pending' || view === 'rejected'">
          <el-button type="primary" size="large" :loading="refreshing" @click="refresh">
            刷新审核状态
          </el-button>
          <el-button size="large" @click="startEdit">
            {{ view === 'rejected' ? '重新申请' : '修改资料重提' }}
          </el-button>
        </template>
        <template v-else>
          <el-button size="large" @click="router.push('/merchant')">返回积分商城</el-button>
        </template>
      </div>
    </section>

    <!-- ===== 入驻表单（首次 / 修改重提共用） ===== -->
    <section v-else class="apply-card">
      <h2 class="card-title">{{ formTitle }}</h2>
      <p class="card-hint">{{ formHint }}</p>

      <div class="form-item">
        <label class="form-label" for="apply-name">
          店铺名<span class="req" aria-hidden="true">*</span>
        </label>
        <el-input
          id="apply-name"
          v-model="form.name"
          size="large"
          maxlength="100"
          show-word-limit
          placeholder="如：社区打印店"
        />
      </div>

      <div class="form-item">
        <label class="form-label" for="apply-category">店铺类型</label>
        <el-select
          id="apply-category"
          v-model="form.category"
          size="large"
          class="full"
          clearable
          placeholder="请选择（可留空）"
          aria-label="店铺类型"
        >
          <el-option v-for="name in CATEGORIES" :key="name" :label="name" :value="name" />
        </el-select>
        <p class="form-tip">类型用于积分商城的分类筛选，可留空。</p>
      </div>

      <div class="form-item">
        <label class="form-label" for="apply-contact">联系方式</label>
        <el-input
          id="apply-contact"
          v-model="form.contact"
          size="large"
          maxlength="100"
          placeholder="手机号 / 微信"
        />
      </div>

      <div class="form-item">
        <label class="form-label" for="apply-address">地址</label>
        <el-input
          id="apply-address"
          v-model="form.address"
          size="large"
          maxlength="200"
          placeholder="如：小区北门 1 号商铺"
        />
      </div>

      <div class="form-item">
        <label class="form-label" for="apply-desc">店铺简介</label>
        <el-input
          id="apply-desc"
          v-model="form.description"
          type="textarea"
          :rows="4"
          maxlength="2000"
          show-word-limit
          placeholder="介绍一下你能提供的服务，比如打印、复印、装订…"
        />
      </div>

      <p v-if="formError" class="form-error" role="alert">{{ formError }}</p>

      <div class="form-actions">
        <el-button type="primary" size="large" :loading="submitting" @click="submit">
          {{ submitLabel }}
        </el-button>
        <el-button v-if="hasMerchant" size="large" @click="cancelEdit">取消</el-button>
        <button type="button" class="text-btn" @click="router.push('/merchant')">
          先去积分商城看看 →
        </button>
      </div>
    </section>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { applyMerchant } from '../../api/merchant'
import { useMerchantStore } from '../../store/merchant'

/**
 * 商家入驻申请页（4 态合一）。
 *
 * 【为什么状态页不单独做一个页面】
 * 后端 `GET /merchant/info` 未入驻时返回 200 + merchant:null（不是 404），
 * 本来就设计成「同一个接口决定渲染表单还是状态」。把「审核中 / 已拒绝 / 已停业」
 * 收在本页内，守卫只需做一件事：非「已通过」一律送来这里。
 * 少一个页面、少一套样式，且状态与表单天然共享同一份 merchant.info。
 *
 * 【重提的坑（阶段一后端已修，前端必须配合）】
 * 后端只覆盖**显式传入**的字段。所以提交时要把表单里所有字段都传出去
 * （含空串——空串表示「清空该项」），否则用户刚清空的地址不会被清掉。
 */
const router = useRouter()
const merchantStore = useMerchantStore()

// 值取自真实库 merchant.category 的实际取值（与积分商城筛选项同一份口径）
const CATEGORIES = ['打印', '便利店', '理发', '回收', '家政']

const form = reactive({ name: '', category: '', contact: '', address: '', description: '' })
const submitting = ref(false)
const refreshing = ref(false)
const formError = ref('')
const loadError = ref(false)
// 有店时点「修改资料 / 重新申请」才进表单态
const showForm = ref(false)

const hasMerchant = computed(() => Boolean(merchantStore.info))

const view = computed(() => {
  if (loadError.value) return 'error'
  if (!merchantStore.loaded) return 'loading'
  if (!hasMerchant.value) return 'form'
  const status = Number(merchantStore.info?.status)
  if (status === 1) return 'approved'
  if (showForm.value) return 'form'
  if (status === 0) return 'pending'
  if (status === 2) return 'rejected'
  return 'closed'
})

/* ---------- 状态视图文案 ---------- */
const STATE_META = {
  pending: {
    icon: '⏳',
    badge: 'wait',
    tag: 'ms-pending',
    title: '申请已提交，等待审核',
    desc: '平台通常会在 1 个工作日内完成审核。审核通过后即可进入工作台上架商品。',
  },
  rejected: {
    icon: '!',
    badge: 'bad',
    tag: 'ms-rejected',
    title: '入驻申请未通过',
    desc: '请按上方原因修改资料后重新提交，平台会重新审核。',
  },
  closed: {
    icon: '×',
    badge: 'off',
    tag: 'ms-closed',
    title: '店铺已停业',
    desc: '店铺处于停业状态，暂不支持自行修改或重新申请。如需重新经营请联系平台客服。',
  },
}

const stateIcon = computed(() => STATE_META[view.value]?.icon || '·')
const stateTitle = computed(() => STATE_META[view.value]?.title || '')
const stateDesc = computed(() => STATE_META[view.value]?.desc || '')
const stateBadgeClass = computed(() => STATE_META[view.value]?.badge || 'wait')
const stateTagClass = computed(() => STATE_META[view.value]?.tag || 'ms-pending')

/* ---------- 表单文案 ---------- */
const isRejected = computed(() => Number(merchantStore.info?.status) === 2)

const formTitle = computed(() => {
  if (!hasMerchant.value) return '填写入驻资料'
  if (isRejected.value) return '重新提交入驻申请'
  return '修改入驻资料'
})

const formHint = computed(() => {
  if (!hasMerchant.value) return '提交后平台会在 1 个工作日内完成审核。'
  if (isRejected.value) return '请按上方未通过原因修正资料，保存后会重新进入审核队列。'
  return '保存后会重新进入审核队列。需要清空某项，把它删成空即可。'
})

const submitLabel = computed(() => (hasMerchant.value ? '保存并重新提交' : '提交申请'))

/* ---------- 数据 ---------- */
function prefill() {
  const m = merchantStore.info
  form.name = m?.name || ''
  form.category = m?.category || ''
  form.contact = m?.contact || ''
  form.address = m?.address || ''
  form.description = m?.description || ''
  formError.value = ''
}

async function refresh() {
  refreshing.value = true
  loadError.value = false
  try {
    await merchantStore.fetchInfo(true)
    // 刷新后回到状态视图（不把用户正在填的表单顶掉）
    showForm.value = false
    ElMessage.success('已刷新审核状态')
  } catch {
    // fetchInfo 带 skipErrorToast（守卫也会调它），错误提示由本页负责，只弹一次
    loadError.value = !merchantStore.loaded
    ElMessage.error('刷新失败，请检查网络后重试')
  } finally {
    refreshing.value = false
  }
}

function startEdit() {
  prefill()
  showForm.value = true
}

function cancelEdit() {
  showForm.value = false
  formError.value = ''
}

async function submit() {
  formError.value = ''
  const name = form.name.trim()
  if (!name) {
    formError.value = '请填写店铺名'
    return
  }

  submitting.value = true
  try {
    // 字段全部显式传出（空串 → 后端落 NULL），避免「没重填的项被保留成旧值」
    await applyMerchant({
      name,
      category: form.category || '',
      contact: form.contact || '',
      address: form.address || '',
      description: form.description || '',
    })
    const resent = hasMerchant.value
    ElMessage.success(resent ? '已重新提交入驻申请，请等待审核' : '入驻申请已提交，请等待审核')
    await merchantStore.fetchInfo(true)
    showForm.value = false
    prefill()
  } catch (error) {
    // applyMerchant 带 skipErrorToast：错误在卡片内展示，不弹全局 toast
    formError.value = error?.response?.data?.message || error?.message || '提交失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}

/* ---------- 展示工具 ---------- */
function formatDateTime(value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.toLocaleDateString('zh-CN')} ${d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
}

onMounted(async () => {
  try {
    await merchantStore.fetchInfo()
  } catch {
    loadError.value = true
  }
  prefill()
  // 没有店铺 → 直接展示表单，省掉一次点击
  showForm.value = !hasMerchant.value
})
</script>

<style scoped>
/* 局部设计令牌：与工作台 .mw-shell 同构，本页在 MainLayout 下独立生效 */
.merchant-apply-page {
  max-width: 760px;
  --mw-green: var(--green-primary);
  --mw-text: var(--text-primary);
  --mw-text-sub: var(--text-secondary);
  --mw-bg: #f7f8f7;
  --mw-card: #ffffff;
  --mw-border: #e5e7eb;
  --mw-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.heading-row {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
}

/* ---------- 卡片 ---------- */
.apply-card {
  margin-top: 24px;
  padding: 24px;
  background: var(--mw-card);
  border: 1px solid var(--mw-border);
  border-radius: 16px;
  box-shadow: var(--mw-shadow);
}

.card-title {
  position: relative;
  margin: 0 0 8px;
  padding-left: 12px;
  font-size: 18px;
  font-weight: 700;
  color: var(--mw-text);
}

.card-title::before {
  content: "";
  position: absolute;
  left: 0;
  top: 50%;
  width: 4px;
  height: 16px;
  border-radius: 2px;
  background: var(--mw-green);
  transform: translateY(-50%);
}

.card-hint {
  margin: 0 0 20px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--mw-text-sub);
}

.state-text {
  margin: 0;
  padding: 12px 0;
  font-size: 14px;
  color: var(--mw-text-sub);
}

/* ---------- 状态视图 ---------- */
.state-head {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 18px;
}

.state-badge {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  font-size: 20px;
  font-weight: 800;
  color: #fff;
  background: #f59e0b;
  border-radius: 50%;
}

.state-badge.ok {
  background: #16a34a;
  color: #fff;
}

.state-badge.bad {
  background: #dc2626;
}

.state-badge.off {
  background: #8a8a8a;
}

.state-badge svg {
  width: 24px;
  height: 24px;
}

.state-title {
  margin: 0;
  font-size: 19px;
  font-weight: 700;
  color: var(--mw-text);
}

.state-desc {
  margin: 14px 0 0;
  font-size: 14px;
  line-height: 1.8;
  color: var(--mw-text-sub);
}

/* 拒绝原因：必须醒目（商家靠它知道要改什么） */
.reason-box {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0 0 18px;
  padding: 12px 14px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-left: 4px solid #dc2626;
  border-radius: 10px;
}

.reason-label {
  font-size: 12px;
  font-weight: 700;
  color: #b91c1c;
}

.reason-text {
  font-size: 14px;
  line-height: 1.7;
  color: #7f1d1d;
}

/* ---------- 只读信息列表 ---------- */
.info-list {
  display: grid;
  gap: 0;
  margin: 0;
}

.info-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 11px 0;
  border-top: 1px solid var(--mw-border);
}

.info-row:first-child {
  border-top: none;
}

.info-row dt {
  flex: 0 0 88px;
  font-size: 14px;
  color: var(--mw-text-sub);
}

.info-row dd {
  flex: 1 1 auto;
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.7;
  text-align: right;
  color: var(--mw-text);
  word-break: break-all;
}

/* ---------- 表单 ---------- */
.form-item {
  margin-bottom: 18px;
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

.form-tip {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--mw-text-sub);
}

.full {
  width: 100%;
}

.form-error {
  margin: 0 0 14px;
  padding: 10px 12px;
  font-size: 14px;
  font-weight: 600;
  color: #b91c1c;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 10px;
}

.form-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.text-btn {
  min-height: 34px;
  padding: 6px 10px;
  margin-left: auto;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  color: var(--mw-green);
  background: none;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s ease;
}

.text-btn:hover {
  background: var(--mw-bg);
}

.text-btn:focus-visible {
  outline: 3px solid var(--mw-green);
  outline-offset: 2px;
}
</style>

<!-- ============================================================
     非 scoped：本页在 MainLayout 下（.mw-shell 的令牌拿不到），
     故自带一份 ms-* 店铺状态色 + 高对比度 / 助老模式覆盖。
     以 .merchant-apply-page 前缀隔离，不污染其它页面。
     ============================================================ -->
<style>
/* ---------- 本页自带的 ms-* 店铺状态色 ----------
   本页在 MainLayout 下、不在 .mw-shell 里，故不能依赖工作台布局的样式，
   这里自带一份同类名的规则（各自页面前缀隔离，不会互相影响）。 */
.merchant-apply-page .status-tag {
  display: inline-block;
  flex-shrink: 0;
  padding: 2px 10px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.7;
  color: #fff;
  border-radius: 999px;
  white-space: nowrap;
}

.merchant-apply-page .ms-pending {
  background: #f59e0b;
}

.merchant-apply-page .ms-approved {
  background: #16a34a;
}

.merchant-apply-page .ms-rejected {
  background: #dc2626;
}

.merchant-apply-page .ms-closed {
  background: #8a8a8a;
}

html.theme-high-contrast .merchant-apply-page {
  --mw-card: #000000;
  --mw-bg: #000000;
  --mw-border: #ffffff;
  --mw-shadow: none;
}

html.theme-high-contrast .merchant-apply-page .status-tag {
  color: #000000;
}

html.theme-high-contrast .merchant-apply-page .ms-pending {
  background: #fcd34d;
}

html.theme-high-contrast .merchant-apply-page .ms-approved {
  background: #4ade80;
}

html.theme-high-contrast .merchant-apply-page .ms-rejected {
  background: #fca5a5;
}

html.theme-high-contrast .merchant-apply-page .ms-closed {
  background: #e5e5e5;
}

html.theme-high-contrast .merchant-apply-page .reason-box {
  background: #000000;
  border-color: #fca5a5;
}

html.theme-high-contrast .merchant-apply-page .reason-label,
html.theme-high-contrast .merchant-apply-page .reason-text,
html.theme-high-contrast .merchant-apply-page .form-error {
  color: #fca5a5;
}

html.theme-high-contrast .merchant-apply-page .form-error {
  background: #000000;
  border-color: #fca5a5;
}

html.theme-high-contrast .merchant-apply-page .state-badge,
html.theme-high-contrast .merchant-apply-page .state-badge.ok,
html.theme-high-contrast .merchant-apply-page .state-badge.bad,
html.theme-high-contrast .merchant-apply-page .state-badge.off {
  color: #000000;
  background: #ffffff;
}

html.theme-high-contrast .merchant-apply-page .text-btn {
  color: #4ade80;
}

/* 助老模式：字号放大 + 点击目标 ≥60px */
html.mode-elderly .merchant-apply-page .card-title {
  font-size: 24px;
}

html.mode-elderly .merchant-apply-page .card-hint,
html.mode-elderly .merchant-apply-page .state-desc,
html.mode-elderly .merchant-apply-page .form-tip,
html.mode-elderly .merchant-apply-page .reason-text,
html.mode-elderly .merchant-apply-page .form-error {
  font-size: 18px;
}

html.mode-elderly .merchant-apply-page .form-label,
html.mode-elderly .merchant-apply-page .info-row dt,
html.mode-elderly .merchant-apply-page .info-row dd,
html.mode-elderly .merchant-apply-page .state-title {
  font-size: 20px;
}

html.mode-elderly .merchant-apply-page .info-row dt {
  flex-basis: 110px;
}

html.mode-elderly .merchant-apply-page .status-tag {
  font-size: 18px;
}

html.mode-elderly .merchant-apply-page .el-button,
html.mode-elderly .merchant-apply-page .text-btn {
  min-height: 60px;
  padding: 12px 24px;
  font-size: 18px;
}

html.mode-elderly .merchant-apply-page .info-row {
  padding: 16px 0;
}
</style>
