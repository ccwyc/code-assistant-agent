<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import MessageBubble from './MessageBubble.vue'
import WelcomePanel from './WelcomePanel.vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  threadId: { type: String, default: '' },
  configured: { type: Boolean, default: true },
  online: { type: Boolean, default: false },
  model: { type: String, default: '' },
})

const emit = defineEmits(['example'])

const scrollEl = ref(null)
const innerEl = ref(null)
const stick = ref(true)
let observer = null

function nearBottom(el) {
  return el.scrollHeight - el.scrollTop - el.clientHeight < 90
}

function onScroll() {
  if (scrollEl.value) stick.value = nearBottom(scrollEl.value)
}

function scrollToBottom(smooth = false) {
  const el = scrollEl.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
  stick.value = true
}

onMounted(() => {
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(() => {
      if (stick.value) scrollToBottom()
    })
    if (innerEl.value) observer.observe(innerEl.value)
  }
  scrollToBottom()
})

onBeforeUnmount(() => observer?.disconnect())

watch(
  () => props.threadId,
  async () => {
    stick.value = true
    await nextTick()
    scrollToBottom()
  }
)

watch(
  () => props.messages.length,
  async (next, prev) => {
    if (next > prev) {
      stick.value = true
      await nextTick()
      scrollToBottom(true)
    }
  }
)

defineExpose({ scrollToBottom })
</script>

<template>
  <div class="messages-wrap">
    <div ref="scrollEl" class="messages" @scroll.passive="onScroll">
      <div ref="innerEl" class="messages-inner">
        <div v-if="loading" class="skeleton" aria-live="polite" aria-label="正在加载会话">
          <div class="sk-row" v-for="n in 3" :key="n" :style="{ animationDelay: `${n * 90}ms` }">
            <span class="sk-avatar"></span>
            <span class="sk-lines">
              <span class="sk-line w60"></span>
              <span class="sk-line w90"></span>
              <span class="sk-line w45"></span>
            </span>
          </div>
        </div>

        <WelcomePanel
          v-else-if="!messages.length"
          :configured="configured"
          :online="online"
          :model="model"
          @example="(payload) => emit('example', payload)"
        />

        <div v-else class="list">
          <MessageBubble v-for="message in messages" :key="message.id" :message="message" />
        </div>
      </div>
    </div>

    <transition name="jump">
      <button v-if="!stick && messages.length" type="button" class="jump-btn" @click="scrollToBottom(true)">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 5v14M6 13l6 6 6-6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        回到底部
      </button>
    </transition>
  </div>
</template>

<style scoped>
.messages-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
}

.messages {
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  scroll-behavior: smooth;
  padding: 0 28px;
}

.messages-inner {
  max-width: 860px;
  margin: 0 auto;
  padding-bottom: 28px;
}

.list {
  padding-top: 6px;
}

.skeleton {
  padding: 34px 6px;
  display: flex;
  flex-direction: column;
  gap: 26px;
}

.sk-row {
  display: flex;
  gap: 13px;
  animation: fade-up 0.3s var(--ease) both;
}

.sk-avatar {
  flex: none;
  width: 34px;
  height: 34px;
  border-radius: 11px;
  background: linear-gradient(90deg, var(--panel-2) 25%, var(--panel-3) 37%, var(--panel-2) 63%);
  background-size: 400% 100%;
  animation: shimmer 1.4s ease infinite;
}

.sk-lines {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 9px;
  padding-top: 4px;
}

.sk-line {
  height: 11px;
  border-radius: 6px;
  background: linear-gradient(90deg, var(--panel-2) 25%, var(--panel-3) 37%, var(--panel-2) 63%);
  background-size: 400% 100%;
  animation: shimmer 1.4s ease infinite;
}

.w60 {
  width: 60%;
}

.w90 {
  width: 90%;
}

.w45 {
  width: 45%;
}

@keyframes shimmer {
  0% {
    background-position: 100% 0;
  }
  100% {
    background-position: 0 0;
  }
}

.jump-btn {
  position: absolute;
  left: 50%;
  bottom: 16px;
  transform: translateX(-50%);
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 13px;
  border-radius: 999px;
  border: 1px solid var(--border-strong);
  background: var(--panel);
  color: var(--text-muted);
  font-size: 12px;
  box-shadow: var(--shadow-md);
  backdrop-filter: blur(8px);
}

.jump-btn:hover {
  color: var(--text);
  border-color: var(--accent);
}

.jump-btn svg {
  width: 13px;
  height: 13px;
}

.jump-enter-active,
.jump-leave-active {
  transition:
    opacity 0.18s var(--ease),
    transform 0.18s var(--ease);
}

.jump-enter-from,
.jump-leave-to {
  opacity: 0;
  transform: translate(-50%, 6px);
}

@media (max-width: 760px) {
  .messages {
    padding: 0 14px;
  }
}
</style>
