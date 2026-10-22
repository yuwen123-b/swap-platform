<template>
  <div class="page profile-page">
    <p class="eyebrow">个人中心</p>
    <h1 class="page-title">个人中心</h1>
    <p class="lead">管理你的资料与系统设置，配置会保存到账号</p>

    <!-- ===== 第一区：用户信息卡（Hero） ===== -->
    <section class="profile-card hero-card">
      <!-- 顶部渐变带（纯装饰） -->
      <div class="hero-band" aria-hidden="true"></div>

      <!-- 助老模式快捷开关：Hero 卡右下角 -->
      <button
        type="button"
        class="elderly-quick-toggle"
        :class="{ active: elderlyMode }"
        :aria-pressed="elderlyMode"
        :aria-label="elderlyMode ? '关闭助老模式' : '开启助老模式'"
        :title="elderlyMode ? '关闭助老模式' : '开启助老模式'"
        :disabled="togglingElderly"
        @click="toggleElderlyMode"
      >
        <span aria-hidden="true">👁️</span>
      </button>

      <div class="hero-body">
        <!-- 头像：悬浮于渐变带下沿，点击上传/更换 -->
        <div
          class="avatar-wrap"
          role="button"
          tabindex="0"
          aria-label="点击更换头像"
          @click="pickAvatar"
          @keydown.enter.prevent="pickAvatar"
          @keydown.space.prevent="pickAvatar"
        >
          <img v-if="avatarSrc" class="avatar-img" :src="avatarSrc" :alt="`${displayName}的头像`" />
          <div v-else class="avatar-circle" aria-hidden="true">{{ avatarText }}</div>
          <span class="avatar-mask">更换</span>
          <input
            ref="avatarInput"
            class="avatar-input"
            type="file"
            accept="image/jpeg,image/png"
            @change="onAvatarChange"
          />
        </div>

        <div class="hero-info">
          <!-- 昵称 + 等级徽章 + 编辑 -->
          <div class="nickname-row">
            <template v-if="editingNickname">
              <el-input
                ref="nicknameInput"
                v-model="nicknameDraft"
                size="large"
                maxlength="20"
                class="nickname-input"
                placeholder="请输入昵称"
                @keyup.enter="saveNickname"
              />
              <el-button type="primary" :loading="savingNickname" @click="saveNickname">保存</el-button>
              <el-button link @click="cancelNickname">取消</el-button>
            </template>
            <template v-else>
              <span class="nickname-text">{{ displayName }}</span>
              <span class="level-badge" :class="`level-${level.code}`">{{ level.label }}</span>
              <el-button
                link
                type="primary"
                class="edit-btn"
                aria-label="编辑昵称"
                @click="startEditNickname"
              >
                编辑
              </el-button>
            </template>
          </div>

          <!-- 所在社区：昵称下方小字 -->
          <p v-if="profile?.community" class="community-line">{{ profile.community }}</p>

          <!-- 数据展示区：加入天数 + 碳积分（两列） -->
          <div class="stat-grid">
            <div class="stat-block">
              <span class="stat-value">{{ joinDays }}<span class="stat-unit">天</span></span>
              <span class="stat-label">加入社区</span>
            </div>
            <div class="stat-block">
              <span class="stat-value">{{ pointsDisplay }}<span class="stat-unit">分</span></span>
              <span class="stat-label">碳积分</span>
            </div>
          </div>

          <!-- 碳积分进度：到下一级的进度 -->
          <div class="progress-wrap">
            <div
              class="progress-track"
              role="progressbar"
              aria-valuemin="0"
              aria-valuemax="100"
              :aria-valuenow="progress.percent"
              :aria-label="progress.text"
            >
              <div class="progress-fill" :style="{ width: `${progress.percent}%` }"></div>
            </div>
            <p class="progress-text">{{ progress.text }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ===== 第二区：我的物品（最近 3 条，查看全部跳独立子页） ===== -->
    <section class="profile-card">
      <div class="card-head">
        <h2 class="card-title">我的物品</h2>
        <button type="button" class="more-link" @click="router.push('/profile/items')">查看全部</button>
      </div>

      <div class="mini-tabs" role="tablist" aria-label="按状态筛选我的物品">
        <button
          v-for="tab in ITEM_TABS"
          :key="String(tab.key)"
          type="button"
          role="tab"
          class="mini-tab"
          :class="{ active: activeItemTab === tab.key }"
          :aria-selected="activeItemTab === tab.key"
          @click="switchItemTab(tab.key)"
        >
          {{ tab.label }}
        </button>
      </div>

      <p v-if="itemsLoading" class="mini-empty">加载中…</p>

      <template v-else-if="myItems.length">
        <button
          v-for="item in myItems"
          :key="item.id"
          type="button"
          class="mini-row"
          @click="router.push(`/items/${item.id}`)"
        >
          <span class="mini-thumb">
            <img v-if="item.cover" :src="item.cover" alt="" />
            <span v-else aria-hidden="true">📦</span>
          </span>
          <span class="mini-main">
            <span class="mini-title">{{ item.title || '未命名物品' }}</span>
            <span class="mini-time">{{ formatShortDate(item.created_at) }}</span>
          </span>
          <span class="status-tag" :class="`s-${item.status}`">{{ item.status_label }}</span>
        </button>
      </template>

      <p v-else class="mini-empty">{{ itemsEmptyText }}</p>
    </section>

    <!-- ===== 我的收藏（最近 3 条，查看全部跳独立子页） ===== -->
    <section class="profile-card">
      <div class="card-head">
        <h2 class="card-title">我的收藏</h2>
        <button type="button" class="more-link" @click="router.push('/profile/favorites')">查看全部</button>
      </div>

      <p v-if="favoritesLoading" class="mini-empty">加载中…</p>

      <template v-else-if="myFavorites.length">
        <button
          v-for="fav in myFavorites"
          :key="fav.favorite_id"
          type="button"
          class="mini-row"
          @click="toFavoriteItem(fav)"
        >
          <span class="mini-thumb">
            <img v-if="fav.cover" :src="fav.cover" alt="" />
            <span v-else aria-hidden="true">📦</span>
          </span>
          <span class="mini-main">
            <span class="mini-title">{{ fav.title || '物品已不存在' }}</span>
            <span class="mini-time">收藏于 {{ formatShortDate(fav.favorited_at) }}</span>
          </span>
          <span class="status-tag" :class="`s-${fav.status}`">{{ fav.status_label }}</span>
        </button>
      </template>

      <p v-else class="mini-empty">还没有收藏任何物品，在物品详情页点右上角的心形即可收藏</p>
    </section>

    <!-- ===== 我想要的（我的需求，最近 3 条，查看全部跳独立子页） ===== -->
    <section class="profile-card">
      <div class="card-head">
        <h2 class="card-title">我想要的</h2>
        <button type="button" class="more-link" @click="router.push('/profile/demands')">查看全部</button>
      </div>

      <p v-if="demandsLoading" class="mini-empty">加载中…</p>

      <template v-else-if="myDemands.length">
        <button
          v-for="demand in myDemands"
          :key="demand.id"
          type="button"
          class="mini-row"
          @click="router.push('/profile/demands')"
        >
          <span class="mini-main">
            <span class="mini-title">{{ demand.title || '未命名需求' }}</span>
            <span class="mini-time">发布于 {{ formatShortDate(demand.created_at) }}</span>
          </span>
          <span class="status-tag" :class="`s-${demand.status}`">{{ demand.status_label }}</span>
        </button>
      </template>

      <p v-else class="mini-empty">还没有发布过需求，去「我想要的」写下你在找的物品吧</p>
    </section>

    <!-- ===== 第四区：碳积分概览（汇总 + 进度 + 最近 3 条明细） ===== -->
    <section class="profile-card">
      <div class="card-head">
        <h2 class="card-title">碳积分概览</h2>
        <button type="button" class="more-link" @click="router.push('/profile/carbon')">查看明细</button>
      </div>

      <div class="mini-stats">
        <div class="stat-block">
          <span class="stat-value">{{ carbonSummary.total_points }}<span class="stat-unit">分</span></span>
          <span class="stat-label">碳积分余额</span>
        </div>
        <div class="stat-block">
          <span class="stat-value">{{ carbonDisplay }}<span class="stat-unit">kg</span></span>
          <span class="stat-label">碳减排量</span>
        </div>
        <div class="stat-block">
          <span class="stat-value">{{ carbonSummary.exchange_count }}<span class="stat-unit">次</span></span>
          <span class="stat-label">完成交换</span>
        </div>
      </div>

      <div class="progress-wrap">
        <div
          class="progress-track"
          role="progressbar"
          aria-valuemin="0"
          aria-valuemax="100"
          :aria-valuenow="carbonSummary.progress_percent"
          :aria-label="carbonProgressText"
        >
          <div class="progress-fill" :style="{ width: `${carbonSummary.progress_percent}%` }"></div>
        </div>
        <p class="progress-text">{{ carbonProgressText }}</p>
      </div>

      <h3 class="mini-sub">最近积分变动</h3>
      <template v-if="recentLogs.length">
        <div v-for="log in recentLogs" :key="log.id" class="mini-row static">
          <span class="mini-main">
            <span class="mini-title">{{ log.description || log.source_label }}</span>
            <span class="mini-time">{{ formatShortDate(log.created_at) }}</span>
          </span>
          <span class="log-delta" :class="log.points >= 0 ? 'plus' : 'minus'">
            {{ log.points >= 0 ? '+' : '' }}{{ log.points }}
          </span>
        </div>
      </template>
      <p v-else class="mini-empty">暂无积分记录，发布物品通过审核即可获得积分</p>
    </section>

    <!-- ===== 第三区：我的交换（最近 3 条，查看全部跳独立子页） ===== -->
    <section class="profile-card">
      <div class="card-head">
        <h2 class="card-title">我的交换</h2>
        <button type="button" class="more-link" @click="router.push('/profile/exchanges')">查看全部</button>
      </div>

      <p v-if="ordersLoading" class="mini-empty">加载中…</p>

      <template v-else-if="myOrders.length">
        <button
          v-for="order in myOrders"
          :key="order.order_id"
          type="button"
          class="mini-row"
          @click="router.push('/profile/exchanges')"
        >
          <span class="mini-thumb">
            <img v-if="order.item_image" :src="order.item_image" alt="" />
            <span v-else aria-hidden="true">📦</span>
          </span>
          <span class="mini-main">
            <span class="mini-title">{{ order.item_title || '未命名物品' }}</span>
            <span class="mini-time">
              与 {{ order.other_nickname }} · {{ formatShortDate(order.created_at) }}
            </span>
          </span>
          <span class="status-tag" :class="`os-${order.status}`">{{ order.status_label }}</span>
        </button>
      </template>

      <template v-else>
        <p class="mini-empty">还没有交换记录，去探索物品发起交换吧</p>
        <button type="button" class="empty-cta" @click="router.push('/items')">探索物品</button>
      </template>
    </section>

    <!-- ===== 我的兑换（最近 3 条待核销，查看全部跳独立子页） ===== -->
    <section class="profile-card">
      <div class="card-head">
        <h2 class="card-title">我的兑换</h2>
        <div class="head-links">
          <!-- 商家入口：导航保持 8 项不动，入口放在这里（自己开店的邻居能直接找到） -->
          <button type="button" class="more-link" @click="router.push('/merchant/dashboard')">
            商家工作台
          </button>
          <button type="button" class="more-link" @click="router.push('/profile/redemptions')">查看全部</button>
        </div>
      </div>

      <p v-if="redemptionsLoading" class="mini-empty">加载中…</p>

      <template v-else-if="myRedemptions.length">
        <button
          v-for="record in myRedemptions"
          :key="record.id"
          type="button"
          class="mini-row"
          @click="router.push('/profile/redemptions')"
        >
          <span class="mini-thumb" aria-hidden="true">🎟️</span>
          <span class="mini-main">
            <span class="mini-title">{{ record.product_title || '未命名商品' }}</span>
            <span class="mini-time">
              {{ record.merchant_name || '商家已下线' }} · 核销码 {{ prettyCode(record.code) }}
            </span>
          </span>
          <!-- 兑换单是第三套状态枚举，必须用 rs-*（不能用物品/需求的 s-*） -->
          <span class="status-tag" :class="statusClass(record.status)">{{ record.status_label }}</span>
        </button>
      </template>

      <template v-else>
        <p class="mini-empty">还没有兑换记录，去积分商城看看</p>
        <button type="button" class="empty-cta" @click="router.push('/merchant')">去积分商城</button>
      </template>
    </section>

    <!-- ===== 我的回收单（最近 3 条，查看全部跳独立子页） ===== -->
    <section class="profile-card">
      <div class="card-head">
        <h2 class="card-title">我的回收单</h2>
        <button type="button" class="more-link" @click="router.push('/profile/recycle')">查看全部</button>
      </div>

      <p v-if="recyclesLoading" class="mini-empty">加载中…</p>

      <template v-else-if="myRecycles.length">
        <button
          v-for="record in myRecycles"
          :key="record.id"
          type="button"
          class="mini-row"
          @click="router.push('/profile/recycle')"
        >
          <span class="mini-thumb" aria-hidden="true">♻️</span>
          <span class="mini-main">
            <span class="mini-title">{{ record.item_title || '未命名物品' }}</span>
            <span class="mini-time">估价 +{{ record.points_reward }} 积分 · {{ record.pickup_method_label }}</span>
          </span>
          <!-- 回收单是第四套状态枚举，必须用 yc-*（不能用 s-*/os-*/rs-*） -->
          <span class="status-tag" :class="recycleStatusClass(record.status)">{{ record.status_label }}</span>
        </button>
      </template>

      <template v-else>
        <p class="mini-empty">还没有回收记录，发布物品时选「交给平台回收」即可立即得积分</p>
        <button type="button" class="empty-cta" @click="router.push('/items')">去发布闲置</button>
      </template>
    </section>

    <!-- ===== 我的私信（最近 3 条会话，查看全部跳私信页） =====
         私信入口原先在主导航，已移到这里（顶栏保留一个图标入口）。
         本卡片同时补上「私信在个人中心也有落点」的产品直觉。 -->
    <section class="profile-card">
      <div class="card-head">
        <h2 class="card-title">我的私信</h2>
        <button type="button" class="more-link" @click="router.push('/messages')">查看全部</button>
      </div>

      <p v-if="messagesLoading" class="mini-empty">加载中…</p>

      <template v-else-if="mySessions.length">
        <button
          v-for="session in mySessions"
          :key="session.other_user_id"
          type="button"
          class="mini-row"
          @click="router.push('/messages')"
        >
          <span class="mini-thumb" aria-hidden="true">{{ (session.other_nickname || '邻').charAt(0) }}</span>
          <span class="mini-main">
            <span class="mini-title">{{ session.other_nickname || '社区邻居' }}</span>
            <span class="mini-time">{{ session.content || '暂无消息' }}</span>
          </span>
          <!-- 未读数走独立 .msg-unread（红色系），不复用物品/兑换的状态标签色 -->
          <span v-if="session.unread_count > 0" class="status-tag msg-unread">
            {{ session.unread_count > 99 ? '99+' : session.unread_count }}
          </span>
          <span v-else class="msg-date">{{ formatShortDate(session.created_at) }}</span>
        </button>
      </template>

      <template v-else>
        <p class="mini-empty">还没有私信，从物品详情页联系邻居吧</p>
        <button type="button" class="empty-cta" @click="router.push('/items')">看看闲置</button>
      </template>
    </section>

    <!-- ===== 系统设置（3 列图标网格，点击跳转独立子页面） ===== -->
    <section class="profile-card">
      <h2 class="card-title">系统设置</h2>
      <div class="setting-grid">
        <button
          v-for="tile in SETTING_TILES"
          :key="tile.key"
          type="button"
          class="tile"
          @click="onTileClick(tile)"
        >
          <span class="tile-icon" aria-hidden="true">{{ tile.icon }}</span>
          <span class="tile-label">{{ tile.label }}</span>
        </button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getCarbonLogs, getCarbonSummary, getFavorites, getMyDemands, getMyItems, getProfile, updateProfile, uploadAvatar } from '../api/user'
