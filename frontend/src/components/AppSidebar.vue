<script setup>
import { computed, ref } from 'vue'
import { formatRelative, truncate } from '../utils/format'

const props = defineProps({
  threads: { type: Array, default: () => [] },
  activeId: { type: String, default: '' },
  online: { type: Boolean, default: false },
  configured: { type: Boolean, default: false },
  model: { type: String, default: '' },
  checking: { type: Boolean, default: false },
})

const emit = defineEmits(['new', 'select', 'delete', 'close'])

const query = ref('')
const pendingDelete = ref('')

const filtered = computed(() => {
  const keyword = query.value.trim().toLowerCase()
  if (!keyword) return props.threads
  return props.threads.filter((thread) => thread.title.toLowerCase().includes(keyword))
})

function askDelete(thread) {
  pendingDelete.value = thread.id
}

function confirmDelete(thread) {
  pendingDelete.value = ''
  emit('delete', thread.id)
}

function select(thread) {
  if (pendingDelete.value === thread.id) return
  emit('select', thread.id)
}
</script>

<template>
  <aside class="sidebar">
    <div class="brand">
      <div class="logo" aria-hidden="true">
        <svg viewBox="0 0 24 24">
          <path d="M8 7 4 12l4 5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
          <path d="M16 7l4 5-4 5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
          <path d="M13.4 5.5 10.6 18.5" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" opacity=".7" />
        </svg>
      </div>
      <div class="brand-text">
        <strong>代码助手</strong>
        <span>vibe-coding · V1.0</span>
      </div>
      <button type="button" class="icon-btn close" aria-label="关闭侧边栏" @click="emit('close')">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M6 6l12 12M18 6 6 18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
        </svg>
      </button>
    </div>

    <button type="button" class="new-chat" @click="emit('new')">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 5v14M5 12h14" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" />
      </svg>
      <span>新建对话</span>
      <kbd>Ctrl K</kbd>
    </button>

    <div v-if="threads.length > 4" class="search">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="11" cy="11" r="6.2" fill="none" stroke="currentColor" stroke-width="1.9" />
        <path d="m16 16 4 4" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" />
      </svg>
      <input v-model="query" type="search" placeholder="搜索会话" aria-label="搜索会话" />
    </div>

    <div class="section-head">
      <span>最近会话</span>
      <span class="count">{{ threads.length }}</span>
    </div>

    <nav class="thread-list" aria-label="会话列表">
      <div v-if="!filtered.length" class="empty">
        {{ threads.length ? '没有匹配的会话' : '还没有会话，点击上方新建' }}
      </div>

      <div
        v-for="thread in filtered"
        :key="thread.id"
        class="thread"
        :class="{ active: thread.id === activeId }"
        role="button"
        tabindex="0"
        @click="select(thread)"
        @keydown.enter.prevent="select(thread)"
        @keydown.space.prevent="select(thread)"
      >
        <span class="t-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24">
            <path d="M20 12a7.6 7.6 0 0 1-7.6 7.6H6.4L4 21.2V12a7.6 7.6 0 0 1 7.6-7.6H12A7.6 7.6 0 0 1 20 12Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" />
          </svg>
        </span>
        <span class="t-body">
          <span class="t-title">{{ truncate(thread.title, 30) }}</span>
          <span class="t-meta">{{ formatRelative(thread.updatedAt) }}</span>
        </span>

        <button
          type="button"
          class="t-del"
          aria-label="删除会话"
          title="删除会话"
          @click.stop="askDelete(thread)"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M5 7h14M9.6 7V5.6c0-.7.6-1.3 1.3-1.3h2.2c.7 0 1.3.6 1.3 1.3V7M7 7l.7 11.2c.1.9.8 1.6 1.7 1.6h5.2c.9 0 1.6-.7 1.7-1.6L17 7" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>

        <div v-if="pendingDelete === thread.id" class="t-confirm" @click.stop>
          <span>删除？</span>
          <button type="button" class="yes" @click.stop="confirmDelete(thread)">删除</button>
          <button type="button" class="no" @click.stop="pendingDelete = ''">取消</button>
        </div>
      </div>
    </nav>

    <footer class="footer">
      <div class="status-line">
        <span class="dot" :class="!online ? 'off' : configured ? 'ok' : 'warn'"></span>
        <div class="status-text">
          <strong>{{ !online ? '服务未连接' : configured ? '服务在线' : '未配置 API Key' }}</strong>
          <small :title="model">{{ model || '正在检测后端…' }}</small>
        </div>
        <span v-if="checking" class="pulse"></span>
      </div>
      <p class="foot-hint">生成 → 校验 → 修正 · 多轮上下文</p>
    </footer>
  </aside>
</template>

<style scoped>
.sidebar {
  display: flex;
  flex-direction: column;
  width: var(--sidebar-w);
  height: 100%;
  padding: 14px 12px 12px;
  border-right: 1px solid var(--border);
  background: var(--bg-elev);
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 6px 14px;
}

.logo {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: var(--panel-2);
  border: 1px solid var(--border);
  color: var(--accent);
}

