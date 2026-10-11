<template>
  <section class="page message-page">
    <div class="page-head">
      <div class="eyebrow">{{ t('message.eyebrow') }}</div>
      <h1 class="page-title">{{ t('message.titleLead') }}<span class="gradient-text">{{ t('message.titleHighlight') }}</span></h1>
      <p class="muted page-sub">{{ t('message.subtitle') }}</p>
    </div>

    <div class="chat-shell">
      <!-- 左侧：会话列表 -->
      <aside class="session-panel">
        <div class="panel-head">{{ t('message.sessionList') }}</div>
        <div v-if="sessions.length" class="session-list">
          <button
            v-for="s in sessions"
            :key="s.other_user_id"
            class="session-item"
            :class="{ active: s.other_user_id === activeUserId }"
            @click="openSession(s)"
          >
            <span class="avatar">{{ (s.other_nickname || t('message.neighborShort')).charAt(0) }}</span>
            <span class="session-main">
              <span class="session-name">{{ s.other_nickname || t('message.defaultNeighbor') }}</span>
              <span class="session-last">{{ s.content }}</span>
            </span>
            <span class="session-side">
              <span class="session-time">{{ formatTime(s.created_at) }}</span>
              <span
                v-if="s.unread_count > 0 && s.other_user_id !== activeUserId"
                class="unread-badge"
              >{{ s.unread_count }}</span>
            </span>
          </button>
        </div>
        <div v-else class="session-empty muted">{{ t('message.emptySessions') }}</div>
      </aside>

      <!-- 右侧：聊天窗口 -->
      <div class="chat-panel">
        <template v-if="activeUserId">
          <div class="panel-head chat-head">
            <span class="avatar sm">{{ (activeName || t('message.neighborShort')).charAt(0) }}</span>
            <span class="chat-title">{{ activeName || t('message.defaultNeighbor') }}</span>
            <span v-if="currentItemId" class="chat-item-tag">{{ t('message.relatedItem', { id: currentItemId }) }}</span>
          </div>

          <div ref="chatBox" class="chat-box">
            <div
              v-for="m in chatMessages"
              :key="m.id"
              class="msg-row"
              :class="{ mine: m.sender_id === myId }"
            >
              <div class="bubble">
                <p class="msg-content">{{ m.content }}</p>
                <span class="msg-time">{{ formatTime(m.created_at) }}</span>
              </div>
            </div>
          </div>

          <div class="chat-input">
            <el-input
              v-model="draft"
              type="textarea"
              :rows="2"
              resize="none"
              :placeholder="t('message.inputPlaceholder')"
              @keydown.enter.exact.prevent="send"
            />
            <el-button type="primary" :loading="sending" @click="send">{{ t('message.send') }}</el-button>
          </div>
        </template>

        <div v-else class="chat-empty">
          <span class="empty-icon">💬</span>
          <p>{{ t('message.selectTip') }}</p>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getChatHistory, getSessionList, markRead, sendMessage } from '../api/message'
import { useUserStore } from '../store/user'
import { useI18n } from '../i18n'

const { t } = useI18n()
const route = useRoute()
const userStore = useUserStore()
const myId = computed(() => userStore.user?.id)

const sessions = ref([])
const activeUserId = ref(null)
const activeName = ref('')
const currentItemId = ref(null)
const chatMessages = ref([])
const draft = ref('')
const sending = ref(false)
const chatBox = ref(null)

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n) => String(n).padStart(2, '0')
  const hhmm = `${pad(d.getHours())}:${pad(d.getMinutes())}`
  const isToday = d.toDateString() === new Date().toDateString()
  return isToday ? hhmm : `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${hhmm}`
}