import { getOrders } from '../api/order'
import { getMyRedemptions } from '../api/merchant'
import { getMyRecycles } from '../api/recycle'
import { getSessionList } from '../api/message'
import { useUserStore } from '../store/user'
import { useProfileStore } from '../store/profile'

const userStore = useUserStore()
const profileStore = useProfileStore()
const router = useRouter()

const profile = ref(null)
const avatarInput = ref(null)

/* ---------- 昵称编辑 ---------- */
const editingNickname = ref(false)
const nicknameDraft = ref('')
const savingNickname = ref(false)
const nicknameInput = ref(null)

const displayName = computed(() => profile.value?.nickname || userStore.user?.nickname || '居民')

/* ---------- 头像 ---------- */
const avatarSrc = computed(() => profile.value?.avatar || '')
// 头像兜底：昵称首字
const avatarText = computed(() => {
  const name = displayName.value || ''
  return name ? name.charAt(0).toUpperCase() : '居'
})

/* ---------- 加入天数 ---------- */
const joinDays = computed(() => {
  const createdAt = profile.value?.created_at
  if (!createdAt) return 0
  const start = new Date(createdAt).getTime()
  if (Number.isNaN(start)) return 0
  const diff = Date.now() - start
  return Math.max(0, Math.floor(diff / 86400000))
})

