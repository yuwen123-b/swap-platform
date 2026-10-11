import request from './request'

// 发送私信 { receiver_id, item_id?, content }
export const sendMessage = (data) => request.post('/messages', data)

// 获取与某人的聊天记录（itemId 可选，用于过滤关联物品的会话）
export const getChatHistory = (otherUserId, itemId) =>
  request.get('/messages/chat', { params: { other_user_id: otherUserId, item_id: itemId ?? undefined } })

// 当前用户会话列表（按对方用户分组，含最后一条消息与未读数）
export const getSessionList = () => request.get('/messages/sessions')

// 标记某条消息为已读
export const markRead = (messageId) => request.put(`/messages/read/${messageId}`)
