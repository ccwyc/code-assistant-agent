<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import AppSidebar from './components/AppSidebar.vue'
import ChatHeader from './components/ChatHeader.vue'
import MessageList from './components/MessageList.vue'
import ChatComposer from './components/ChatComposer.vue'
import ToastStack from './components/ToastStack.vue'
import { useChat } from './composables/useChat'
import { useHealth } from './composables/useHealth'
import { useTheme } from './composables/useTheme'
import { useThreads } from './composables/useThreads'
import { truncate } from './utils/format'

const {
  threads,
  activeId,
  activeThread,
  createThread,
  selectThread,
  renameThread,
  touchThread,
  removeThread,
  ensureActive,
} = useThreads()

const chat = useChat()
const { checking, online, configured, model, check, start, stop } = useHealth()
const { theme, toggle: toggleTheme } = useTheme()

const LANGUAGE_KEY = 'ca.language.v1'
const STREAM_KEY = 'ca.stream.v1'

const language = ref(localStorage.getItem(LANGUAGE_KEY) || 'auto')
const streaming = ref(localStorage.getItem(STREAM_KEY) !== '0')
const sidebarOpen = ref(false)
const composerRef = ref(null)
const toasts = ref([])

watch(language, (value) => localStorage.setItem(LANGUAGE_KEY, value))
watch(streaming, (value) => localStorage.setItem(STREAM_KEY, value ? '1' : '0'))

const title = computed(() => activeThread.value?.title || '新对话')
const messageCount = computed(() => chat.messages.value.length)
const canClear = computed(() => chat.messages.value.length > 0 && !chat.sending.value)

let toastSeq = 0

function toast(text, { title: heading = '', type = 'error', timeout = 5000 } = {}) {
  const id = ++toastSeq
  toasts.value.push({ id, text, title: heading, type })
  if (timeout > 0) {
    setTimeout(() => dismiss(id), timeout)
  }
}

function dismiss(id) {
  toasts.value = toasts.value.filter((item) => item.id !== id)
}

async function handleSend(text) {
  if (chat.sending.value) return
  const isFirstTurn = !chat.messages.value.some((message) => message.role === 'user')
  const thread = ensureActive()
  if (isFirstTurn) renameThread(thread.id, truncate(text, 28))

  await chat.send({
    threadId: thread.id,
    text,
    language: language.value,
    stream: streaming.value,
  })
  touchThread(thread.id)

  if (chat.error.value) {
    toast(chat.error.value.message, { title: '请求失败' })
  }
}

async function handleSelect(id) {
  sidebarOpen.value = false
  if (id === activeId.value) return
  chat.stop()
  selectThread(id)
  await chat.loadHistory(id)
  composerRef.value?.focus()
}

function handleNew() {
  chat.stop()
  chat.clear()
  createThread()
  sidebarOpen.value = false
  composerRef.value?.focus()
}

async function handleDelete(id) {
  const wasActive = id === activeId.value
  const ok = await chat.deleteRemote(id)
  removeThread(id)

  if (!ok) {
    toast('删除失败：后端未响应，已从本地列表移除', { title: '会话删除' })
  }

  if (wasActive) {
    const next = ensureActive()
    await chat.loadHistory(next.id)
  }
}

async function handleClear() {
  const id = activeId.value
  if (!id) return
  chat.stop()
  await chat.deleteRemote(id)
  chat.clear()
  renameThread(id, '新对话')
  touchThread(id)
  toast('当前会话已清空', { title: '已完成', type: 'success', timeout: 2400 })
}

function handleExample({ text, language: exampleLanguage }) {
  if (exampleLanguage) language.value = exampleLanguage
  composerRef.value?.setText(text)
}

function onKeydown(event) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    handleNew()
    return
  }
  if (event.key === 'Escape') {
    if (chat.sending.value) {
      chat.stop()
    } else if (sidebarOpen.value) {
      sidebarOpen.value = false
    }
  }
}

onMounted(async () => {
  start()
  const thread = ensureActive()
  if (thread?.id) await chat.loadHistory(thread.id)
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('focus', check)
})

onBeforeUnmount(() => {
  stop()
  chat.stop()
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('focus', check)
})
</script>

<template>
  <div class="app" :class="{ 'sidebar-open': sidebarOpen }">
    <div class="sidebar-slot">
      <AppSidebar
        :threads="threads"
        :active-id="activeId"
        :online="online"
        :configured="configured"
        :model="model"
        :checking="checking"
        @new="handleNew"
        @select="handleSelect"
        @delete="handleDelete"
        @close="sidebarOpen = false"
      />
    </div>

    <transition name="fade">
      <div v-if="sidebarOpen" class="backdrop" @click="sidebarOpen = false"></div>
    </transition>

    <main class="main">
      <div class="glow" aria-hidden="true"></div>

      <ChatHeader
        :title="title"
        :message-count="messageCount"
        :online="online"
        :configured="configured"
        :model="model"
        :theme="theme"
        :can-clear="canClear"
        @menu="sidebarOpen = true"
        @toggle-theme="toggleTheme"
        @clear="handleClear"
      />

      <MessageList
        :messages="chat.messages.value"
        :loading="chat.loading.value"
        :thread-id="activeId"
        :configured="configured"
        :online="online"
        :model="model"
        @example="handleExample"
      />

      <ChatComposer
        ref="composerRef"
        :disabled="chat.sending.value"
        :language="language"
        :streaming="streaming"
        :phase="chat.phase.value"
        @send="handleSend"
        @stop="chat.stop()"
        @update:language="language = $event"
        @update:streaming="streaming = $event"
      />
    </main>

    <ToastStack :items="toasts" @dismiss="dismiss" />
  </div>
</template>

<style scoped>
.app {
  display: flex;
  height: 100%;
  background: var(--bg);
  overflow: hidden;
}

.sidebar-slot {
  flex: none;
  height: 100%;
}

.main {
  position: relative;
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.glow {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(60% 45% at 78% -8%, rgba(99, 102, 241, 0.16), transparent 62%),
    radial-gradient(50% 40% at 12% 0%, rgba(34, 211, 238, 0.1), transparent 60%);
  z-index: 0;
}

.main > :not(.glow) {
  position: relative;
  z-index: 1;
}

.backdrop {
  display: none;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

@media (max-width: 900px) {
  .sidebar-slot {
    position: fixed;
    top: 0;
    bottom: 0;
    left: 0;
    z-index: 60;
    transform: translateX(-102%);
    transition: transform 0.26s var(--ease);
  }

  .app.sidebar-open .sidebar-slot {
    transform: none;
  }

  .backdrop {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 50;
    background: rgba(3, 7, 13, 0.62);
    backdrop-filter: blur(3px);
  }
}
</style>