/* ---------- 等级规则：基于 points ---------- */
const LEVELS = [
  { min: 1000, code: 4, label: 'LV4' },
  { min: 501, code: 3, label: 'LV3' },
  { min: 101, code: 2, label: 'LV2' },
  { min: 0, code: 1, label: 'LV1' },
]
const level = computed(() => {
  const points = Number(profile.value?.points || 0)
  return LEVELS.find((item) => points >= item.min) || LEVELS[LEVELS.length - 1]
})

/* ---------- 碳积分展示与进度 ---------- */
// points 后端为整数，前台按整数展示
const pointsDisplay = computed(() => Math.max(0, Math.floor(Number(profile.value?.points || 0))))

const LEVEL_PROGRESS = {
  1: { from: 0, to: 101, next: 'LV2' },
  2: { from: 101, to: 501, next: 'LV3' },
  3: { from: 501, to: 1000, next: 'LV4' },
}

const progress = computed(() => {
  const points = pointsDisplay.value
  const segment = LEVEL_PROGRESS[level.value.code]
  if (!segment) {
    return { percent: 100, text: `已达最高等级 ${level.value.label}` }
  }
  const span = segment.to - segment.from
  const done = Math.min(Math.max(points - segment.from, 0), span)
  const remaining = Math.max(segment.to - points, 0)
  return {
    percent: span > 0 ? Math.round((done / span) * 100) : 0,
    text: `距离 ${segment.next} 还差 ${remaining} 分`,
  }
})

/* ---------- 系统设置网格 ---------- */
// 前 5 项跳转独立子页面；「退出登录」单独走二次确认弹窗
const SETTING_TILES = [
  { key: 'security', icon: '🔒', label: '账户安全', route: '/profile/account' },
  { key: 'location', icon: '📍', label: '位置管理', route: '/profile/location' },
  { key: 'notify', icon: '🔔', label: '通知设置', route: '/profile/notifications' },
  { key: 'accessibility', icon: '♿', label: '无障碍设置', route: '/profile/accessibility' },
  { key: 'feedback', icon: '💬', label: '意见反馈', route: '/profile/feedback' },
  { key: 'logout', icon: '🚪', label: '退出登录', route: null },
]

function onTileClick(tile) {
  if (tile.route) {
    router.push(tile.route)
    return
  }
  doLogout()
}

