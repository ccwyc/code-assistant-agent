/**
 * 后端 API 客户端。
 *
 * 统一约定：
 * - 所有请求走 `VITE_API_BASE`（默认 `/api`，开发期由 Vite 代理、生产期由 Nginx 反代）；
 * - 非 2xx 统一抛 ApiError（带 status / hint），页面层直接展示 detail；
 * - 流式对话使用 fetch + ReadableStream 手写 SSE 解析（EventSource 不支持 POST）。
 */

const BASE = (import.meta.env.VITE_API_BASE ?? '/api').replace(/\/+$/, '')

export class ApiError extends Error {
  constructor(message, { status = 0, hint = '', code = '' } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.hint = hint
    this.code = code
  }
}

async function readErrorPayload(response) {
  try {
    const data = await response.json()
    return {
      detail: data?.detail || data?.message || '',
      hint: data?.hint || '',
    }
  } catch (error) {
    return { detail: '', hint: '' }
  }
}

async function toApiError(response) {
  const { detail, hint } = await readErrorPayload(response)
  const fallback =
    response.status === 503
      ? '后端未配置 DEEPSEEK_API_KEY，暂时无法调用模型'
      : response.status === 502
        ? '模型服务调用失败，请查看后端日志'
        : response.status === 504
          ? '模型调用超时，请稍后重试'
          : `请求失败（HTTP ${response.status}）`
  return new ApiError(detail || fallback, { status: response.status, hint })
}

function withNetworkMessage(error) {
  if (error instanceof ApiError) return error
  if (error?.name === 'AbortError') return error
  return new ApiError('无法连接后端服务，请确认 FastAPI 已启动（默认 127.0.0.1:8000）', {
    code: 'network',
    hint: '检查 .env 中的端口与 VITE_PROXY_TARGET 配置',
  })
}

async function request(path, { method = 'GET', body, signal, timeout = 15000 } = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  const onAbort = () => controller.abort()
  signal?.addEventListener('abort', onAbort, { once: true })
  try {
    const response = await fetch(`${BASE}${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    })
    if (!response.ok) throw await toApiError(response)
    return await response.json()
  } catch (error) {
    throw withNetworkMessage(error)
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', onAbort)
  }
}

/* ------------------------------------------------------------------ 健康检查 */
export function fetchHealth() {
  return request('/health', { timeout: 8000 })
}

/* ------------------------------------------------------------------ 会话管理 */
export function fetchHistory(threadId) {
  return request(`/threads/${encodeURIComponent(threadId)}/history`)
}

export function removeThread(threadId) {
  return request(`/threads/${encodeURIComponent(threadId)}`, { method: 'DELETE' })
}

/* ------------------------------------------------------------------ SSE 解析 */
function createSseParser(onEvent) {
  let buffer = ''

  function handleBlock(raw) {
    if (!raw || !raw.trim()) return
    let event = 'message'
    const dataLines = []

    for (const line of raw.split('\n')) {
      if (!line || line.startsWith(':')) continue
      const colon = line.indexOf(':')
      const field = colon === -1 ? line : line.slice(0, colon)
      let value = colon === -1 ? '' : line.slice(colon + 1)
      if (value.startsWith(' ')) value = value.slice(1)

      if (field === 'event') event = value
      else if (field === 'data') dataLines.push(value)
    }

    if (!dataLines.length) return
    const text = dataLines.join('\n')
    let data = text
    try {
      data = JSON.parse(text)
    } catch (error) {
      /* 非 JSON 的 data 原样透传 */
    }
    onEvent({ event, data })
  }

  return {
    push(chunk) {
      buffer += chunk.replace(/\r\n/g, '\n')
      let boundary = buffer.indexOf('\n\n')
      while (boundary !== -1) {
        handleBlock(buffer.slice(0, boundary))
        buffer = buffer.slice(boundary + 2)
        boundary = buffer.indexOf('\n\n')
      }
    },
    flush() {
      if (buffer.trim()) handleBlock(buffer)
      buffer = ''
    },
  }
}

/* ------------------------------------------------------------------ 对话 */
export async function sendChat({ threadId, message, language, signal }) {
  return request('/chat', {
    method: 'POST',
    body: { thread_id: threadId, message, language: language || null },
    signal,
    timeout: 180000,
  })
}

/**
 * 流式对话。onEvent 会收到 { event, data }：
 * meta / token / tool_call / tool_result / done / error。
 */
export async function streamChat({ threadId, message, language, signal, onEvent }) {
  let response
  try {
    response = await fetch(`${BASE}/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify({
        thread_id: threadId,
        message,
        language: language || null,
      }),
      signal,
    })
  } catch (error) {
    throw withNetworkMessage(error)
  }

  if (!response.ok) throw await toApiError(response)
  if (!response.body) {
    throw new ApiError('当前浏览器不支持流式响应，请改用非流式模式', { code: 'no-stream' })
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  const parser = createSseParser(onEvent)

  try {
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      parser.push(decoder.decode(value, { stream: true }))
    }
    parser.push(decoder.decode())
    parser.flush()
  } finally {
    reader.releaseLock?.()
  }
}

export { BASE as apiBase }
