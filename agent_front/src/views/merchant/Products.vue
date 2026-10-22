<template>
  <section class="mw-page mw-products">
    <div class="mw-page-head">
      <div>
        <h1 class="mw-page-title">商品管理</h1>
        <p class="mw-page-desc">上架邻居能用积分兑换的服务，库存和积分随时可改</p>
      </div>
      <div class="head-actions">
        <button type="button" class="mw-btn" :disabled="loading" @click="load">
          {{ loading ? '刷新中…' : '刷新' }}
        </button>
        <el-button type="primary" size="large" @click="openCreate">+ 上架新商品</el-button>
      </div>
    </div>

    <p v-if="merchantStatus !== null && merchantStatus !== 1" class="mw-error" role="alert">
      店铺当前状态为「{{ statusLabelOf(merchantStatus) }}」，需通过审核后才能上架或修改商品。
    </p>

    <div class="mw-card">
      <div class="mw-card-head">
        <h2 class="mw-card-title">我的商品（{{ list.length }}）</h2>
        <span class="card-sub">含已下架商品</span>
      </div>

      <p v-if="loading && !list.length" class="mw-empty">加载中…</p>

      <div v-else-if="list.length" class="prod-list">
        <!-- 表头（窄屏隐藏，靠 .col-label 逐项标注） -->
        <div class="prod-head" aria-hidden="true">
          <span>商品</span>
          <span>所需积分</span>
          <span>库存</span>
          <span>已兑换</span>
          <span>状态</span>
          <span>操作</span>
        </div>

        <div v-for="product in list" :key="product.id" class="prod-row">
          <span class="prod-thumb">
            <img v-if="product.image_url" :src="product.image_url" alt="" />
            <span v-else aria-hidden="true">🎁</span>
          </span>

          <span class="prod-info">
            <span class="prod-title">{{ product.title || '未命名商品' }}</span>
            <span class="prod-desc">{{ product.description || '未填写描述' }}</span>
          </span>

          <span class="prod-col">
            <span class="col-label">所需积分</span>
            <span class="col-value" :class="{ free: !product.points_cost }">
              {{ pointsText(product.points_cost) }}
            </span>
          </span>

          <span class="prod-col">
            <span class="col-label">库存</span>
            <span class="col-value">{{ product.stock }}</span>
          </span>

          <span class="prod-col">
            <span class="col-label">已兑换</span>
            <span class="col-value">{{ product.sold_count }}</span>
          </span>

          <span class="prod-status">
            <!-- 商品状态：第四套 ms-* -->
            <span class="status-tag" :class="productStatusClass(product.status)">
              {{ product.status_label }}
            </span>
            <span v-if="Number(product.stock) <= 0" class="soldout">已兑完</span>
          </span>

          <span class="prod-actions">
            <button type="button" class="mw-btn" @click="openEdit(product)">编辑</button>
            <button
              v-if="Number(product.status) === 1"
              type="button"
              class="mw-btn danger"
              @click="offline(product)"
            >
              下架
            </button>
            <button v-else type="button" class="mw-btn primary" @click="online(product)">
              重新上架
            </button>
          </span>
        </div>
      </div>

      <template v-else>
        <p class="mw-empty">还没有商品，点上架新商品开始吧</p>
        <div class="empty-cta">
          <el-button type="primary" size="large" @click="openCreate">+ 上架新商品</el-button>
        </div>
      </template>
    </div>

    <!-- ===== 新建 / 编辑 Dialog ===== -->
    <el-dialog
      v-model="dialogVisible"
      :title="editing ? '编辑商品' : '上架新商品'"
      width="min(520px, 94vw)"
      append-to-body
      align-center
      class="product-dialog"
    >
      <div class="form-item">
        <label class="form-label" for="prod-title">商品名称<span class="req" aria-hidden="true">*</span></label>
        <el-input
          id="prod-title"
          v-model="form.title"
          maxlength="100"
          show-word-limit
          placeholder="如：打印券10张"
        />
      </div>

      <div class="form-item">
        <label class="form-label" for="prod-desc">商品描述</label>
        <el-input
          id="prod-desc"
          v-model="form.description"
          type="textarea"
          :rows="3"
          maxlength="2000"
          placeholder="写清使用范围、有效期、注意事项…"
        />
      </div>

      <div class="form-item">
        <label class="form-label" for="prod-image">图片链接（选填）</label>
        <el-input
          id="prod-image"
          v-model="form.image_url"
          maxlength="500"
          placeholder="填 https:// 开头的图片地址，留空用图标占位"
        />
        <p class="form-tip">
          <template v-if="hasLocalImage && !form.image_url">
            当前已有本店上传的图片，留空表示保持不变。
          </template>
          <template v-else>本阶段不支持上传图片，填外部图片地址即可；留空则由图标占位。</template>
        </p>
      </div>

      <div class="two-cols">
        <div class="form-item">
          <label class="form-label" for="prod-points">所需积分<span class="req" aria-hidden="true">*</span></label>
          <el-input
            id="prod-points"
            v-model="form.points_cost"
            inputmode="numeric"
            placeholder="0 表示免费券"
          />
          <p class="form-tip">{{ Number(form.points_cost) === 0 ? '该商品为免费券，兑换不扣积分' : '邻居兑换时扣掉的积分数' }}</p>
        </div>

        <div class="form-item">
          <label class="form-label" for="prod-stock">库存<span class="req" aria-hidden="true">*</span></label>
          <el-input
            id="prod-stock"
            v-model="form.stock"
            inputmode="numeric"
            placeholder="如：100"
          />
          <p class="form-tip">每次兑换自动减 1，为 0 时自动停兑</p>
        </div>
      </div>

      <p v-if="formError" class="form-error" role="alert">{{ formError }}</p>

      <template #footer>
        <div class="dialog-actions">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="save">
            {{ editing ? '保存修改' : '确认上架' }}
          </el-button>
        </div>
      </template>
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createMerchantProduct,
  getMerchantProducts,
  offlineMerchantProduct,
  onlineMerchantProduct,
  updateMerchantProduct,
} from '../../api/merchant'