async function doLogout() {
  try {
    await ElMessageBox.confirm('确定要退出登录吗？', '退出登录', {
      confirmButtonText: '退出',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    // 用户取消
    return
  }
  userStore.logout()
  ElMessage.success('已退出登录')
  router.push('/login')
}

/* ---------- 助老模式快捷开关 ---------- */
const togglingElderly = ref(false)
const elderlyMode = computed(() => profileStore.elderlyMode)

async function toggleElderlyMode() {
  if (togglingElderly.value) return
  togglingElderly.value = true
  const next = !profileStore.elderlyMode
  try {
    await profileStore.saveProfile({ elderly_mode: next ? 1 : 0 })
    ElMessage.success(next ? '已开启助老模式' : '已关闭助老模式')
  } catch {
    ElMessage.error('切换失败，请稍后再试')
  } finally {
    togglingElderly.value = false
  }
}

/* ---------- 加载档案 ---------- */
async function loadProfile() {
  try {
    profile.value = await getProfile()
  } catch {
    // 加载失败保持页面可用，错误提示由请求拦截器统一处理
  }
}

/* ---------- 头像上传 ---------- */
function pickAvatar() {
  avatarInput.value?.click()
}

async function onAvatarChange(event) {
  const file = event.target.files?.[0]
  // 立即重置 input，保证同一文件可重复选择
  event.target.value = ''
  if (!file) return

  if (!['image/jpeg', 'image/png'].includes(file.type)) {
    ElMessage.warning('头像仅支持 jpg/png 格式')
    return
  }
  if (file.size > 2 * 1024 * 1024) {
    ElMessage.warning('头像大小不能超过 2MB')
    return
  }

  const formData = new FormData()
  formData.append('file', file)
  try {
    const data = await uploadAvatar(formData)
    if (profile.value) profile.value.avatar = data.avatar
    // 同步 store 与 localStorage，刷新前后一致
    if (userStore.user) {
      userStore.user.avatar = data.avatar
      localStorage.setItem('user', JSON.stringify(userStore.user))
    }
    ElMessage.success('头像已更新')
  } catch {
    ElMessage.error('头像上传失败，请稍后再试')
  }
}

/* ---------- 昵称编辑 ---------- */
async function startEditNickname() {
  nicknameDraft.value = displayName.value
  editingNickname.value = true
  await nextTick()
  nicknameInput.value?.focus()
}

function cancelNickname() {
  editingNickname.value = false
  nicknameDraft.value = ''
}

async function saveNickname() {
  const name = nicknameDraft.value.trim()
  if (!name) {
    ElMessage.warning('昵称不能为空')
    return
  }
  if (name.length > 20) {
    ElMessage.warning('昵称不能超过 20 个字')
    return
  }
  savingNickname.value = true
  try {
    const data = await updateProfile({ nickname: name })
    profile.value = data
    if (userStore.user) {
      userStore.user.nickname = data.nickname
      localStorage.setItem('user', JSON.stringify(userStore.user))
    }
    editingNickname.value = false
    ElMessage.success('昵称已更新')
  } catch {
    ElMessage.error('昵称保存失败，请稍后再试')
  } finally {
    savingNickname.value = false
  }
}

/* ============================================================
   第二区：我的物品（主页只展示最近 3 条）
   ============================================================ */
// 主页概览固定展示 3 条，更多走 /profile/items
const PREVIEW_SIZE = 3

// null 表示不筛选，与后端 status 可选参数对应
const ITEM_TABS = [
  { key: null, label: '全部' },
  { key: 1, label: '在售' },
  { key: 4, label: '审核中' },
  { key: 2, label: '已下架' },
]

const activeItemTab = ref(null)
const myItems = ref([])
const itemsLoading = ref(false)

const itemsEmptyText = computed(() =>
  activeItemTab.value === null ? '你还没有发布过物品' : '该状态下暂无物品',
)

async function loadMyItems() {
  itemsLoading.value = true
  try {
    const params = { page: 1, size: PREVIEW_SIZE }
    if (activeItemTab.value !== null) params.status = activeItemTab.value
    const data = await getMyItems(params)
    myItems.value = data?.list || []
  } catch {
    // 错误提示由请求拦截器统一处理
    myItems.value = []
  } finally {
    itemsLoading.value = false
  }
}

function switchItemTab(key) {
  if (activeItemTab.value === key) return
  activeItemTab.value = key
  loadMyItems()
}

/* ============================================================
   我的收藏（主页只展示最近 3 条，更多走 /profile/favorites）
   ============================================================ */
const myFavorites = ref([])
const favoritesLoading = ref(false)

async function loadFavorites() {
  favoritesLoading.value = true
  try {
    const data = await getFavorites({ page: 1, size: PREVIEW_SIZE })
    myFavorites.value = data?.list || []
  } catch {
    // 错误提示由请求拦截器统一处理
    myFavorites.value = []
  } finally {
    favoritesLoading.value = false
  }
}

function toFavoriteItem(fav) {
  // 物品已被删除（后端 LEFT JOIN 取不到 item）时没有可跳转详情
  if (!fav.id) return
  router.push(`/items/${fav.id}`)
}

/* ============================================================
   我想要的（主页只展示最近 3 条，更多走 /profile/demands）
   ============================================================ */
const myDemands = ref([])
const demandsLoading = ref(false)

async function loadDemands() {
  demandsLoading.value = true
  try {
    const data = await getMyDemands({ page: 1, size: PREVIEW_SIZE })
    myDemands.value = data?.list || []
  } catch {
    // 错误提示由请求拦截器统一处理
    myDemands.value = []
  } finally {
    demandsLoading.value = false
  }
}

/* ============================================================
   我的交换（主页只展示最近 3 条，更多走 /profile/exchanges）
   数据源：GET /orders?role=all —— 我会以买家或卖家身份参与，
   后端按「我在该单里的实际身份」返回 other_nickname（对方昵称）。
   ============================================================ */
const myOrders = ref([])
const ordersLoading = ref(false)

async function loadOrders() {
  ordersLoading.value = true
  try {
    const data = await getOrders({ role: 'all', page: 1, size: PREVIEW_SIZE })
    myOrders.value = data?.list || []
  } catch {
    // 错误提示由请求拦截器统一处理
    myOrders.value = []
  } finally {
    ordersLoading.value = false
  }
}

/* ============================================================
   我的兑换（主页只展示最近 3 条**待核销**，更多走 /profile/redemptions）
   只取 status=1：待核销是唯一需要用户行动的状态，其余状态没有催促价值。
   ============================================================ */
const myRedemptions = ref([])
const redemptionsLoading = ref(false)

async function loadRedemptions() {
  redemptionsLoading.value = true
  try {
    const data = await getMyRedemptions({ status: 1, page: 1, size: PREVIEW_SIZE })
    myRedemptions.value = data?.list || []
  } catch {
    // 错误提示由请求拦截器统一处理
    myRedemptions.value = []
  } finally {
    redemptionsLoading.value = false
  }
}

/* 兑换单状态类名：**第三套 rs-***（语义命名）。
   本文件已有 s-*（物品/需求）与 os-*（交换单），数值含义都不同：
   兑换单 2 是「已核销」（绿），而 s-2 是「已下架」（灰）、os-2 是「交换中」（蓝）；
   兑换单 3 是「已过期」（灰），而 s-3 是「审核未通过」（红）。
   类名定义见本文件 <style scoped> 的 .rs-* 与 RedemptionsView.vue。 */
const REDEMPTION_STATUS_CLASS = {
  1: 'rs-pending',
  2: 'rs-redeemed',
  3: 'rs-expired',
  4: 'rs-cancelled',
}

function statusClass(status) {
  return REDEMPTION_STATUS_CLASS[Number(status)] || 'rs-cancelled'
}

// 6 位核销码按 3+3 分组展示（字符串处理，保住前导 0）
function prettyCode(code) {
  const s = String(code ?? '').replace(/\s+/g, '')
  if (!s) return '——'
  if (s.length === 6) return `${s.slice(0, 3)} ${s.slice(3)}`
  const mid = Math.ceil(s.length / 2)
  return `${s.slice(0, mid)} ${s.slice(mid)}`
}

/* ============================================================
   我的回收单（主页只展示最近 3 条，更多走 /profile/recycle）
   与 loadRedemptions 同套路：单路失败不影响其它卡片。
   ============================================================ */
const myRecycles = ref([])
const recyclesLoading = ref(false)

async function loadRecycles() {
  recyclesLoading.value = true
  try {
    const data = await getMyRecycles({ page: 1, size: PREVIEW_SIZE })
    myRecycles.value = data?.list || []
  } catch {
    // 错误提示由请求拦截器统一处理
    myRecycles.value = []
  } finally {
    recyclesLoading.value = false
  }
}

/* 回收单状态类名：**第四套 yc-***（语义命名）。
   本文件已有 s-*（物品/需求）、os-*（交换单）、rs-*（兑换单）三套，
   回收单 2 是「已入库」（蓝），与 s-2「已下架」/ os-2「交换中」/ rs-2「已核销」
   语义都不同，复用必然语义反向，故新开一套（样式见本文件 .yc-*）。 */
const RECYCLE_STATUS_CLASS = {
  1: 'yc-pending',
  2: 'yc-stock',
  3: 'yc-sold',
  4: 'yc-cancelled',
}

function recycleStatusClass(status) {
  return RECYCLE_STATUS_CLASS[Number(status)] || 'yc-cancelled'
}

/* ============================================================
   我的私信（主页只展示最近 3 条会话，更多走 /messages）
   会话列表接口已带 unread_count，这里只需展示，不再额外请求。
   ============================================================ */
const mySessions = ref([])
const messagesLoading = ref(false)

async function loadMessages() {
  messagesLoading.value = true
  try {
    // skipErrorToast：私信卡片是附属信息，接口抖动时不该弹错误打扰用户
    const data = await getSessionList({ skipErrorToast: true })
    const list = Array.isArray(data) ? data : data?.list || []
    mySessions.value = list.slice(0, PREVIEW_SIZE)
  } catch {
    mySessions.value = []
  } finally {
    messagesLoading.value = false
  }
}

/* ============================================================
   第四区：碳积分概览（汇总 / 进度 / 最近 3 条明细）
   等级与进度由后端 /user/carbon/summary 返回，
   阈值定义在 app/core/constants.py，与 Hero 卡的前端计算同值。
   ============================================================ */
const carbonSummary = ref({
  total_points: 0,
  carbon_total: 0,
  exchange_count: 0,
  level: 1,
  level_label: 'LV1',
  next_level: null,
  next_level_gap: 0,
  progress_percent: 0,
})
const recentLogs = ref([])

// 碳减排量保留 1 位小数，避免浮点长尾
const carbonDisplay = computed(() => Number(carbonSummary.value.carbon_total || 0).toFixed(1))

const carbonProgressText = computed(() => {
  const item = carbonSummary.value
  if (!item.next_level) return `已达最高等级 ${item.level_label}`
  return `距离 ${item.next_level} 还差 ${item.next_level_gap} 分`
})

async function loadCarbonOverview() {
  try {
    const [summary, logs] = await Promise.all([
      getCarbonSummary(),
      getCarbonLogs({ limit: PREVIEW_SIZE }),
    ])
    if (summary) carbonSummary.value = summary
    recentLogs.value = logs?.list || []
  } catch {
    // 错误提示由请求拦截器统一处理
  }
}

/* 概览卡片里的时间统一按日期展示，避免长文本撑破行 */
function formatShortDate(value) {
  if (!value) return '时间未知'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间未知'
  return date.toLocaleDateString('zh-CN')
}

// 登录态就绪后加载档案（用户信息可能晚于本组件挂载）
watch(() => profileStore.userId, (id) => {
  if (id) {
    loadProfile()
    loadMyItems()
    loadFavorites()
    loadDemands()
    loadOrders()
    loadRedemptions()
    loadRecycles()
    loadMessages()
    loadCarbonOverview()
  }
}, { immediate: true })

// 未登录不应到达此页（路由守卫也会拦截），双保险
if (!userStore.isLoggedIn) {
  ElMessage.warning('请先登录后再查看个人中心')
  router.replace({ path: '/login', query: { redirect: '/profile' } })
}

onMounted(() => {
  loadProfile()
  loadMyItems()
  loadFavorites()
  loadDemands()
  loadOrders()
  loadRedemptions()
  loadRecycles()
  loadMessages()
  loadCarbonOverview()
})
</script>

<style scoped>
/* ============================================================
   局部色板
   原则：色值优先引用 global.css 的全局令牌；全局没有对应令牌时，
   才在 .profile-page 上定义局部变量，且值从全局色系派生（不另造新色）。
   ============================================================ */
.profile-page {
  --pc-green: var(--green-primary); /* 品牌绿：复用全局主色 */
  /* 辅助绿：全局无对应令牌，用主色提亮派生（替代设计稿的浅绿） */
  --pc-green-alt: color-mix(in srgb, var(--green-primary) 80%, #ffffff);
  /* 文字：统一引用全局令牌，高对比度主题可自动改写 */
  --pc-text: var(--text-primary);
  --pc-text-sub: var(--text-secondary);
  /* 中性色：全局无令牌，按设计规范取值 */
  --pc-bg: #f7f8f7;
  --pc-card: #ffffff;
  --pc-border: #e5e7eb;
  --pc-track: #e5e7eb;
  /* 阴影：按设计规范的轻量两档，不使用全局重阴影 */
  --pc-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  --pc-shadow-hover: 0 4px 16px rgba(0, 0, 0, 0.08);
}

.profile-page {
  max-width: 820px;
}

/* ---------- 卡片基础：样式自持，不再复用 .glass-card ---------- */
.profile-card {
  margin-top: 20px;
  padding: 20px;
  background: var(--pc-card);
  border: 1px solid var(--pc-border);
  border-radius: 16px;
  box-shadow: var(--pc-shadow);
  transition: box-shadow 0.2s ease;
}

.profile-card:hover {
  box-shadow: var(--pc-shadow-hover);
}

/* 卡片标题：16px 粗体 + 左侧 4px 绿色竖线 */
.card-title {
  position: relative;
  margin-bottom: 20px;
  padding-left: 12px;
  font-size: 16px;
  font-weight: 700;
  color: var(--pc-text);
}

.card-title::before {
  content: "";
  position: absolute;
  left: 0;
  top: 50%;
  width: 4px;
  height: 16px;
  border-radius: 2px;
  background: var(--pc-green);
  transform: translateY(-50%);
}

/* ============================================================
   第一区：Hero 用户信息卡
   ============================================================ */
.hero-card {
  position: relative;
  padding: 0;
  /* 仅 Hero 卡片裁切：让渐变带的圆角与卡片的 16px 圆角严丝合缝。
     其他卡片不裁切，避免网格 tile 的 hover 阴影被切掉。 */
  overflow: hidden;
}

/* 顶部渐变带 */
.hero-band {
  height: 100px;
  border-radius: 16px 16px 0 0;
  background: linear-gradient(135deg, var(--pc-green) 0%, var(--pc-green-alt) 100%);
}

/* 助老模式快捷开关：Hero 卡右下角小图标按钮 */
.elderly-quick-toggle {
  position: absolute;
  right: 14px;
  bottom: 14px;
  z-index: 2;
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  padding: 0;
  font-size: 18px;
  line-height: 1;
  background: var(--pc-bg);
  border: 1px solid var(--pc-border);
  border-radius: 50%;
  cursor: pointer;
  transition: all 0.2s ease;
}

.elderly-quick-toggle:hover {
  transform: translateY(-2px);
  border-color: var(--pc-green);
  box-shadow: var(--pc-shadow-hover);
}

.elderly-quick-toggle.active {
  border-color: var(--pc-green);
  background: color-mix(in srgb, var(--pc-green) 14%, var(--pc-card));
}

.elderly-quick-toggle:focus-visible {
  outline: 3px solid var(--pc-green);
  outline-offset: 2px;
}

.elderly-quick-toggle:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.hero-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0 20px 20px;
}

/* 头像：96px，白色 4px 边框，上浮 48px 悬浮在渐变带下沿 */
.avatar-wrap {
  position: relative;
  width: 96px;
  height: 96px;
  flex-shrink: 0;
  margin-top: -48px;
  border: 4px solid var(--pc-card);
  border-radius: 50%;
  overflow: hidden;
  background: var(--pc-card);
  cursor: pointer;
  outline: none;
}

.avatar-wrap:focus-visible {
  outline: 3px solid var(--pc-green);
  outline-offset: 2px;
}

.avatar-img,
.avatar-circle {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  object-fit: cover;
  display: grid;
  place-items: center;
}

.avatar-circle {
  font-size: 34px;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, var(--pc-green), var(--pc-green-alt));
}

/* 悬浮遮罩：提示可点击更换 */
.avatar-mask {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  font-size: 13px;
  color: #fff;
  background: rgba(0, 0, 0, 0.45);
  opacity: 0;
  transition: opacity 0.2s ease;
}

.avatar-wrap:hover .avatar-mask,
.avatar-wrap:focus-visible .avatar-mask {
  opacity: 1;
}

.avatar-input {
  display: none;
}

.hero-info {
  width: 100%;
  min-width: 0;
}

/* 昵称行：昵称 + 等级徽章 + 灰色文字「编辑」按钮 */
.nickname-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 12px;
}