function scrollBottom() {
  nextTick(() => {
    const el = chatBox.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

async function loadSessions() {
  try {
    sessions.value = await getSessionList()
  } catch {
    // 401/501 已由 axios 拦截器统一处理
  }
}

async function loadChat() {
  try {
    chatMessages.value = await getChatHistory(activeUserId.value, currentItemId.value ?? undefined)
    // 把对方发来的未读消息标记为已读，并同步左侧徽标
    const unread = chatMessages.value.filter((m) => m.receiver_id === myId.value && !m.is_read)
    if (unread.length) {
      await Promise.allSettled(unread.map((m) => markRead(m.id)))
      const s = sessions.value.find((x) => x.other_user_id === activeUserId.value)
      if (s) s.unread_count = 0
    }
    scrollBottom()
  } catch {
    // 拦截器已提示
  }
}

function openSession(s) {
  activeUserId.value = s.other_user_id
  activeName.value = s.other_nickname
  currentItemId.value = null // 从会话进入查看完整聊天，不按物品过滤
  loadChat()
}

async function send() {
  const content = draft.value.trim()
  if (!content || !activeUserId.value || sending.value) return
  sending.value = true
  try {
    const { message_id } = await sendMessage({
      receiver_id: activeUserId.value,
      item_id: currentItemId.value ?? undefined,
      content,
    })
    chatMessages.value.push({
      id: message_id,
      sender_id: myId.value,
      receiver_id: activeUserId.value,
      item_id: currentItemId.value,
      content,
      is_read: 0,
      created_at: new Date().toISOString(),
    })
    draft.value = ''
    scrollBottom()
    loadSessions() // 刷新左侧会话预览与时间
  } catch {
    // 拦截器已提示
  } finally {
    sending.value = false
  }
}

onMounted(async () => {
  await loadSessions()
  // 支持从物品详情等入口携带 ?otherUserId=xxx&itemId=xxx 直接打开会话
  const otherId = Number(route.query.otherUserId)
  if (otherId) {
    const s = sessions.value.find((x) => x.other_user_id === otherId)
    activeUserId.value = otherId
    activeName.value = s?.other_nickname || t('message.neighborWithId', { id: otherId })
    const itemId = Number(route.query.itemId)
    currentItemId.value = itemId || null
    await loadChat()
  }
})
</script>

<style scoped>
.page-sub {
  margin: 6px 0 0;
  font-size: 14px;
}

.chat-shell {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 18px;
  height: 68vh;
  min-height: 480px;
  margin-top: 28px;
}

/* ---------- 左侧会话面板 ---------- */
.session-panel {
  display: flex;
  flex-direction: column;
  background: #fff;
  border: 1px solid rgba(76, 175, 80, 0.22);
  border-radius: 16px;
  overflow: hidden;
}

.panel-head {
  padding: 14px 18px;
  font-size: 15px;
  font-weight: 700;
  color: #2e7d32;
  border-bottom: 1px solid rgba(76, 175, 80, 0.16);
  background: #f4fbf6;
}

.session-list {
  flex: 1;
  overflow-y: auto;
}

.session-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 13px 16px;
  border: none;
  border-bottom: 1px solid rgba(76, 175, 80, 0.1);
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: background 0.2s;
}

.session-item:hover {
  background: #f1f8f3;
}

.session-item.active {
  background: #e8f5e9;
}

.avatar {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, #4caf50, #2e7d32);
  color: #fff;
  font-size: 16px;
  font-weight: 700;
}

.avatar.sm {
  width: 32px;
  height: 32px;
  font-size: 14px;
}

.session-main {
  flex: 1;
  min-width: 0;
}

.session-name {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: #1b3a26;
}

.session-last {
  display: block;
  margin-top: 3px;
  font-size: 12.5px;
  color: #63786d;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-side {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 5px;
  flex-shrink: 0;
}

.session-time {
  font-size: 11.5px;
  color: #9db3a6;
}

.unread-badge {
  min-width: 18px;
  padding: 1px 6px;
  border-radius: 999px;
  background: #4caf50;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  text-align: center;
}

.session-empty {
  padding: 40px 20px;
  text-align: center;
  font-size: 13.5px;
}

/* ---------- 右侧聊天面板 ---------- */
.chat-panel {
  display: flex;
  flex-direction: column;
  background: #fff;
  border: 1px solid rgba(76, 175, 80, 0.22);
  border-radius: 16px;
  overflow: hidden;
}

.chat-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.chat-title {
  font-size: 15px;
  font-weight: 700;
  color: #1b3a26;
}

.chat-item-tag {
  padding: 3px 10px;
  border-radius: 999px;
  background: #e8f5e9;
  color: #2e7d32;
  font-size: 12px;
}

.chat-box {
  flex: 1;
  padding: 18px;
  overflow-y: auto;
  background: #f4fbf6;
}

.msg-row {
  display: flex;
  margin-bottom: 14px;
}

.msg-row.mine {
  justify-content: flex-end;
}

.bubble {
  max-width: 72%;
  padding: 10px 14px;
  border-radius: 14px;
  background: #fff;
  border: 1px solid rgba(76, 175, 80, 0.22);
}

.msg-row.mine .bubble {
  background: linear-gradient(135deg, #4caf50, #2e7d32);
  border: none;
}

.msg-content {
  margin: 0;
  font-size: 14px;
  line-height: 1.7;
  color: #2c4637;
  word-break: break-word;
}

.msg-row.mine .msg-content {
  color: #fff;
}

.msg-time {
  display: block;
  margin-top: 4px;
  font-size: 11px;
  color: #9db3a6;
  text-align: right;
}

.msg-row.mine .msg-time {
  color: rgba(255, 255, 255, 0.75);
}

/* ---------- 输入区 ---------- */
.chat-input {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  padding: 14px 16px;
  border-top: 1px solid rgba(76, 175, 80, 0.16);
  background: #fff;
}

.chat-input .el-button {
  height: 46px;
}

.chat-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  gap: 12px;
}

.empty-icon {
  font-size: 44px;
}

.chat-empty p {
  margin: 0;
  color: #63786d;
  font-size: 14px;
}

@media (max-width: 800px) {
  .chat-shell {
    grid-template-columns: 1fr;
    height: auto;
  }

  .session-list {
    max-height: 240px;
  }

  .chat-panel {
    height: 60vh;
  }
}
</style>
