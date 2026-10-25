/**
 * Cloudflare Pages 高级模式反向代理（_worker.js）
 *
 * 作用：管理端浏览器只请求本站同源地址，/api/* 由 Pages 服务端转发到 ngrok 隧道。
 * 解决两个免费版 ngrok 的死结：
 *   1. CORS：同源请求根本不需要 CORS 头；
 *   2. 拦截页：ngrok 免费版对「像浏览器」且不带 ngrok-skip-browser-warning
 *      头的请求返回 200 + HTML 拦截页 → XHR 报 Network Error / ERR_FAILED 200。
 *      改走本代理后由服务端统一注入该头，且 CF 边缘 UA 不是浏览器。
 *
 * 注意：构建/部署时不要再把 VITE_API_BASE_URL 覆盖成 ngrok 绝对地址，
 *       必须保持 .env 里的相对路径 /api/admin，请求才会进本代理。
 * ngrok 免费版重启后地址会变：改本文件的 FALLBACK_UPSTREAM 即可；
 * 也可在 CF Pages「设置 → 环境变量」配置 NGROK_UPSTREAM（优先级更高）。
 */
const FALLBACK_UPSTREAM = 'https://silica-pushover-rudder.ngrok-free.dev'

export default {
  async fetch(request, env) {
    const url = new URL(request.url)

    // 非接口请求：走 Pages 静态资源
    if (!url.pathname.startsWith('/api/')) {
      return env.ASSETS.fetch(request)
    }

    const upstream = (env && env.NGROK_UPSTREAM) || FALLBACK_UPSTREAM
    const target = upstream.replace(/\/+$/, '') + url.pathname + url.search

    const proxied = new Request(target, request)
    proxied.headers.set('ngrok-skip-browser-warning', 'true')
    return fetch(proxied)
  },
}