.nickname-text {
  font-size: 22px;
  font-weight: 700;
  line-height: 1.3;
  color: var(--pc-text);
}

.nickname-input {
  max-width: 220px;
}

/* 编辑按钮：灰色文字按钮，默认隐藏，hover / 聚焦时显示 */
.nickname-row .edit-btn {
  flex-shrink: 0;
  font-size: 13px;
  color: var(--pc-text-sub);
  opacity: 0;
  transition: opacity 0.2s ease;
}

.nickname-row:hover .edit-btn,
.nickname-row:focus-within .edit-btn {
  opacity: 1;
}

/* 触屏设备没有 hover，直接常显，避免按钮不可发现 */
@media (hover: none) {
  .nickname-row .edit-btn {
    opacity: 1;
  }
}

/* 所在社区：昵称下方小字 */
.community-line {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--pc-text-sub);
  text-align: center;
}

/* 数据展示区：两列 */
.stat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  width: 100%;
  margin-top: 20px;
}

.stat-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.2;
  color: var(--pc-green);
}

.stat-unit {
  margin-left: 2px;
  font-size: 13px;
  font-weight: 500;
  color: var(--pc-text-sub);
}

.stat-label {
  font-size: 13px;
  color: var(--pc-text-sub);
}

/* 碳积分进度条 */
.progress-wrap {
  width: 100%;
  margin-top: 20px;
}

