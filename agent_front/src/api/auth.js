import request from './request'
export const sendCode = (data) => request.post('/auth/send-code', data)
export const register = (data) => request.post('/auth/register', data)
export const loginEmailCode = (data) => request.post('/auth/login/email-code', data)
export const loginPhoneCode = (data) => request.post('/auth/login/phone-code', data)
export const loginPassword = (data) => request.post('/auth/login/password', data)
export const getMe = () => request.get('/auth/me')
