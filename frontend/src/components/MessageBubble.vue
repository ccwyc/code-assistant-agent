<script setup>
import { computed, ref } from 'vue'
import MarkdownBody from './MarkdownBody.vue'
import ToolTrace from './ToolTrace.vue'
import ValidationCard from './ValidationCard.vue'
import { copyText, formatTime } from '../utils/format'

const props = defineProps({
  message: { type: Object, required: true },
})

const copied = ref(false)

const isUser = computed(() => props.message.role === 'user')
const elapsed = computed(() => {
  const ms = props.message.usage?.elapsed_ms
  if (!ms) return ''
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`
})

async function copyAll() {
  const ok = await copyText(props.message.content)
  copied.value = ok
  setTimeout(() => {
    copied.value = false
  }, 1600)
}
</script>

<template>
  <article class="msg" :class="isUser ? 'is-user' : 'is-assistant'">
    <div class="avatar" aria-hidden="true">
      <svg v-if="isUser" viewBox="0 0 24 24">
        <circle cx="12" cy="8.2" r="3.6" fill="none" stroke="currentColor" stroke-width="2" />
        <path d="M4.8 20c.7-3.6 3.6-5.6 7.2-5.6s6.5 2 7.2 5.6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
      </svg>
      <svg v-else viewBox="0 0 24 24">
        <rect x="4.2" y="7.4" width="15.6" height="11.4" rx="3.4" fill="none" stroke="currentColor" stroke-width="2" />
        <path d="M12 3.2v4.2M8.6 12.2v1.4M15.4 12.2v1.4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
        <path d="M9.4 15.6c.8.7 1.6 1 2.6 1s1.8-.3 2.6-1" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
      </svg>
    </div>

    <div class="body">
      <header class="meta">
        <span class="name">{{ isUser ? '你' : '代码助手' }}</span>
        <time>{{ formatTime(message.createdAt) }}</time>
        <span v-if="message.streaming" class="state is-live">
          <span class="dot"></span>{{ message.stopped ? '已停止' : '生成中' }}
        </span>
        <span v-else-if="message.stopped" class="state">已停止</span>
        <button
          v-if="message.content && !message.streaming"
          type="button"
          class="copy"
          :title="isUser ? '复制这条提问' : '复制完整回答'"
          @click="copyAll"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <rect x="9" y="9" width="10.4" height="10.4" rx="2.4" fill="none" stroke="currentColor" stroke-width="1.9" />
            <path d="M6.4 15H5.8A1.8 1.8 0 0 1 4 13.2V5.8A1.8 1.8 0 0 1 5.8 4h7.4A1.8 1.8 0 0 1 15 5.8v.6" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" />
          </svg>
          <span>{{ copied ? '已复制' : '复制' }}</span>
        </button>
      </header>

      <div v-if="message.error" class="msg-error">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2" />
          <path d="M12 7.5V13M12 16.6v.4" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" />
        </svg>
        <span>{{ message.error }}</span>
      </div>

      <p v-if="isUser" class="user-text">{{ message.content }}</p>
      <MarkdownBody v-else-if="message.content" :content="message.content" />

      <span v-if="message.streaming && !message.stopped" class="caret" aria-hidden="true"></span>

      <ToolTrace v-if="!isUser && message.tools.length" :tools="message.tools" />
      <ValidationCard v-if="!isUser && message.validation" :validation="message.validation" />

      <footer v-if="!isUser && (elapsed || message.usage)" class="msg-foot">
        <span v-if="elapsed">耗时 {{ elapsed }}</span>
        <span v-if="message.validation" class="sep">·</span>
        <span v-if="message.validation">
          {{ message.validation.valid ? '语法校验通过' : '语法校验未通过' }}
        </span>
      </footer>
    </div>
  </article>
</template>

<style scoped>
.msg {
  display: flex;
  gap: 13px;
  padding: 18px 0;
  animation: fade-up 0.28s var(--ease) both;
}

.msg + .msg {
  border-top: 1px solid var(--border);
}

.is-user {
  padding-top: 14px;
}

.avatar {
  flex: none;
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 11px;
  border: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text-muted);
  margin-top: 2px;
}

.is-user .avatar {
  color: #06111c;
  border-color: transparent;
  background: var(--accent-gradient);
}

.avatar svg {
  width: 19px;
  height: 19px;
}

.is-assistant .avatar {
  color: var(--accent);
  background: radial-gradient(120% 120% at 20% 0%, var(--accent-soft), var(--panel-2));
  border-color: rgba(34, 211, 238, 0.22);
}

.body {
  flex: 1;
  min-width: 0;
}

.meta {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 26px;
  margin-bottom: 4px;
}

.name {
  font-size: 13.5px;
  font-weight: 650;
  letter-spacing: 0.01em;
}

time {
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--text-faint);
}

.state {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11.5px;
  color: var(--text-faint);
}

.state.is-live {
  color: var(--accent);
}

.state .dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse-dot 1.1s ease-in-out infinite;
}

.copy {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 25px;
  padding: 0 8px;
  border-radius: 7px;
  border: 1px solid transparent;
  color: var(--text-faint);
  font-size: 11.5px;
  opacity: 0;
  transition:
    opacity 0.16s var(--ease),
    background 0.16s var(--ease),
    border-color 0.16s var(--ease),
    color 0.16s var(--ease);
}

.msg:hover .copy,
.copy:focus-visible {
  opacity: 1;
}

.copy:hover {
  background: var(--panel-2);
  border-color: var(--border);
  color: var(--text);
}

.copy svg {
  width: 13px;
  height: 13px;
}

.user-text {
  margin: 2px 0 0;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--panel-2);
  font-size: 14.5px;
  line-height: 1.7;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.msg-error {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 4px 0 6px;
  padding: 9px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(251, 113, 133, 0.3);
  background: var(--red-soft);
  color: var(--red);
  font-size: 13px;
  line-height: 1.6;
}

.msg-error svg {
  flex: none;
  width: 16px;
  height: 16px;
  margin-top: 1px;
}

.caret {
  display: inline-block;
  width: 8px;
  height: 1.1em;
  margin-left: 2px;
  vertical-align: text-bottom;
  border-radius: 2px;
  background: var(--accent);
  animation: blink 1s steps(1) infinite;
}

.msg-foot {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-faint);
}

.msg-foot .sep {
  opacity: 0.5;
}

/* 触屏设备没有 hover，复制按钮常驻显示 */
@media (hover: none) {
  .copy {
    opacity: 1;
  }
}
</style>