.progress-track {
  height: 6px;
  border-radius: 999px;
  background: var(--pc-track);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--pc-green), var(--pc-green-alt));
  transition: width 0.3s ease;
}

.progress-text {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--pc-text-sub);
  text-align: center;
}

/* 等级徽章：胶囊形；LV3 使用品牌绿，LV4 用全局暖色令牌派生（不另造新色） */
.level-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.4;
  color: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
}

.level-1 {
  background: #8a8a8a;
}

.level-2 {
  background: #3b82f6;
}

.level-3 {
  background: var(--pc-green);
}

.level-4 {
  background: linear-gradient(135deg, var(--peach), color-mix(in srgb, var(--peach) 70%, #ffffff));
}

/* ============================================================
   第二 / 三 / 四区：概览卡片
   （Hero 卡与设置网格的样式保持原样，此处只新增概览卡片所需类）
   ============================================================ */
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

/* 复用 .card-title，但头部行内不再需要下外边距 */
.card-head .card-title {
  margin-bottom: 0;
}

/* 卡片头右侧的一组文字按钮（如「商家工作台 / 查看全部」） */
.head-links {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

/* 右上角「查看全部 / 查看明细」文字按钮 */
.more-link {
  flex-shrink: 0;
  padding: 4px 8px;
  font: inherit;
  font-size: 13px;
  color: var(--pc-text-sub);
  background: none;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: color 0.2s ease, background 0.2s ease;
}

.more-link:hover {
  color: var(--pc-green);
  background: var(--pc-bg);
}

.more-link:focus-visible {
  outline: 3px solid var(--pc-green);
  outline-offset: 2px;
}

/* 概览内的小 Tab：胶囊形，选中态用品牌绿 */
.mini-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}

.mini-tab {
  padding: 6px 14px;
  font: inherit;
  font-size: 13px;
  color: var(--pc-text-sub);
  background: var(--pc-bg);
  border: 1px solid var(--pc-border);
  border-radius: 999px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.mini-tab:hover {
  color: var(--pc-green);
  border-color: var(--pc-green);
}

.mini-tab.active {
  color: #fff;
  background: var(--pc-green);
  border-color: var(--pc-green);
}

.mini-tab:focus-visible {
  outline: 3px solid var(--pc-green);
  outline-offset: 2px;
}

/* 概览行：列表项 48px 高 + hover 换底色 */
.mini-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-height: 48px;
  padding: 10px 12px;
  margin: 0 -12px;
  font: inherit;
  text-align: left;
  color: inherit;
  background: none;
  border: none;
  border-top: 1px solid var(--pc-border);
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s ease;
}

/* 首行紧跟标题，不再画分隔线 */
.mini-tabs + .mini-row,
.mini-sub + .mini-row {
  border-top: none;
}

.mini-row:hover {
  background: var(--pc-bg);
}

.mini-row:focus-visible {
  outline: 3px solid var(--pc-green);
  outline-offset: 2px;
}

/* 积分明细行不可点击，去掉指针样式 */
.mini-row.static {
  cursor: default;
}

.mini-thumb {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  overflow: hidden;
  font-size: 20px;
  background: var(--pc-bg);
  border: 1px solid var(--pc-border);
  border-radius: 10px;
}

.mini-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.mini-main {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.mini-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--pc-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mini-time {
  margin-top: 2px;
  font-size: 12px;
  color: var(--pc-text-sub);
}

.mini-sub {
  margin: 20px 0 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--pc-text);
}

.mini-empty {
  padding: 12px 0;
  margin: 0;
  font-size: 14px;
  color: var(--pc-text-sub);
}

/* 空态跳转入口：描边胶囊按钮。
   颜色全部走局部色板令牌（--pc-text / --pc-border / --pc-card / --pc-green），
   因此高对比度主题下会自动变成「黑底 + 白描边 + 白字」，无需额外覆盖规则。 */
.empty-cta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 40px;
  padding: 8px 20px;
  margin-top: 4px;
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  color: var(--pc-text);
  background: var(--pc-card);
  border: 1px solid var(--pc-border);
  border-radius: 999px;
  cursor: pointer;
  transition: color 0.2s ease, border-color 0.2s ease, background 0.2s ease;
}

.empty-cta:hover {
  color: var(--pc-green);
  border-color: var(--pc-green);
  background: var(--pc-bg);
}

.empty-cta:focus-visible {
  outline: 3px solid var(--pc-green);
  outline-offset: 2px;
}

/* 碳积分三个数字：三列布局（Hero 的两列 .stat-grid 保持不变） */
.mini-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

/* 积分变动值：获得用品牌绿，消耗用警示红 */
.log-delta {
  flex-shrink: 0;
  font-size: 16px;
  font-weight: 700;
}

.log-delta.plus {
  color: var(--pc-green);
}

.log-delta.minus {
  color: #dc2626;
}

/* 物品状态标签 */
.status-tag {
  flex-shrink: 0;
  padding: 2px 10px;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  border-radius: 999px;
}

/* 收藏列表可能含已被删除的物品（后端 status=0），用中性灰兜底 */
.s-0 {
  background: #8a8a8a;
}

.s-1 {
  background: var(--pc-green);
}

.s-2 {
  background: #8a8a8a;
}

.s-3 {
  background: #dc2626;
}

.s-4 {
  background: #3b82f6;
}

/* 订单状态标签：与物品/需求状态（s-*）刻意分开命名。
   两套枚举的数值含义不同——订单 3 是「已完成」，而 s-3 是「审核未通过（红）」，
   若复用 s-* 会把「已完成」显示成红色、「已取消」显示成蓝色，语义完全相反。 */
.os-1 {
  background: #f59e0b; /* 待确认 */
}

.os-2 {
  background: #3b82f6; /* 交换中 */
}

.os-3 {
  background: #16a34a; /* 已完成 */
}

.os-4 {
  background: #8a8a8a; /* 已取消 */
}

.os-5 {
  background: #7c3aed; /* 争议中 */
}

/* ---------- 兑换单状态标签：**第三套 rs-***（语义命名） ----------
   枚举：1 待核销 / 2 已核销 / 3 已过期 / 4 已取消。
   与 s-*（物品/需求）、os-*（交换单）刻意分开：三套枚举数值含义都不同，
   复用会把「已核销」显示成灰色、「已过期」显示成红色，语义完全反向。
   类名与 RedemptionsView.vue 保持一致。 */
.rs-pending {
  background: #f59e0b; /* 待核销 */
}

.rs-redeemed {
  background: #16a34a; /* 已核销 */
}

.rs-expired {
  background: #8a8a8a; /* 已过期（积分已退还，不是错误态） */
}

.rs-cancelled {
  background: #6b7280; /* 已取消 */
}

/* ---------- 回收单状态标签：**第四套 yc-***（语义命名） ----------
   枚举：1 待取件 / 2 已入库 / 3 已售出 / 4 已取消。
   与 s-*、os-*、rs-* 三套刻意分开：回收单 2 是「已入库」（蓝），
   复用任何一套都会语义反向。类名与 RecycleView.vue 保持一致。 */
.yc-pending {
  background: #f59e0b; /* 待取件 */
}

.yc-stock {
  background: #2563eb; /* 已入库（平台持有中） */
}

.yc-sold {
  background: #16a34a; /* 已售出 */
}

.yc-cancelled {
  background: #8a8a8a; /* 已取消（积分已退回，不是错误态） */
}

/* ---------- 私信未读数：独立红色系 ----------
   与物品 / 交换 / 兑换 / 回收四套状态枚举都无关（它表示「有几条没看」，
   不是业务状态），因此不复用既有四套状态类名，单开一个类。 */
.msg-unread {
  background: #e53935;
}

/* 无未读时右侧显示时间，视觉权重比未读数字轻 */
.msg-date {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--pc-text-sub);
}

