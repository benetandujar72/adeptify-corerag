import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

function browser(cookie = '__Host-adeptify_csrf=synthetic-csrf-only', base = '/api') {
  const calls = []
  const values = new Map([['patufet_token', 'old-synthetic-token']])
  const storage = { getItem: key => values.get(key), removeItem: key => values.delete(key), setItem: (key,v) => values.set(key,v) }
  const context = { exports: {}, URL, Headers, Request, Response, Event,
    document: { cookie }, window: { location: { origin: 'https://suite.example.test' }, dispatchEvent() {} },
    localStorage: storage, sessionStorage: storage,
    fetch: async (input, init) => { calls.push({ input, init }); return new Response('{}', { status: 200 }) } }
  let source = readFileSync(new URL('../src/auth/cookieSession.ts', import.meta.url), 'utf8')
    .replace('import.meta.env.VITE_API_BASE_URL', JSON.stringify(base))
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  } }).outputText, context)
  context.exports.installCookieSessionTransport()
  return { context, calls, values, mod: context.exports }
}

test('session transport removes old JWT storage and browser Authorization', async () => {
  const { context, calls, values } = browser()
  assert.equal(values.has('patufet_token'), false)
  await context.fetch('/api/auth/me', { headers: { Authorization: 'Bearer synthetic-old' } })
  assert.equal(calls[0].init.headers.has('Authorization'), false)
  assert.equal(calls[0].init.credentials, 'same-origin')
  assert.equal(calls[0].init.headers.get('X-Adeptify-Session'), 'cookie')
  assert.equal(calls[0].init.cache, 'no-store')
})

test('unsafe cookie requests carry CSRF, preserving uploads and cancellation', async () => {
  const { context, calls } = browser()
  const body = new FormData(); body.set('file', 'synthetic')
  const signal = new AbortController().signal
  await context.fetch('/api/upload', { method: 'POST', body, signal, keepalive: true })
  assert.equal(calls[0].init.headers.get('X-Adeptify-CSRF'), 'synthetic-csrf-only')
  assert.equal(calls[0].init.body, body)
  assert.equal(calls[0].init.signal, signal)
  assert.equal(calls[0].init.keepalive, true)
})

test('SSE reads have cookie credentials and do not send CSRF unnecessarily', async () => {
  const { context, calls } = browser()
  await context.fetch('/api/missatgeria/stream', { headers: { Accept: 'text/event-stream' } })
  assert.equal(calls[0].init.headers.get('Accept'), 'text/event-stream')
  assert.equal(calls[0].init.headers.has('X-Adeptify-CSRF'), false)
  assert.equal(calls[0].init.credentials, 'same-origin')
})

test('CSRF is not sent to external providers, apps or lookalike API paths', async () => {
  const { context, calls } = browser()
  for (const url of ['https://external.example.test/api/auth', '/fitxai/api/logout', '/fotosegura/api/logout', '/api-evil']) {
    await context.fetch(url, { method: 'POST' })
    assert.equal(calls.at(-1).init.headers, undefined)
    assert.equal(calls.at(-1).init.credentials, undefined)
  }
})

test('configured API in a different origin is closed before any request', async () => {
  const { context, calls } = browser('', 'https://external.example.test/api')
  await assert.rejects(context.fetch('https://external.example.test/api/auth/login', { method: 'POST' }),
    /mateix origen/)
  assert.equal(calls.length, 0)
})

test('duplicated or malformed CSRF cookies fail closed', () => {
  assert.equal(browser('__Host-adeptify_csrf=a; adeptify_csrf_dev=b').mod.csrfDelNavegador(), null)
  assert.equal(browser('__Host-adeptify_csrf=%zz').mod.csrfDelNavegador(), null)
  assert.equal(browser('').mod.csrfDelNavegador(), null)
})

test('Request objects retain their HTTP method and receive CSRF on writes', async () => {
  const { context, calls } = browser()
  const req = new Request('https://suite.example.test/api/record', { method: 'DELETE' })
  await context.fetch(req)
  assert.equal(calls[0].init.headers.get('X-Adeptify-CSRF'), 'synthetic-csrf-only')
})

test('a new credentialed login clears logout intent without storing a JWT', () => {
  const { values, mod } = browser()
  values.set('adeptify_logout_pending', '1')
  mod.notificaEntrada()
  assert.equal(values.has('adeptify_logout_pending'), false)
  assert.equal(values.has('patufet_token'), false)
  assert.equal(values.has('adeptify_session_changed'), true)
})

test('logout intent is read safely when browser storage is blocked', () => {
  const { context, values, mod } = browser()
  values.set('adeptify_logout_pending', '1')
  assert.equal(mod.teSortidaPendent(), true)
  context.localStorage.getItem = () => { throw new Error('Storage blocked') }
  assert.equal(mod.teSortidaPendent(), false)
})

