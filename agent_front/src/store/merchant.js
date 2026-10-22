import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { getMerchantInfo } from '../api/merchant'

/**
 * 商家身份缓存（工作台守卫与 5 个页面共用）。
 *
 * 为什么需要缓存：路由守卫每次跳转都要判断「是不是已通过审核的商家」，
 * 若每次都打 /merchant/info，在工作台里点 4 个菜单就是 4 次多余请求。
 *
 * 【请求静默】
 * fetchInfo 一律带 skipErrorToast —— 它会被路由守卫调用，若让拦截器弹错，
 * 每次导航失败都会弹一次。调用方（页面按钮）需要提示时自己 catch 后 ElMessage。
 *
 * 【缓存失效靠 token 指纹，而不是靠「退出登录时手动清」】
 * 工作台里切换账号只能通过退出登录（会回到 /login），但用户也可能在
 * 另一个标签页登录了别的账号 —— 那时本标签页的 localStorage.token 已经变了。
 * 所以把「取信息时的 token」记下来，取数前比对一次：token 变了就自动作废缓存。
 * 这样既不用改 user.js 的 logout()，也不会出现「A 账号看到 B 账号店铺」。
 */
export const useMerchantStore = defineStore('merchant', () => {
  const loaded = ref(false)
  const enabled = ref(true)
  const info = ref(null)
  // 取信息时的 token 指纹；与当前 localStorage.token 不一致 → 缓存作废
  const ownerToken = ref('')

  const status = computed(() => (info.value ? Number(info.value.status) : null))
  const isMerchant = computed(() => Boolean(info.value))
  // 1 = 已通过审核：只有这个状态能进工作台
  const isApproved = computed(() => status.value === 1)

  function apply(data, token = '') {
    info.value = data?.merchant || null
    // enabled 只认「明确为 false」：老后端不返回该字段时不能把功能判成关闭
    enabled.value = data?.enabled !== false
    ownerToken.value = token
    loaded.value = true
  }

  /**
   * 取商家信息。默认走缓存；force=true 强制刷新。
   *
   * 失败时**不写入任何状态**（不把「请求失败」记成「不是商家」）——
   * 否则一次网络抖动就会让商家被踢回入驻页。
   */
  async function fetchInfo(force = false) {
    const token = localStorage.getItem('token') || ''
    if (!force && loaded.value && ownerToken.value === token) {
      return { merchant: info.value, enabled: enabled.value }
    }
    const data = await getMerchantInfo({ skipErrorToast: true })
    apply(data, token)
    return data
  }

  function reset() {
    loaded.value = false
    enabled.value = true
    info.value = null
    ownerToken.value = ''
  }

  return { loaded, enabled, info, ownerToken, status, isMerchant, isApproved, apply, fetchInfo, reset }
})
