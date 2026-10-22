import { ref } from 'vue'
import { defineStore } from 'pinia'

/**
 * 「AI 估价 → 一键发布」的跨页草稿（估价页 → 物品列表发布弹窗）。
 *
 * 为什么必须是 pinia 而不是 sessionStorage / URL query：
 * 草稿里包含**图片 File 对象**，File 无法被 JSON 序列化（sessionStorage 会写成
 * "[object File]"、URL 更长不下），只有同一次 SPA 会话内的内存引用才能把它交出去。
 *
 * 生命周期：估价页 setDraft → 发布弹窗读取并预填 → **提交成功或关闭弹窗后 clearDraft**，
 * 避免用户下次从侧边栏直接进列表页时被上一次估价的旧数据污染。
 */
export const usePublishDraftStore = defineStore('publishDraft', () => {
  // null 表示没有待发布的草稿
  const draft = ref(null)

  /**
   * 写入草稿。字段约定（全部可选，缺失即不预填）：
   *   imageFile      图片 File 对象（引用传递，不序列化）
   *   title          物品名称
   *   description    物品描述
   *   categoryName   分类**中文名**（发布页需再映射成 category_id）
   *   conditionLevel 成色 1-5（估价页 el-rate 的值）
   *   originalPrice  原价（估价页表单里用户填的原价）
   *   price          建议售价（估价结果的 suggested_price）
   *   contact        联系方式（估价页没有，预留）
   */
  function setDraft(payload) {
    draft.value = payload ? { ...payload } : null
  }

  function clearDraft() {
    draft.value = null
  }

  return { draft, setDraft, clearDraft }
})
