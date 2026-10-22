<template>
  <div class="container">
    <!-- 顶部品牌头部 -->
    <header class="as-header">
      <div class="as-brand">
        <span class="as-mark">★</span>
        <span class="as-title">智能体助手</span>
      </div>
      <div class="as-sub">
        旧物互换 · 智能问答
        <el-button v-if="chatList.length" link class="clear-btn" @click="clearConfirm">
          清空对话
        </el-button>
      </div>
    </header>

    <!-- 主体：空状态欢迎引导 + 对话区 -->
    <div class="as-body">
      <transition name="fade">
        <div v-if="chatList.length === 0" class="welcome">
          <div class="welcome-greet">
            <div class="welcome-hi">
              你好，我是<span class="grad-text">旧物互换智能助手</span>
            </div>
            <div class="welcome-tip">关于物品发布、智能匹配、交易安全、环保价值，都可以问我</div>
          </div>
          <div class="preset-grid">
            <div
              v-for="(q, i) in presetQuestions"
              :key="i"
              class="preset-card"
              @click="clickPreset(q)"
            >
              <span class="preset-icon">❝</span>
              <span class="preset-text">{{ q }}</span>
            </div>
          </div>
        </div>
      </transition>

      <el-scrollbar ref="scrollRef" class="chat-list" always>
        <div class="chat-inner">
          <div
            v-for="(msg, idx) in chatList"
            :key="idx"
            class="msg-row"
            :class="msg.role === 'user' ? 'is-user' : 'is-ai'"
          >
            <span class="msg-avatar" :class="msg.role">{{ msg.role === 'user' ? '我' : 'AI' }}</span>
            <div class="msg-bubble">
              <span class="msg-text" v-html="renderContent(msg.content)"></span>
              <span v-if="msg.streaming" class="cursor">▍</span>
            </div>
          </div>
        </div>
      </el-scrollbar>

      <div class="sender">
        <el-input
          v-model="query"
          type="textarea"
          :rows="2"
          resize="none"
          placeholder="请输入消息...（Enter 发送，Shift+Enter 换行）"
          :disabled="isStreamLoad"
          @keydown.enter.exact.prevent="inputEnter"
        />
        <div class="sender-actions">
          <el-button v-if="!isStreamLoad" type="primary" class="send-btn" @click="inputEnter">
            发送
          </el-button>
          <el-button v-else type="danger" plain class="send-btn" @click="onStop">
            停止
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>
<!--scoped 属性代表设置的样式仅对Assistant.vue页面有效，对其他vue界面不生效-->
<style scoped>
.container {
  /* 与导航栏对齐：main 已限制 min(1180px,88vw) 并居中，这里在其内部再做统一宽度约束 */
  width: 100%;
  max-width: 1200px;
  margin: 12px auto 0;
  padding: 0 24px;
  /* 顶部导航(72px + 12px 外边距)之外铺满剩余视口，保证聊天区内部滚动 */
  /* 先写 vh 兜底，再用 --app-vvh（visualViewport 实时值）覆盖：
     手机上键盘弹起时 --app-vvh 会变小，整个聊天容器随之收缩，
     输入区始终留在可视区内。PC 上没有键盘，两者等价。 */
  height: calc(100vh - 108px);
  height: calc(var(--app-vvh, 100dvh) - 108px);
  display: flex;
  flex-direction: column;
  background:
    radial-gradient(circle at 18% 8%, rgba(15, 118, 110, 0.08), transparent 50%),
    radial-gradient(circle at 88% 92%, rgba(212, 175, 55, 0.1), transparent 50%),
    var(--bg, #fff);
}

/* 小标题栏：无左右外边距，紧贴主容器内边距线 */
.as-header {
  flex-shrink: 0;
  margin-left: 0;
  margin-right: 0;
  padding: 16px 4px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: transparent;
  border-bottom: 1px solid var(--line, #eef0f5);
}

.as-brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.as-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: var(--grad-brand, linear-gradient(120deg, #0f766e, #1e3a8a));
  color: #fff;
  font-size: 1.1rem;
  box-shadow: 0 6px 14px rgba(15, 118, 110, 0.35);
}

.as-title {
  font-size: 1.15rem;
  font-weight: 800;
  letter-spacing: 2px;
  color: var(--ink, #1f2329);
}

.as-sub {
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: 0.85rem;
  color: var(--muted, #646a73);
  letter-spacing: 1px;
}

/* ---------- 主体 ---------- */
.as-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  position: relative;
  overflow: hidden;
}

.chat-list {
  flex: 1;
  min-height: 0;
  width: 100%;
}

.chat-inner {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 26px 8px;
}

/* ---------- 空状态欢迎引导 ---------- */
.welcome {
  flex-shrink: 0;
  width: 100%;
  padding: 40px 4px 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 26px;
}

.welcome-greet {
  text-align: center;
}

.welcome-hi {
  font-size: 1.5rem;
  font-weight: 800;
  letter-spacing: 1px;
  color: var(--ink, #1f2329);
}

.grad-text {
  background: var(--grad-title, linear-gradient(100deg, #0f766e, #1e3a8a, #d4af37));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.welcome-tip {
  margin-top: 10px;
  font-size: 0.9rem;
  color: var(--muted, #646a73);
  letter-spacing: 1px;
}

.preset-grid {
  width: 100%;
  max-width: 760px;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.preset-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 18px;
  background: #fff;
  border: 1px solid var(--line, #eef0f5);
  border-radius: 12px;
  box-shadow: 0 4px 14px rgba(31, 35, 41, 0.04);
  cursor: pointer;
  transition: all 0.25s ease;
}

.preset-card:hover {
  border-color: var(--brand, #0f766e);
  box-shadow: 0 10px 24px rgba(15, 118, 110, 0.12);
  transform: translateY(-2px);
}

.preset-icon {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: var(--brand-pale, #e6f2f0);
  color: var(--brand, #0f766e);
  font-size: 0.95rem;
}

.preset-text {
  font-size: 0.9rem;
  color: var(--ink, #1f2329);
  line-height: 1.4;
}

/* ---------- 对话气泡 ---------- */
.msg-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.msg-row.is-user {
  flex-direction: row-reverse;
}

.msg-avatar {
  flex-shrink: 0;
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
}

.msg-avatar.user {
  background: linear-gradient(135deg, #0f766e, #14b8a6);
}

.msg-avatar.ai {
  background: linear-gradient(135deg, #d4af37, #f59e0b);
}

.msg-bubble {
  max-width: 72%;
  padding: 12px 16px;
  border-radius: 14px;
  font-size: 0.92rem;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.is-user .msg-bubble {
  background: linear-gradient(135deg, #0f766e, #14867a);
  color: #fff;
  border-top-right-radius: 4px;
}

.is-ai .msg-bubble {
  background: #fff;
  color: var(--ink, #1f2329);
  border: 1px solid var(--line, #eef0f5);
  border-top-left-radius: 4px;
  box-shadow: 0 4px 14px rgba(31, 35, 41, 0.04);
}

/* AI 返回的图表图片 */
.chart-img {
  display: block;
  max-width: 100%;
  border-radius: 8px;
  margin: 8px 0 4px;
  border: 1px solid var(--line, #eef0f5);
}

.cursor {
  display: inline-block;
  margin-left: 2px;
  color: var(--brand, #0f766e);
  animation: blink 0.9s infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

/* ---------- 输入区 ---------- */
.sender {
  flex-shrink: 0;
  width: 100%;
  margin: 0 auto 18px;
  display: flex;
  align-items: flex-end;
  gap: 12px;
  padding: 12px;
  background: #fff;
  border: 1px solid var(--line, #eef0f5);
  border-radius: 14px;
  box-shadow: 0 6px 20px rgba(31, 35, 41, 0.06);
}

.sender .el-input {
  flex: 1;
}

.send-btn {
  height: 44px;
  min-width: 88px;
}

/* ---------- 过渡 ---------- */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* ---------- 响应式 ---------- */
@media (max-width: 640px) {
  .container {
    padding: 0 16px;
  }

  .preset-grid {
    grid-template-columns: 1fr;
  }

  .welcome-hi {
    font-size: 1.25rem;
  }
}

/* ============================================================
   移动端（≤767px）
   要点：整页高度 = 真实可视区 − 顶栏(56) − 底部 Tab(54) − 余量(6)
        用 --app-vvh（由 visualViewport 写入），键盘弹起时容器同步收缩，
        输入区不会被盖住；不依赖任何 JS 定位。
   ============================================================ */
@media (max-width: 767px) {
  .container {
    /* main 已提供左右 16px，这里不再叠加，避免聊天区被压到 311px */
    padding: 0;
    margin-top: 0;
    height: calc(100vh - 116px);
    height: calc(var(--app-vvh, 100dvh) - 116px);
  }

  .as-header {
    padding: 10px 0 8px;
  }

  .as-title {
    font-size: 17px;
    letter-spacing: 1px;
  }

  .as-sub {
    gap: 8px;
    font-size: 12px;
  }

  .chat-inner {
    gap: 14px;
    padding: 14px 0;
  }

  /* 手机上气泡放宽到 86%：72% 会让长句频繁折行 */
  .msg-bubble {
    max-width: 86%;
    padding: 10px 13px;
    font-size: 15px;
    line-height: 1.65;
  }

  .sender {
    margin-bottom: 8px;
    padding: 8px;
    gap: 8px;
  }

  .send-btn {
    min-width: 64px;
    padding: 0 12px;
  }

  .preset-grid {
    gap: 10px;
  }
}
</style>
<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

/* ---------- 移动端键盘适配 ----------
   问题：iOS Safari 弹起键盘时**不会**缩小 100vh/100dvh，底部输入区会被键盘盖住；
        Android 会缩小 layout viewport，100vh 反而"够用"。
   做法：用 visualViewport.height（= 真实可视区高度，键盘会扣掉）写进 CSS 变量
        --app-vvh，样式里用它算容器高度。不存在 visualViewport 的老浏览器自动回落 100dvh。
   注意：必须监听 resize 与 scroll（iOS 在键盘弹起时会顺带滚动视口）。 */
function syncViewportHeight() {
  const vv = window.visualViewport
  if (!vv) return
  document.documentElement.style.setProperty('--app-vvh', `${Math.round(vv.height)}px`)
}

onMounted(() => {
  if (!window.visualViewport) return
  syncViewportHeight()
  window.visualViewport.addEventListener('resize', syncViewportHeight)
  window.visualViewport.addEventListener('scroll', syncViewportHeight)
})

onBeforeUnmount(() => {
  if (!window.visualViewport) return
  window.visualViewport.removeEventListener('resize', syncViewportHeight)
  window.visualViewport.removeEventListener('scroll', syncViewportHeight)
})

// 把消息文本中的 markdown 图片 ![alt](url) 渲染为 <img>，其余文本转义防 XSS
function renderContent(text) {
  if (!text) return ''
  // 1. 先转义所有 HTML 特殊字符
  const escaped = String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
  // 2. 转义后 ![alt](https://...) 形式还原为 <img>
  return escaped.replace(
    /!\[([^\]]*)\]\((https?:\/\/[^\s)]+)\)/g,
    (m, alt, url) => `<img src="${url}" alt="${alt}" class="chart-img" />`,
  )
}

// 预设问题（点击即发送，复用 inputEnter 逻辑）；computed 保证切换语言时响应式更新
const presetQuestions = computed(() => [
  '我有一台旧微波炉想换，怎么发布？',
  '我想换一本小学三年级的数学教材，附近有吗？',
  '怎么和对方约定交接时间和地点？',
  "我这个月交换了3次，能上'绿色达人'榜单吗？",
])

// 对话列表：{ role: 'user' | 'assistant', content: string, streaming?: boolean }
const chatList = ref([])
const isStreamLoad = ref(false)
const query = ref('')
const scrollRef = ref()
// js中用来手动终止SSE以及ajax等请求
let abort = null

function scrollToBottom() {
  nextTick(() => {
    const wrap = scrollRef.value?.wrapRef
    if (wrap) wrap.scrollTop = wrap.scrollHeight
  })
}

function clearConfirm() {
  // 清空会丢失本次全部对话且不可恢复：先二次确认
  // （原实现函数名叫 confirm，实际却直接清空，属误触即丢数据的隐患）
  ElMessageBox.confirm('清空后将无法恢复本次对话记录。', '确定清空对话？', {
    confirmButtonText: '清空',
    cancelButtonText: '取消',
    type: 'warning',
  })
    .then(() => {
      chatList.value = []
    })
    .catch(() => {})
}

//点击预设问题：填入输入框并复用 inputEnter 发送
function clickPreset(q) {
  query.value = q
  inputEnter()
}

//当用户点击了输入框的发送或者在输入框回车之后触发这个函数来实现智能体的问答
async function inputEnter() {
  const problem = query.value.trim()
  if (!problem || isStreamLoad.value) return
  // 1、把用户的问题渲染到界面上
  chatList.value.push({ role: 'user', content: problem })
  //清空输入框内容 query
  query.value = ''
  // 开启输入框的暂停按钮状态
  isStreamLoad.value = true
  //2、请求后端获取AI智能体的回答（SSE 流式）
  //添加一条空的AI消息，为了显示正在加载效果（reactive 包装：闭包内追加 content 才能触发视图更新）
  const aiMsg = reactive({ role: 'assistant', content: '', streaming: true })
  chatList.value.push(aiMsg)
  scrollToBottom()

  //用户信息携带上 jwt-token，后端解析出 user_id；地址走 vite 代理（/api -> 8000）
  const token = localStorage.getItem('token')
  //AbortController 是 js 真正用来手动终止异步请求的核心对象
  abort = new AbortController()
  const signal = abort.signal

  try {
    const resp = await fetch(
      '/api/v1/ai/agent/stream?question=' + encodeURIComponent(problem),
      {
        headers: { Authorization: 'Bearer ' + token },
        signal,
      },
    )
    if (!resp.ok || !resp.body) {
      const text = await resp.text().catch(() => '')
      let tip = `请求失败（${resp.status}）`
      try {
        tip = JSON.parse(text)?.message || tip
      } catch {}
      if (resp.status === 401) {
        localStorage.removeItem('token')
        tip = '登录已过期，请重新登录'
      }
      throw new Error(tip)
    }

    // 3、解析 SSE 流：按 \n\n 切帧，取 data: {"msg": "..."} 的 msg 逐段追加
    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    let done = false
    while (!done) {
      const { value, done: streamDone } = await reader.read()
      if (streamDone) break
      buffer += decoder.decode(value, { stream: true })
      const frames = buffer.split('\n\n')
      buffer = frames.pop() || ''
      for (const frame of frames) {
        const line = frame.trim()
        if (!line.startsWith('data:')) continue
        let msg = ''
        try {
          msg = JSON.parse(line.slice(5).trim())?.msg ?? ''
        } catch {
          continue
        }
        if (msg === '[end_stream]') {
          done = true
          break
        }
        aiMsg.content += msg
        scrollToBottom()
      }
    }
    // 收到结束帧后主动释放剩余流，避免浏览器记录 net::ERR_ABORTED
    await reader.cancel().catch(() => {})
  } catch (err) {
    if (err?.name === 'AbortError') {
      aiMsg.content += '\n（已停止生成）'
    } else {
      aiMsg.content =
        aiMsg.content ||
        `抱歉，出了点问题：${err?.message || '未知错误'}`
      ElMessage.error(err?.message || '请求失败')
    }
  } finally {
    aiMsg.streaming = false
    isStreamLoad.value = false
    scrollToBottom()
  }
}

//点击了输入框的停止执行按钮之后会触发这个函数执行
function onStop() {
  isStreamLoad.value = false
  if (abort) {
    abort.abort()
  }
}
</script>
