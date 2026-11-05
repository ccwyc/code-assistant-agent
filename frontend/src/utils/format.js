/** 通用格式化 / 剪贴板 / id 工具。 */

export function uid(prefix = 'id') {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}-${crypto.randomUUID().slice(0, 8)}`
  }
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

/** 后端 thread_id 只允许 [A-Za-z0-9_.:-]，这里生成合规的会话 ID。 */
export function newThreadId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `web-${crypto.randomUUID()}`
  }
  return `web-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

export function formatTime(value) {
  const date = value ? new Date(value) : new Date()
  return date.toLocaleTimeString('zh-CN', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatRelative(value) {
  const time = value ? new Date(value).getTime() : Date.now()
  const diff = Date.now() - time
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  if (diff < 7 * 86_400_000) return `${Math.floor(diff / 86_400_000)} 天前`
  return new Date(time).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}

export function truncate(text, max = 28) {
  const value = String(text || '')
    .replace(/\s+/g, ' ')
    .trim()
  return value.length > max ? `${value.slice(0, max)}…` : value
}

export async function copyText(text) {
  const value = String(text ?? '')
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(value)
      return true
    } catch (error) {
      /* 降级到 execCommand */
    }
  }
  try {
    const textarea = document.createElement('textarea')
    textarea.value = value
    textarea.setAttribute('readonly', '')
    textarea.style.position = 'fixed'
    textarea.style.top = '-9999px'
    document.body.appendChild(textarea)
    textarea.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(textarea)
    return ok
  } catch (error) {
    return false
  }
}
