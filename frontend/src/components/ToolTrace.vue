<script setup>
import { ref } from 'vue'

const props = defineProps({
  tools: { type: Array, default: () => [] },
})

const openId = ref('')

const LABELS = {
  validate_code: '语法校验',
  review_code: '代码评审',
}

function labelOf(tool) {
  return LABELS[tool.name] || tool.name || '工具'
}

function verdictOf(tool) {
  if (tool.status === 'running') return '校验中…'
  if (tool.valid === true) return '通过'
  if (tool.valid === false) return '未通过'
  return '已完成'
}

function toneOf(tool) {
  if (tool.status === 'running') return 'running'
  if (tool.valid === true) return 'ok'
  if (tool.valid === false) return 'bad'
  return 'done'
}

function toggle(id) {
  openId.value = openId.value === id ? '' : id
}

function activeTool() {
  return props.tools.find((tool) => tool.id === openId.value) || null
}
</script>

<template>
  <div v-if="tools.length" class="tool-trace">
    <button
      v-for="tool in tools"
      :key="tool.id"
      type="button"
      class="tool-pill"
      :class="toneOf(tool)"
      :aria-expanded="openId === tool.id"
      @click="toggle(tool.id)"
    >
      <span class="tool-icon" aria-hidden="true">
        <svg v-if="tool.status === 'running'" viewBox="0 0 24 24" class="spin">
          <circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-dasharray="24 14" />
        </svg>
        <svg v-else-if="tool.valid === true" viewBox="0 0 24 24">
          <path d="M5 12.5l4.5 4.5L19 6.5" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        <svg v-else-if="tool.valid === false" viewBox="0 0 24 24">
          <path d="M6 6l12 12M18 6L6 18" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" />
        </svg>
        <svg v-else viewBox="0 0 24 24">
          <path d="M5 12.5l4.5 4.5L19 6.5" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </span>
      <span class="tool-name">{{ labelOf(tool) }}</span>
      <span class="tool-verdict">{{ verdictOf(tool) }}</span>
      <svg class="tool-caret" :class="{ open: openId === tool.id }" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M9 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>

    <transition name="detail">
      <pre v-if="activeTool()" class="tool-detail">{{ activeTool().content || '（无输出）' }}</pre>
    </transition>
  </div>
</template>

<style scoped>
.tool-trace {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 10px 0 2px;
}

.tool-pill {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 27px;
  padding: 0 9px 0 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text-muted);
  font-size: 12px;
  transition:
    border-color 0.16s var(--ease),
    background 0.16s var(--ease),
    color 0.16s var(--ease);
}

.tool-pill:hover {
  border-color: var(--border-strong);
  color: var(--text);
}

.tool-pill.ok {
  color: var(--green);
  border-color: var(--green-soft);
  background: var(--green-soft);
}

.tool-pill.bad {
  color: var(--red);
  border-color: var(--red-soft);
  background: var(--red-soft);
}

.tool-pill.running {
  color: var(--accent);
  border-color: var(--accent-soft);
  background: var(--accent-soft);
}

.tool-icon {
  display: inline-flex;
  width: 13px;
  height: 13px;
}

.tool-icon svg {
  width: 100%;
  height: 100%;
}

.tool-name {
  font-weight: 600;
  letter-spacing: 0.01em;
}

.tool-verdict {
  opacity: 0.85;
}

.tool-caret {
  width: 12px;
  height: 12px;
  opacity: 0.5;
  transition: transform 0.18s var(--ease);
}

.tool-caret.open {
  transform: rotate(90deg);
}

.tool-detail {
  flex-basis: 100%;
  margin: 0;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--code-bg);
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
  max-height: 240px;
  overflow: auto;
  white-space: pre-wrap;
}

.spin {
  animation: spin 0.9s linear infinite;
  transform-origin: center;
}

.detail-enter-active,
.detail-leave-active {
  transition: opacity 0.16s ease;
}

.detail-enter-from,
.detail-leave-to {
  opacity: 0;
}
</style>
