<script setup>
import { ref } from 'vue'

const props = defineProps({
  title: { type: String, default: '新对话' },
  messageCount: { type: Number, default: 0 },
  online: { type: Boolean, default: false },
  configured: { type: Boolean, default: false },
  model: { type: String, default: '' },
  theme: { type: String, default: 'dark' },
  canClear: { type: Boolean, default: false },
})

const emit = defineEmits(['menu', 'toggle-theme', 'clear'])

const confirming = ref(false)

function askClear() {
  if (!props.canClear) return
  confirming.value = true
}

function confirmClear() {
  confirming.value = false
  emit('clear')
}
</script>

<template>
  <header class="header">
    <button type="button" class="icon-btn menu" aria-label="打开会话列表" @click="emit('menu')">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 7h16M4 12h16M4 17h16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
      </svg>
    </button>

    <div class="title-block">
      <h1 :title="title">{{ title }}</h1>
      <p>
        <span>{{ messageCount }} 条消息</span>
        <span class="sep">/</span>
        <span class="mono">{{ model || 'deepseek' }}</span>
      </p>
    </div>

    <div class="actions">
      <span class="status" :class="{ ok: online && configured, warn: online && !configured, off: !online }">
        <span class="dot"></span>
        {{ !online ? '服务未连接' : configured ? '在线' : '未配置 Key' }}
      </span>

      <button
        type="button"
        class="icon-btn"
        :aria-label="theme === 'dark' ? '切换到亮色主题' : '切换到暗色主题'"
        :title="theme === 'dark' ? '亮色主题' : '暗色主题'"
        @click="emit('toggle-theme')"
      >
        <svg v-if="theme === 'dark'" viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="12" r="4.2" fill="none" stroke="currentColor" stroke-width="1.9" />
          <path d="M12 3v2.2M12 18.8V21M3 12h2.2M18.8 12H21M5.6 5.6l1.6 1.6M16.8 16.8l1.6 1.6M18.4 5.6l-1.6 1.6M7.2 16.8l-1.6 1.6" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" />
        </svg>
        <svg v-else viewBox="0 0 24 24" aria-hidden="true">
          <path d="M20 14.4A8.4 8.4 0 0 1 9.6 4a8.6 8.6 0 1 0 10.4 10.4Z" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round" />
        </svg>
      </button>

      <div class="clear-wrap">
        <button
          type="button"
          class="icon-btn danger"
          :disabled="!canClear"
          aria-label="清空当前会话"
          title="清空当前会话"
          @click="askClear"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M4.5 7h15M9.5 7V5.4c0-.8.6-1.4 1.4-1.4h2.2c.8 0 1.4.6 1.4 1.4V7M6.8 7l.8 11.4c.1 1 .9 1.6 1.9 1.6h5c1 0 1.8-.7 1.9-1.6L17.2 7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
            <path d="M10.4 11v6M13.6 11v6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
          </svg>
        </button>

        <transition name="pop">
          <div v-if="confirming" class="confirm">
            <span>清空当前会话？</span>
            <button type="button" class="mini danger" @click="confirmClear">清空</button>
            <button type="button" class="mini" @click="confirming = false">取消</button>
          </div>
        </transition>
      </div>
    </div>
  </header>
</template>

<style scoped>
.header {
  display: flex;
  align-items: center;
  gap: 12px;
  height: var(--header-h);
  padding: 0 22px;
  border-bottom: 1px solid var(--border);
  background: var(--bg);
  background: color-mix(in srgb, var(--bg) 82%, transparent);
  backdrop-filter: blur(12px);
  z-index: 5;
}

.menu {
  display: none;
}

.title-block {
  min-width: 0;
  flex: 1;
}

h1 {
  margin: 0;
  font-size: 15px;
  font-weight: 650;
  letter-spacing: -0.01em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.title-block p {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 1px 0 0;
  font-size: 11.5px;
  color: var(--text-faint);
}

.mono {
  font-family: var(--font-mono);
}

.sep {
  opacity: 0.5;
}

.actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 26px;
  padding: 0 10px;
  margin-right: 4px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text-faint);
  font-size: 11.5px;
  white-space: nowrap;
}

.status .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.status.ok {
  color: var(--green);
  border-color: var(--green-soft);
  background: var(--green-soft);
}

.status.ok .dot {
  box-shadow: 0 0 0 3px rgba(52, 211, 153, 0.14);
}

.status.warn {
  color: var(--amber);
  border-color: var(--amber-soft);
  background: var(--amber-soft);
}

.status.off {
  color: var(--red);
  border-color: var(--red-soft);
  background: var(--red-soft);
}

.icon-btn.danger:hover:not(:disabled) {
  color: var(--red);
  border-color: var(--red-soft);
  background: var(--red-soft);
}

.clear-wrap {
  position: relative;
}

.confirm {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-strong);
  background: var(--panel);
  box-shadow: var(--shadow-lg);
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
  z-index: 20;
}

.mini {
  height: 24px;
  padding: 0 9px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text);
  font-size: 11.5px;
}

.mini:hover {
  border-color: var(--border-strong);
}

.mini.danger {
  color: var(--red);
  border-color: var(--red-soft);
  background: var(--red-soft);
}

.pop-enter-active,
.pop-leave-active {
  transition:
    opacity 0.15s ease,
    transform 0.15s ease;
}

.pop-enter-from,
.pop-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

@media (max-width: 900px) {
  .menu {
    display: inline-flex;
  }

  .header {
    padding: 0 12px;
  }

  .status {
    display: none;
  }
}
</style>
