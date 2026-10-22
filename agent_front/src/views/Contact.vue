<template>
  <section class="page contact-page">
    <div class="page-head">
      <div class="eyebrow">Contact Us</div>
      <h1 class="page-title">联系<span class="gradient-text">客服</span></h1>
      <p class="page-sub muted">有任何问题或建议，随时找到我们</p>
    </div>

    <!-- 客服信息 -->
    <div class="info-grid">
      <div class="panel info-card">
        <span class="info-icon">✉️</span>
        <h2 class="info-title">客服邮箱</h2>
        <p class="info-value">support@xianwu-huanxin.com</p>
        <p class="info-note">全天生效，48 小时内回复</p>
      </div>
      <div class="panel info-card">
        <span class="info-icon">📞</span>
        <h2 class="info-title">客服电话</h2>
        <p class="info-value">400-880-2026</p>
        <p class="info-note">工作日 9:00 - 18:00</p>
      </div>
      <div class="panel info-card">
        <span class="info-icon">💬</span>
        <h2 class="info-title">客服微信</h2>
        <p class="info-value">xianwu-helper</p>
        <p class="info-note">添加备注「社区互助」，拉你进邻居群</p>
      </div>
    </div>

    <!-- 留言反馈 -->
    <div class="panel form-panel">
      <h2 class="form-title">📝 留言反馈</h2>
      <p class="form-sub muted">留下你的问题或建议，我们会尽快回复</p>

      <el-form label-position="top" @submit.prevent="submitFeedback">
        <div class="form-row">
          <el-form-item label="姓名" required>
            <el-input v-model="form.name" placeholder="怎么称呼你？" maxlength="20" />
          </el-form-item>
          <el-form-item label="联系方式" required>
            <el-input
              v-model="form.contact"
              placeholder="手机号 / 微信号 / 邮箱"
              maxlength="50"
            />
          </el-form-item>
        </div>
        <el-form-item label="留言内容" required>
          <el-input
            v-model="form.message"
            type="textarea"
            :rows="5"
            maxlength="300"
            show-word-limit
            placeholder="写下你想对社区说的话、遇到的问题或改进建议……"
          />
        </el-form-item>
        <div class="form-actions">
          <el-button type="primary" native-type="submit" :loading="submitting">
            提交留言
          </el-button>
        </div>
      </el-form>
    </div>
  </section>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { submitFeedback as submitFeedbackApi } from '../api/user'
import { useUserStore } from '../store/user'

const userStore = useUserStore()

const form = reactive({
  name: '',
  contact: '',
  message: '',
})

const submitting = ref(false)

const SUPPORT_EMAIL = 'support@xianwu-huanxin.com'

// 降级方案：无法调用接口（未登录 / 请求失败）时，改用邮件客户端发送
function fallbackToMailto() {
  const subject = encodeURIComponent(`【留言反馈】${form.name.trim()}`)
  const body = encodeURIComponent(
    `姓名：${form.name.trim()}\n联系方式：${form.contact.trim()}\n\n${form.message.trim()}`,
  )
  window.location.href = `mailto:${SUPPORT_EMAIL}?subject=${subject}&body=${body}`
  ElMessage.info('已为你打开邮件客户端，请直接发送')
}

async function submitFeedback() {
  if (!form.name.trim() || !form.contact.trim() || !form.message.trim()) {
    ElMessage.warning('请填写完整姓名、联系方式与留言内容')
    return
  }

  // 复用个人中心的反馈接口 POST /user/feedback（user_feedback 表）：
  // 姓名并入留言内容，联系方式作为 contact 字段；不为此功能新建任何表。
  if (!userStore.isLoggedIn) {
    fallbackToMailto()
    return
  }

  submitting.value = true
  try {
    await submitFeedbackApi({
      content: `【${form.name.trim()}】${form.message.trim()}`.slice(0, 500),
      contact: form.contact.trim(),
    })
    ElMessage.success('留言已提交，感谢你的反馈！我们会尽快回复你 🌿')
    Object.assign(form, { name: '', contact: '', message: '' })
  } catch (error) {
    // 401 已由请求拦截器跳转登录，这里只在其它失败时走邮件兜底
    if (error?.response?.status === 401) return
    fallbackToMailto()
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.page-head {
  text-align: center;
}

.page-sub {
  margin: 6px 0 0;
  font-size: 15px;
}

/* ---------- 通用绿色卡片：白底 / 16px 圆角 / 浅绿边框 ---------- */
.panel {
  padding: 28px 26px;
  background: #fff;
  border: 1px solid rgba(76, 175, 80, 0.22);
  border-radius: 16px;
  transition: transform 0.25s ease, box-shadow 0.25s ease;
}

.panel:hover {
  transform: translateY(-3px);
  box-shadow: 0 14px 30px rgba(46, 125, 50, 0.12);
}

/* ---------- 客服信息 ---------- */
.info-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 18px;
  margin-top: 34px;
}

.info-card {
  text-align: center;
}

.info-icon {
  font-size: 32px;
}

.info-title {
  margin: 12px 0 8px;
  font-size: 16px;
  color: #2e7d32;
}

.info-value {
  margin: 0;
  font-size: 16.5px;
  font-weight: 700;
  color: #1b3a26;
  word-break: break-all;
}

.info-note {
  margin: 8px 0 0;
  font-size: 12.5px;
  color: #63786d;
}

/* ---------- 留言反馈 ---------- */
.form-panel {
  margin-top: 20px;
}

.form-title {
  margin: 0;
  font-size: 19px;
  color: #2e7d32;
}

.form-sub {
  margin: 6px 0 18px;
  font-size: 13.5px;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 800px) {
  .info-grid {
    grid-template-columns: 1fr;
  }

  .form-row {
    grid-template-columns: 1fr;
    gap: 0;
  }
}
</style>
