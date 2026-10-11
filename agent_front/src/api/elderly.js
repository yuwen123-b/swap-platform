import request from './request'

// 助老交互：FormData（audio 可选、text 可选），后端 ASR 不可用时返回 503
export const elderlyInteract = (formData, config = {}) =>
  request.post('/elderly/interact', formData, config)

// 一键呼叫子女/志愿者
export const callHelp = (data) => request.post('/elderly/call-help', data)
