<template>
  <ProfileSubLayout title="意见反馈" desc="你的建议会帮助我们做得更好">
    <section class="profile-card">
      <h2 class="card-title">反馈内容</h2>

      <div class="form-item">
        <label class="form-label" for="feedback-content">想说的话</label>
        <el-input
          id="feedback-content"
          v-model="form.content"
          type="textarea"
          :rows="6"
          maxlength="500"
          show-word-limit
          placeholder="请描述你遇到的问题或建议（不超过 500 字）"
        />
      </div>

      <div class="form-item">
        <label class="form-label" for="feedback-contact">联系方式（选填）</label>
        <el-input
          id="feedback-contact"
          v-model="form.contact"
          maxlength="100"
          placeholder="手机号或邮箱，方便我们与你联系"
        />
      </div>

      <div class="form-actions">
        <el-button type="primary" class="save-btn" :loading="submitting" @click="onSubmit">
          提交反馈
        </el-button>
        <el-button :disabled="submitting" @click="reset">重置</el-button>
      </div>
    </section>
  </ProfileSubLayout>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import ProfileSubLayout from '../../layouts/ProfileSubLayout.vue'
import { submitFeedback } from '../../api/user'

const submitting = ref(false)
const form = reactive({ content: '', contact: '' })

function reset() {
  form.content = ''
  form.contact = ''
}

async function onSubmit() {
  const content = form.content.trim()
  if (!content) {
    ElMessage.warning('请填写反馈内容')
    return
  }
  submitting.value = true
  try {
    await submitFeedback({ content, contact: form.contact.trim() || undefined })
    reset()
    ElMessage.success('感谢你的反馈，我们会尽快处理')
  } catch {
    // 错误提示由请求拦截器统一处理
  } finally {
    submitting.value = false
  }
}
</script>