/**
 * 商品管理。
 *
 * 【图片只支持填 URL】
 * 本阶段不做 multipart 上传（`ImageUploader` 只产出 File、项目也没有通用上传端点），
 * 因此 image_url 允许填外部图片地址、或留空走 emoji 占位。
 *
 * 【★ 一个必须绕开的坑：签名 URL 不能回写】
 * 后端的图片字段存的是**相对路径**，读取时现场补 HMAC 签名
 * （`/api/v1/static/xxx.png?exp=…&sig=…`，1 小时过期）。
 * 如果把读回来的 image_url 直接回写数据库，第二次读取会把这个带签名的字符串
 * 当成相对路径再签一次，得到一条彻底废掉的路径。
 * 所以编辑时：
 *   - 外链（http/https）→ 原样回填，用户可改可清空；
 *   - 本地图片（带签名）→ 输入框留空 + 提示「留给空表示保持不变」，
 *     提交时**不携带** image_url 字段（后端 exclude_unset 不会碰它）。
 */
const list = ref([])
const merchantStatus = ref(null)
const loading = ref(false)

const dialogVisible = ref(false)
const editing = ref(null)
const saving = ref(false)
const formError = ref('')
// 编辑对象是否含「本地图片（带签名）」；非空时输入框留空表示保持不变
const hasLocalImage = ref(false)
// 打开编辑时的图片显示值，用于判断用户是否动过这个字段
const originalImageShown = ref('')

const form = reactive({ title: '', description: '', image_url: '', points_cost: '0', stock: '0' })

const SHOP_STATUS_LABEL = { 0: '审核中', 1: '已通过', 2: '已拒绝', 3: '已停业' }

function statusLabelOf(status) {
  return SHOP_STATUS_LABEL[Number(status)] || '未知'
}

/* ---------- 状态类名（第四套 ms-*，语义命名） ---------- */
function productStatusClass(status) {
  return Number(status) === 1 ? 'ms-online' : 'ms-offline'
}

// 0 积分 = 免费券：不显示「0 积分」，显示「免费」
function pointsText(value) {
  return Number(value) > 0 ? `${Number(value)} 积分` : '免费'
}

