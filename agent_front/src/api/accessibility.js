import request from './request'

// 无障碍模式
export const setAccessibilityMode = (data) => request.post('/accessibility/set-mode', data)
export const setMobilityLevel = (data) => request.post('/accessibility/set-mobility', data)
export const getHandoverOptions = (userId) => request.get(`/accessibility/handover-options/${userId}`)
export const getVoiceLabel = (itemId, lang = 'zh_CN') =>
  request.get(`/accessibility/voice-label/${itemId}`, { params: { lang } })

// 志愿者代取任务
export const createVolunteerTask = (data) => request.post('/volunteer/task', data)
export const getVolunteerTasks = (userId) => request.get(`/volunteer/tasks/${userId}`)
export const updateVolunteerTask = (taskId, data) => request.put(`/volunteer/task/${taskId}`, data)
