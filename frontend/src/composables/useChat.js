import { computed, ref } from 'vue'
import { fetchHistory, removeThread, sendChat, streamChat } from '../api/client'
import { uid } from '../utils/format'

/**
 * 对话状态机：
 * - 发送时先落一条 user 消息和一条空的 assistant 消息（streaming=true）；
 * - 流式事件增量写入 assistant.content / tools / validation；
 * - 取消（AbortController）后保留已生成内容并标记 stopped；
 * - 每个会话额外做一份 localStorage 缓存，后端重启导致历史为空时兜底展示。
 */
const CACHE_PREFIX = 'ca.msgs.v1.'

function readCache(threadId) {
  try {
    const raw = localStorage.getItem(`${CACHE_PREFIX}${threadId}`)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter((item) => item && (item.role === 'user' || item.role === 'assistant'))
      .map((item) => ({
        id: item.id || uid('msg'),
        role: item.role,
        content: item.content || '',
        createdAt: item.createdAt || Date.now(),
        streaming: false,
        stopped: Boolean(item.stopped),
        tools: Array.isArray(item.tools) ? item.tools : [],
        validation: item.validation || null,
        usage: item.usage || null,
        error: item.error || null,
        cached: true,
      }))
  } catch (error) {
    return []
  }
}

function writeCache(threadId, messages) {
  if (!threadId) return
  try {
    const payload = messages
      .filter((item) => !item.streaming)
      .slice(-40)
      .map((item) => ({
        id: item.id,
        role: item.role,
        content: item.content,
        createdAt: item.createdAt,
        stopped: item.stopped,
        tools: item.tools,
        validation: item.validation,
        usage: item.usage,
        error: item.error,
      }))
    localStorage.setItem(`${CACHE_PREFIX}${threadId}`, JSON.stringify(payload))
  } catch (error) {
    /* ignore quota errors */
  }
}

function clearCache(threadId) {
  try {
    localStorage.removeItem(`${CACHE_PREFIX}${threadId}`)
  } catch (error) {
    /* ignore */
  }
}

function createMessage(role, content = '') {
  return {
    id: uid('msg'),
    role,
    content,
    createdAt: Date.now(),
    streaming: false,
    stopped: false,
    tools: [],
    validation: null,
    usage: null,
    error: null,
    cached: false,
  }
}

export function useChat() {
  const messages = ref([])
  const sending = ref(false)
  const loading = ref(false)
  const phase = ref('')
  const error = ref(null)

  let controller = null

  const canSend = computed(() => !sending.value)

  function clear() {
    stop()
    messages.value = []
    error.value = null
    phase.value = ''
  }

  function stop() {
    if (controller) {
      controller.abort()
      controller = null
    }
  }

  function markToolsDone(assistant) {
    for (const tool of assistant.tools) {
      if (tool.status === 'running') tool.status = 'done'
    }
  }

  function applyEvent(assistant, { event, data }) {
    switch (event) {
      case 'meta':
        break
      case 'token': {
        const content = typeof data === 'string' ? data : data?.content
        if (content) assistant.content += content
        break
      }
      case 'tool_call': {
        const name = data?.name || 'tool'
        assistant.tools.push({
          id: uid('tool'),
          name,
          args: data?.args || {},
          status: 'running',
          valid: null,
          content: '',
        })
        phase.value = name === 'validate_code' ? '正在做静态校验…' : '正在调用工具…'
        break
      }
      case 'tool_result': {
        const target = [...assistant.tools]
          .reverse()
          .find((tool) => tool.status === 'running' && (!data?.name || tool.name === data.name))
        if (target) {
          target.status = 'done'
          target.valid = data?.valid ?? null
          target.content = data?.content || ''
        }
        phase.value = ''
        break
      }
      case 'done': {
        const payload = data || {}
        if (payload.answer) assistant.content = payload.answer
        if (payload.validation) assistant.validation = payload.validation
        if (payload.usage) assistant.usage = payload.usage
        markToolsDone(assistant)
        phase.value = ''
        break
      }
      case 'error': {
        assistant.error = data?.detail || '模型调用失败'
        if (data?.hint) assistant.error += `（${data.hint}）`
        markToolsDone(assistant)
        phase.value = ''
        break
      }
      default:
        break
    }
  }

  async function send({ threadId, text, language = 'auto', stream = true }) {
    if (sending.value || !threadId) return
    const content = String(text || '').trim()
    if (!content) return

    error.value = null
    phase.value = ''
    messages.value.push(createMessage('user', content))
    messages.value.push({ ...createMessage('assistant'), streaming: true })

    // 必须通过数组代理拿到响应式对象：直接改 push 进去的原始对象不会触发视图更新，
    // 流式 token 就会「只在数据里、不在界面上」。
    const assistant = messages.value[messages.value.length - 1]

    controller = new AbortController()
    sending.value = true

    try {
      if (stream) {
        await streamChat({
          threadId,
          message: content,
          language: language === 'auto' ? null : language,
          signal: controller.signal,
          onEvent: (payload) => applyEvent(assistant, payload),
        })
      } else {
        const result = await sendChat({
          threadId,
          message: content,
          language: language === 'auto' ? null : language,
          signal: controller.signal,
        })
        assistant.content = result.answer || ''
        assistant.validation = result.validation || null
        assistant.usage = result.usage || null
      }
    } catch (err) {
      if (err?.name === 'AbortError') {
        assistant.stopped = true
      } else {
        assistant.error = err?.message || '请求失败'
        if (err?.hint) assistant.error += `（${err.hint}）`
        error.value = err
      }
    } finally {
      assistant.streaming = false
      assistant.cached = false
      if (!assistant.content && !assistant.error) {
        assistant.content = assistant.stopped ? '（已停止生成）' : '（未收到内容，请重试）'
      }
      sending.value = false
      phase.value = ''
      controller = null
      writeCache(threadId, messages.value)
    }
  }

  async function loadHistory(threadId) {
    if (!threadId) {
      messages.value = []
      return []
    }
    loading.value = true
    error.value = null
    try {
      const data = await fetchHistory(threadId)
      const items = (data?.messages || []).filter(
        (item) => item && (item.role === 'user' || item.role === 'assistant')
      )
      if (items.length) {
        messages.value = items.map((item) => {
          const message = createMessage(item.role, item.content || '')
          message.createdAt = Date.now()
          message.cached = false
          return message
        })
        writeCache(threadId, messages.value)
      } else {
        messages.value = readCache(threadId)
      }
    } catch (err) {
      messages.value = readCache(threadId)
      if (err?.name !== 'AbortError') error.value = err
    } finally {
      loading.value = false
    }
    return messages.value
  }

  async function deleteRemote(threadId) {
    clearCache(threadId)
    try {
      await removeThread(threadId)
      return true
    } catch (err) {
      if (err?.status === 404) return true
      error.value = err
      return false
    }
  }

  return {
    messages,
    sending,
    loading,
    phase,
    error,
    canSend,
    send,
    stop,
    clear,
    loadHistory,
    deleteRemote,
    hasMessages: computed(() => messages.value.length > 0),
  }
}