function isExternal(url) {
  return typeof url === 'string' && /^https?:\/\//i.test(url)
}

/* ---------- 列表 ---------- */
async function load() {
  loading.value = true
  try {
    const data = await getMerchantProducts()
    list.value = data?.list || []
    merchantStatus.value = Number(data?.merchant_status ?? 1)
  } catch {
    // 错误提示由请求拦截器统一处理
    list.value = []
  } finally {
    loading.value = false
  }
}

/* ---------- Dialog ---------- */
function openCreate() {
  editing.value = null
  formError.value = ''
  hasLocalImage.value = false
  originalImageShown.value = ''
  form.title = ''
  form.description = ''
  form.image_url = ''
  form.points_cost = '0'
  form.stock = '0'
  dialogVisible.value = true
}

function openEdit(product) {
  editing.value = product
  formError.value = ''
  form.title = product.title || ''
  form.description = product.description || ''
  form.points_cost = String(product.points_cost ?? 0)
  form.stock = String(product.stock ?? 0)

  const external = isExternal(product.image_url)
  hasLocalImage.value = Boolean(product.image_url) && !external
  form.image_url = external ? product.image_url : ''
  originalImageShown.value = form.image_url

  dialogVisible.value = true
}

function parseCount(value, label) {
  const text = String(value ?? '').trim()
  if (text === '') return { error: `请填写${label}` }
  if (!/^\d+$/.test(text)) return { error: `${label}必须是非负整数` }
  return { value: Number(text) }
}

async function save() {
  formError.value = ''
  const title = form.title.trim()
  if (!title) {
    formError.value = '请填写商品名称'
    return
  }
  const points = parseCount(form.points_cost, '所需积分')
  if (points.error) {
    formError.value = points.error
    return
  }
  const stock = parseCount(form.stock, '库存')
  if (stock.error) {
    formError.value = stock.error
    return
  }

  const payload = {
    title,
    description: form.description || '',
    points_cost: points.value,
    stock: stock.value,
  }
  // 只在「用户确实动过图片字段」时才带上它：
  // 否则本地图片会被空串清掉（见文件头注释）
  if (!editing.value || form.image_url !== originalImageShown.value) {
    payload.image_url = form.image_url.trim()
  }

  saving.value = true
  try {
    if (editing.value) {
      // 带 skipErrorToast：错误在 Dialog 内提示，避免「拦截器 + Dialog」双弹
      await updateMerchantProduct(editing.value.id, payload)
      ElMessage.success('商品已更新')
    } else {
      await createMerchantProduct(payload)
      ElMessage.success('商品已上架')
    }
    dialogVisible.value = false
    await load()
  } catch (error) {
    formError.value = error?.response?.data?.message || error?.message || '保存失败，请稍后重试'
  } finally {
    saving.value = false
  }
}

