import request from './request'

// 国际化
export const setLanguage = (data) => request.post('/i18n/set-language', data)
export const translateText = (data) => request.post('/translate', data)