/* ============================================================
   系统设置：3 列图标网格
   ============================================================ */
.setting-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.tile {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 20px;
  font: inherit;
  color: var(--pc-text);
  background: var(--pc-card);
  border: 1px solid var(--pc-border);
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.tile:hover {
  transform: translateY(-2px);
  box-shadow: var(--pc-shadow-hover);
  border-color: var(--pc-green);
}

.tile:focus-visible {
  outline: 3px solid var(--pc-green);
  outline-offset: 2px;
}

.tile-icon {
  font-size: 28px;
  line-height: 1;
  color: var(--pc-green);
}

.tile-label {
  font-size: 14px;
  color: var(--pc-text);
}

/* ============================================================
   响应式
   ============================================================ */
/* 平板：设置网格 2 列 */
@media (max-width: 768px) {
  .setting-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* 手机：设置网格 2 列，卡片间距缩小到 12px */
@media (max-width: 480px) {
  .profile-card {
    margin-top: 12px;
    padding: 16px;
  }

  .hero-card {
    padding: 0;
  }

  .setting-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;
  }

  /* 三列汇总数字在窄屏下压缩间距，不折行 */
  .mini-stats {
    gap: 8px;
  }

  .mini-thumb {
    width: 36px;
    height: 36px;
    font-size: 18px;
  }
}
</style>

<!-- ============================================================
     非 scoped 样式块
     必须非 scoped：需要命中 html 根级选择器（html:has / html.mode-elderly /
     html.theme-high-contrast），scoped 的属性选择器无法命中根元素。
     ============================================================ -->
<style>
/* ---------- 页面底色：仅个人中心生效，不影响其他页面 ----------
   :not(.theme-high-contrast) 排除高对比度主题，让 global.css 的纯黑底生效 */
html:has(.profile-page):not(.theme-high-contrast) body {
  background: #f7f8f7;
}

/* ============================================================
   高对比度主题：重定义局部色板，保证个人中心仍可读
   --pc-green / --pc-text / --pc-text-sub 均引用全局令牌，
   html.theme-high-contrast 已自动改写这些令牌，无需重复声明。
   ============================================================ */
html.theme-high-contrast .profile-page {
  --pc-card: #000000;
  --pc-bg: #000000;
  --pc-border: #ffffff;
  --pc-track: rgba(255, 255, 255, 0.35);
  --pc-shadow: none;
  --pc-shadow-hover: none;
}

/* 渐变带在高对比度下改为纯黑 + 白描边，避免浅绿底上的白边框失效 */
html.theme-high-contrast .profile-page .hero-band {
  background: #000000;
  border-bottom: 1px solid #ffffff;
}

html.theme-high-contrast .profile-page .avatar-wrap {
  border-color: #ffffff;
}

/* 徽章改为浅底黑字，保证在纯黑背景上的对比度 */
html.theme-high-contrast .profile-page .level-badge {
  color: #000000;
  box-shadow: none;
}

html.theme-high-contrast .profile-page .level-1 {
  background: #e5e5e5;
}

html.theme-high-contrast .profile-page .level-2 {
  background: #93c5fd;
}

html.theme-high-contrast .profile-page .level-3 {
  background: #4ade80;
}

html.theme-high-contrast .profile-page .level-4 {
  background: #fbbf24;
}

/* 概览卡片：状态标签与积分变动值同样改为浅底/浅色，保证纯黑背景上可读 */
html.theme-high-contrast .profile-page .status-tag {
  color: #000000;
}

html.theme-high-contrast .profile-page .s-1 {
  background: #4ade80;
}

html.theme-high-contrast .profile-page .s-2 {
  background: #e5e5e5;
}

html.theme-high-contrast .profile-page .s-0 {
  background: #e5e5e5;
}

html.theme-high-contrast .profile-page .s-3 {
  background: #fca5a5;
}

html.theme-high-contrast .profile-page .s-4 {
  background: #93c5fd;
}

/* 订单状态标签在高对比度主题下改为浅底 + 黑字，保证纯黑背景上可读 */
html.theme-high-contrast .profile-page .os-1 {
  background: #fcd34d;
}

html.theme-high-contrast .profile-page .os-2 {
  background: #93c5fd;
}

html.theme-high-contrast .profile-page .os-3 {
  background: #4ade80;
}

html.theme-high-contrast .profile-page .os-4 {
  background: #e5e5e5;
}

html.theme-high-contrast .profile-page .os-5 {
  background: #c4b5fd;
}

/* 兑换单状态标签（rs-*）：同样改为浅底 + 黑字 */
html.theme-high-contrast .profile-page .rs-pending {
  background: #fcd34d;
}

html.theme-high-contrast .profile-page .rs-redeemed {
  background: #4ade80;
}

html.theme-high-contrast .profile-page .rs-expired,
html.theme-high-contrast .profile-page .rs-cancelled {
  background: #e5e5e5;
}

/* 回收单状态标签（yc-*）：同样改为浅底 + 黑字 */
html.theme-high-contrast .profile-page .yc-pending {
  background: #fcd34d;
}

html.theme-high-contrast .profile-page .yc-stock {
  background: #93c5fd;
}

html.theme-high-contrast .profile-page .yc-sold {
  background: #4ade80;
}

html.theme-high-contrast .profile-page .yc-cancelled {
  background: #e5e5e5;
}

/* 私信未读数：高对比度下翻转为浅红底 + 黑字 */
html.theme-high-contrast .profile-page .msg-unread {
  background: #fca5a5;
  color: #000000;
}

html.theme-high-contrast .profile-page .log-delta.minus {
  color: #fca5a5;
}

/* ============================================================
   助老模式：改写（非追加）原有规则，避免两套字号规则打架
   ============================================================ */
/* 卡片圆角 16px -> 20px，间距 20px -> 24px */
html.mode-elderly .profile-page .profile-card {
  margin-top: 24px;
  border-radius: 20px;
}

html.mode-elderly .profile-page .hero-band {
  border-radius: 20px 20px 0 0;
}

/* 标题 */
html.mode-elderly .profile-page .card-title {
  font-size: 22px;
}

/* 数字 24px -> 32px */
html.mode-elderly .profile-page .stat-value {
  font-size: 32px;
}

html.mode-elderly .profile-page .nickname-text {
  font-size: 30px;
}

html.mode-elderly .profile-page .avatar-circle {
  font-size: 40px;
}

/* 次要文字同步放大 */
html.mode-elderly .profile-page .stat-label,
html.mode-elderly .profile-page .stat-unit,
html.mode-elderly .profile-page .community-line,
html.mode-elderly .profile-page .progress-text {
  font-size: 18px;
}

html.mode-elderly .profile-page .level-badge {
  font-size: 18px;
  padding: 6px 16px;
}

/* 图标 28px -> 36px，标题 14px -> 20px */
html.mode-elderly .profile-page .tile-icon {
  font-size: 36px;
}

html.mode-elderly .profile-page .tile-label {
  font-size: 20px;
}

html.mode-elderly .profile-page .setting-grid {
  gap: 20px;
}

/* 头像同步放大，保持「上浮半个身位」的视觉关系 */
html.mode-elderly .profile-page .avatar-wrap {
  width: 112px;
  height: 112px;
  margin-top: -56px;
}

/* 助老模式下「编辑」按钮不再依赖 hover */
html.mode-elderly .profile-page .nickname-row .edit-btn {
  opacity: 1;
}

/* 所有可点击元素最小高度 60px */
html.mode-elderly .profile-page .el-button,
html.mode-elderly .profile-page .avatar-wrap,
html.mode-elderly .profile-page .tile,
html.mode-elderly .profile-page .elderly-quick-toggle {
  min-height: 60px;
}

/* 助老模式下快捷开关放大，便于点按 */
html.mode-elderly .profile-page .elderly-quick-toggle {
  width: 60px;
  height: 60px;
  font-size: 26px;
}

/* ---------- 第二 / 三 / 四区概览卡片（助老模式放大） ---------- */
html.mode-elderly .profile-page .mini-tab,
html.mode-elderly .profile-page .more-link,
html.mode-elderly .profile-page .mini-time,
html.mode-elderly .profile-page .status-tag,
html.mode-elderly .profile-page .mini-empty {
  font-size: 18px;
}

html.mode-elderly .profile-page .mini-title,
html.mode-elderly .profile-page .mini-sub {
  font-size: 20px;
}

html.mode-elderly .profile-page .log-delta {
  font-size: 22px;
}

/* 概览里的可点击元素同样保证 60px 最小高度 */
html.mode-elderly .profile-page .mini-row,
html.mode-elderly .profile-page .mini-tab,
html.mode-elderly .profile-page .more-link {
  min-height: 60px;
}

html.mode-elderly .profile-page .mini-tab,
html.mode-elderly .profile-page .more-link {
  display: inline-flex;
  align-items: center;
}

html.mode-elderly .profile-page .mini-thumb {
  width: 56px;
  height: 56px;
  font-size: 28px;
}

/* 第三区空态跳转入口：助老模式下同样满足 60px 最小点击目标，并放大字号 */
html.mode-elderly .profile-page .empty-cta {
  min-height: 60px;
  padding: 12px 28px;
  font-size: 20px;
}
</style>
