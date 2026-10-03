// The browser keeps the JWT only in a host-only HttpOnly cookie.
// All API fetches, including uploads, downloads, SSE and keepalive logout,
// share this boundary. OIDC-provider and external-module fetches remain separate.
const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '/api'

export function csrfDelNavegador(): string | null {
  const values = document.cookie.split(';').map(v => v.trim())
    .filter(v => v.startsWith('__Host-adeptify_csrf=') || v.startsWith('adeptify_csrf_dev='))
  if (values.length !== 1) return null
  try { return decodeURIComponent(values[0].slice(values[0].indexOf('=') + 1)) }
  catch { return null }
}

export function eliminaCredencialsLlegades(): void {
  for (const key of ['patufet_token', 'patufet_usuari', 'patufet_rol']) {
    try { localStorage.removeItem(key); sessionStorage.removeItem(key) } catch { /* no storage */ }
  }
}

export function notificaEntrada(): void {
  try { localStorage.removeItem('adeptify_logout_pending') } catch { /* no storage */ }
  try { localStorage.setItem('adeptify_session_changed', String(Date.now())) } catch { /* no storage */ }
}

export function teSortidaPendent(): boolean {
  try { return localStorage.getItem('adeptify_logout_pending') === '1' }
  catch { return false }
}

export function installCookieSessionTransport(): () => void {
  const original = globalThis.fetch
  const base = new URL(BASE_URL, window.location.origin)
  const path = base.pathname.replace(/\/+$/, '')
  const wrapped: typeof fetch = async (input, init = {}) => {
    const target = new URL(typeof input === 'string' ? input :
      input instanceof URL ? input.href : input.url, window.location.origin)
    const api = target.origin === base.origin &&
      (target.pathname === path || target.pathname.startsWith(path + '/'))
    if (!api) return original(input, init)
    if (base.origin !== window.location.origin)
      throw new Error('La sessió necessita l’API al mateix origen: configura /api al proxy.')
    const headers = new Headers(input instanceof Request ? input.headers : undefined)
    new Headers(init.headers).forEach((value, name) => headers.set(name, value))
    headers.delete('Authorization')
    headers.set('X-Adeptify-Session', 'cookie')
    const method = (init.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase()
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
      const csrf = csrfDelNavegador()
      if (csrf) headers.set('X-Adeptify-CSRF', csrf)
      else headers.delete('X-Adeptify-CSRF')
    }
    const response = await original(input, { ...init, headers, credentials: 'same-origin', cache: 'no-store' })
    if (response.status === 401 && !target.pathname.endsWith('/auth/login')) {
      try {
        const body = await response.clone().json()
        if (typeof body?.error?.codi === 'string')
          window.dispatchEvent(new Event('adeptify-session-expired'))
      } catch { /* a proxy response does not revoke the application session */ }
    }
    return response
  }
  globalThis.fetch = wrapped
  eliminaCredencialsLlegades()
  return () => { if (globalThis.fetch === wrapped) globalThis.fetch = original }
}