.logo svg {
  width: 22px;
  height: 22px;
}

.brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
  min-width: 0;
}

.brand-text strong {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.brand-text span {
  font-size: 10.5px;
  color: var(--text-faint);
  font-family: var(--font-mono);
  letter-spacing: 0.02em;
}

.close {
  display: none;
  margin-left: auto;
}

.new-chat {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 38px;
  padding: 0 12px;
  border-radius: var(--radius-sm);
  background: var(--accent-gradient);
  color: #06111c;
  font-size: 13px;
  font-weight: 650;
  box-shadow: 0 10px 24px -16px rgba(99, 102, 241, 0.9);
  transition:
    filter 0.16s var(--ease),
    transform 0.16s var(--ease);
}

.new-chat:hover {
  filter: brightness(1.07);
  transform: translateY(-1px);
}

.new-chat svg {
  width: 16px;
  height: 16px;
}

.new-chat kbd {
  margin-left: auto;
  padding: 1px 5px;
  border-radius: 5px;
  background: rgba(6, 17, 28, 0.16);
  font-family: var(--font-mono);
  font-size: 10px;
}

.search {
  position: relative;
  margin-top: 10px;
}

.search svg {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  width: 14px;
  height: 14px;
  color: var(--text-faint);
  pointer-events: none;
}

.search input {
  width: 100%;
  height: 32px;
  padding: 0 10px 0 30px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text);
  font-size: 12.5px;
  outline: none;
}

.search input::placeholder {
  color: var(--text-faint);
}

.search input:focus {
  border-color: var(--accent);
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 8px 7px;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-faint);
}

.section-head .count {
  font-family: var(--font-mono);
  letter-spacing: 0;
}

.thread-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-right: 2px;
}

.empty {
  padding: 14px 10px;
  font-size: 12px;
  color: var(--text-faint);
  line-height: 1.7;
}

.thread {
  position: relative;
  display: flex;
  align-items: center;
  gap: 9px;
  min-height: 44px;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  cursor: pointer;
  transition:
    background 0.15s var(--ease),
    border-color 0.15s var(--ease);
}

.thread:hover {
  background: var(--panel-2);
}

.thread.active {
  background: var(--accent-soft);
  border-color: rgba(34, 211, 238, 0.22);
}

.thread.active::before {
  content: '';
  position: absolute;
  left: -1px;
  top: 12px;
  bottom: 12px;
  width: 2px;
  border-radius: 2px;
  background: var(--accent);
}

.t-icon {
  flex: none;
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text-faint);
}

.thread.active .t-icon {
  background: var(--panel);
  color: var(--accent);
}

.t-icon svg {
  width: 14px;
  height: 14px;
}

.t-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  line-height: 1.35;
}

.t-title {
  font-size: 12.8px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.thread.active .t-title,
.thread:hover .t-title {
  color: var(--text);
}

.t-meta {
  font-size: 10.5px;
  color: var(--text-faint);
}

.t-del {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  color: var(--text-faint);
  opacity: 0;
  transition:
    opacity 0.15s var(--ease),
    color 0.15s var(--ease),
    background 0.15s var(--ease);
}

.thread:hover .t-del {
  opacity: 1;
}

.t-del:hover {
  color: var(--red);
  background: var(--red-soft);
}

.t-del svg {
  width: 14px;
  height: 14px;
}

.t-confirm {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  padding: 0 8px;
  border-radius: var(--radius-sm);
  background: var(--panel-3);
  border: 1px solid var(--red-soft);
  font-size: 11.5px;
  color: var(--text-muted);
}

.t-confirm button {
  height: 22px;
  padding: 0 7px;
  border-radius: 5px;
  font-size: 11px;
  border: 1px solid var(--border);
  background: var(--panel);
  color: var(--text);
}

.t-confirm .yes {
  color: var(--red);
  border-color: var(--red-soft);
  background: var(--red-soft);
}

.footer {
  padding: 12px 8px 4px;
  border-top: 1px solid var(--border);
  margin-top: 8px;
}

.status-line {
  display: flex;
  align-items: center;
  gap: 9px;
}

.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex: none;
}

.dot.ok {
  background: var(--green);
  box-shadow: 0 0 0 3px rgba(52, 211, 153, 0.14);
}

.dot.warn {
  background: var(--amber);
  box-shadow: 0 0 0 3px rgba(251, 191, 36, 0.14);
}

.dot.off {
  background: var(--red);
  box-shadow: 0 0 0 3px rgba(251, 113, 133, 0.14);
}

.status-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.4;
}

.status-text strong {
  font-size: 12px;
  font-weight: 600;
}

.status-text small {
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--text-faint);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pulse {
  margin-left: auto;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid var(--border-strong);
  border-top-color: var(--accent);
  animation: spin 0.9s linear infinite;
}

.foot-hint {
  margin: 8px 0 0;
  font-size: 10.5px;
  color: var(--text-faint);
}

@media (max-width: 900px) {
  .sidebar {
    width: min(86vw, 300px);
  }

  .close {
    display: inline-flex;
  }
}
</style>