/* ---------- 上下架 ---------- */
async function offline(product) {
  try {
    await ElMessageBox.confirm(
      `下架后邻居将无法兑换「${product.title}」，已兑换的核销码不受影响。可随时重新上架。`,
      '确认下架？',
      { confirmButtonText: '下架', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return // 用户取消
  }
  try {
    await offlineMerchantProduct(product.id)
    ElMessage.success('商品已下架')
    await load()
  } catch {
    // skipErrorToast：这里补一次提示，避免静默失败
    ElMessage.error('下架失败，请稍后重试')
  }
}

async function online(product) {
  try {
    await onlineMerchantProduct(product.id)
    ElMessage.success('商品已重新上架')
    await load()
  } catch {
    ElMessage.error('上架失败，请稍后重试')
  }
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

.empty-cta {
  display: flex;
  justify-content: center;
  padding-bottom: 8px;
}

/* ---------- 列表：CSS Grid 行（窄屏堆叠） ---------- */
.prod-list {
  display: flex;
  flex-direction: column;
}

.prod-head,
.prod-row {
  display: grid;
  grid-template-columns: 64px minmax(140px, 2.2fr) 0.9fr 0.7fr 0.8fr 1fr 1.4fr;
  align-items: center;
  gap: 12px;
}

.prod-head {
  padding: 0 8px 10px;
  font-size: 12px;
  font-weight: 600;
  color: var(--mw-text-sub);
  border-bottom: 1px solid var(--mw-border);
}

.prod-row {
  padding: 14px 8px;
  border-bottom: 1px solid var(--mw-border);
}

.prod-row:last-child {
  border-bottom: none;
}

.prod-thumb {
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  overflow: hidden;
  font-size: 24px;
  background: var(--mw-bg);
  border: 1px solid var(--mw-border);
  border-radius: 12px;
}

.prod-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.prod-info {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.prod-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--mw-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.prod-desc {
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--mw-text-sub);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.prod-col {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

/* 表头在窄屏被隐藏，靠这个逐项标注，避免数字失去含义 */
.col-label {
  display: none;
  font-size: 12px;
  color: var(--mw-text-sub);
}

.col-value {
  font-size: 14px;
  font-weight: 700;
  color: var(--mw-text);
  font-variant-numeric: tabular-nums;
}

.col-value.free {
  color: var(--mw-green);
}

.prod-status {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.soldout {
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 600;
  color: #b45309;
  background: #fef3c7;
  border-radius: 999px;
}

.prod-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

/* ---------- Dialog 表单 ---------- */
.form-item {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--mw-text, var(--text-primary));
}

.req {
  margin-left: 2px;
  color: #dc2626;
}

.form-tip {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--mw-text-sub, var(--text-secondary));
}

.two-cols {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.form-error {
  margin: 0;
  padding: 10px 12px;
  font-size: 14px;
  font-weight: 600;
  color: #b91c1c;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 10px;
}

.dialog-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
}

/* ---------- 窄屏：表头隐藏，每行堆叠 ---------- */
@media (max-width: 900px) {
  .prod-head {
    display: none;
  }

  .prod-row {
    grid-template-columns: 64px 1fr;
    row-gap: 10px;
  }

  .prod-info {
    grid-column: 2;
  }

  .prod-col {
    grid-column: 1 / -1;
    flex-direction: row;
    align-items: baseline;
    gap: 8px;
  }

  .col-label {
    display: inline;
  }

  .prod-status,
  .prod-actions {
    grid-column: 1 / -1;
    justify-content: flex-start;
  }
}
</style>

<!-- ============================================================
     非 scoped：Dialog 挂在 body 下（append-to-body），
     根级主题选择器必须非 scoped 才能命中；表格主题态也在这里补。
     ============================================================ -->
<style>
html.theme-high-contrast .mw-shell .prod-thumb {
  background: #000000;
  border-color: #ffffff;
}

html.theme-high-contrast .mw-shell .soldout {
  color: #000000;
  background: #fcd34d;
}

html.theme-high-contrast .mw-shell .col-value.free {
  color: #4ade80;
}

html.theme-high-contrast .product-dialog.el-dialog {
  background: #000000 !important;
  border: 1px solid #ffffff !important;
}

html.theme-high-contrast .product-dialog .el-dialog__title,
html.theme-high-contrast .product-dialog .form-label {
  color: #ffffff !important;
}

html.theme-high-contrast .product-dialog .form-tip {
  color: #f2f2f2 !important;
}

html.theme-high-contrast .product-dialog .form-error {
  color: #fca5a5;
  background: #000000;
  border-color: #fca5a5;
}

html.mode-elderly .mw-shell .prod-thumb {
  width: 68px;
  height: 68px;
  font-size: 30px;
}

html.mode-elderly .mw-shell .prod-row {
  grid-template-columns: 80px minmax(140px, 2.2fr) 0.9fr 0.7fr 0.8fr 1fr 1.4fr;
  padding: 18px 8px;
}

html.mode-elderly .mw-shell .prod-title {
  font-size: 20px;
  white-space: normal;
}

html.mode-elderly .mw-shell .prod-desc,
html.mode-elderly .mw-shell .col-value,
html.mode-elderly .mw-shell .col-label,
html.mode-elderly .mw-shell .soldout {
  font-size: 17px;
}

html.mode-elderly .mw-shell .prod-actions {
  gap: 10px;
}

html.mode-elderly .product-dialog .form-tip {
  font-size: 16px;
}
</style>
