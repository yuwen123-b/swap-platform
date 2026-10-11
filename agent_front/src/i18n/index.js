import { reactive } from 'vue'

// 语言包分片（产品已取消多语言，仅保留中文）
const modules = import.meta.glob('./locales/zh/*.js', { eager: true })

function collect(mods) {
  const out = {}
  for (const [path, mod] of Object.entries(mods)) {
    const name = path.split('/').pop().replace('.js', '')
    out[name] = mod.default || {}
  }
  return out
}

const messages = { zh_CN: collect(modules) }

// 语言状态固定中文（对外保留 state 结构，页面可只读引用）
export const state = reactive({ locale: 'zh_CN' })

// t('shard.key', { param }) —— 缺 key 时回退键名，支持 {name} 插值
export function t(key, params) {
  let text = key
    .split('.')
    .reduce((node, seg) => (node && node[seg] !== undefined ? node[seg] : undefined), messages[state.locale])
  if (text === undefined || text === null) text = key
  if (params && typeof text === 'string') {
    text = text.replace(/\{(\w+)\}/g, (m, k) => (params[k] !== undefined ? String(params[k]) : m))
  }
  return text
}

export function useI18n() {
  return { state, t }
}
