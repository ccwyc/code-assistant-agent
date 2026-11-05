import { computed, ref } from 'vue'
import { newThreadId } from '../utils/format'

/**
 * 会话列表：前端保存「会话索引」（id / 标题 / 时间），消息正文由后端 checkpointer 持久化。
 * 索引落 localStorage，刷新后仍能看到历史会话列表。
 */
const THREADS_KEY = 'ca.threads.v1'
const ACTIVE_KEY = 'ca.activeThread.v1'
const MAX_THREADS = 50

function readThreads() {
  try {
    const raw = localStorage.getItem(THREADS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter((item) => item && typeof item.id === 'string' && item.id)
      .map((item) => ({
        id: item.id,
        title: item.title || '新对话',
        createdAt: item.createdAt || Date.now(),
        updatedAt: item.updatedAt || item.createdAt || Date.now(),
      }))
      .slice(0, MAX_THREADS)
  } catch (error) {
    return []
  }
}

function readActiveId() {
  try {
    return localStorage.getItem(ACTIVE_KEY) || ''
  } catch (error) {
    return ''
  }
}

const threads = ref(readThreads())
const activeId = ref(readActiveId())

const activeThread = computed(
  () => threads.value.find((item) => item.id === activeId.value) || null
)

function persist() {
  try {
    localStorage.setItem(THREADS_KEY, JSON.stringify(threads.value.slice(0, MAX_THREADS)))
  } catch (error) {
    /* 存储满/隐私模式忽略 */
  }
}

function persistActive() {
  try {
    localStorage.setItem(ACTIVE_KEY, activeId.value)
  } catch (error) {
    /* ignore */
  }
}

function sortByUpdated() {
  threads.value.sort((a, b) => b.updatedAt - a.updatedAt)
}

export function useThreads() {
  function createThread(title = '新对话') {
    const now = Date.now()
    const thread = {
      id: newThreadId(),
      title,
      createdAt: now,
      updatedAt: now,
    }
    threads.value.unshift(thread)
    activeId.value = thread.id
    sortByUpdated()
    persist()
    persistActive()
    return thread
  }

  function selectThread(id) {
    if (!threads.value.some((item) => item.id === id)) return
    activeId.value = id
    persistActive()
  }

  function renameThread(id, title) {
    const thread = threads.value.find((item) => item.id === id)
    if (!thread) return
    thread.title = title?.trim() ? title.trim().slice(0, 60) : thread.title
    persist()
  }

  function touchThread(id) {
    const thread = threads.value.find((item) => item.id === id)
    if (!thread) return
    thread.updatedAt = Date.now()
    sortByUpdated()
    persist()
  }

  function removeThread(id) {
    threads.value = threads.value.filter((item) => item.id !== id)
    if (activeId.value === id) {
      activeId.value = threads.value[0]?.id || ''
      persistActive()
    }
    persist()
    return threads.value
  }

  function ensureActive() {
    if (activeId.value && threads.value.some((item) => item.id === activeId.value)) {
      return threads.value.find((item) => item.id === activeId.value)
    }
    if (threads.value.length) {
      activeId.value = threads.value[0].id
      persistActive()
      return threads.value[0]
    }
    return createThread()
  }

  /** 只保留会话索引，避免列表无限增长；仅供测试/重置使用。 */
  function reset() {
    threads.value = []
    activeId.value = ''
    persist()
    persistActive()
  }

  return {
    threads,
    activeId,
    activeThread,
    createThread,
    selectThread,
    renameThread,
    touchThread,
    removeThread,
    ensureActive,
    reset,
  }
}
