<script setup>
import { computed, nextTick, ref, watch } from 'vue'

const props = defineProps({
  disabled: { type: Boolean, default: false },
  language: { type: String, default: 'auto' },
  streaming: { type: Boolean, default: true },
  phase: { type: String, default: '' },
  maxLength: { type: Number, default: 20000 },
})

const emit = defineEmits(['send', 'stop', 'update:language', 'update:streaming'])

const LANGUAGES = [
  { value: 'auto', label: '自动' },
  { value: 'python', label: 'Python' },
  { value: 'java', label: 'Java' },
  { value: 'javascript', label: 'JS' },
]

const PLACEHOLDERS = {
  auto: '描述你的需求，例如：写一个带缓存的斐波那契数列，并解释复杂度…',
  python: '用 Python 实现…（Enter 发送，Shift + Enter 换行）',
  java: '用 Java 实现…（Enter 发送，Shift + Enter 换行）',
  javascript: '用 JavaScript 实现…（Enter 发送，Shift + Enter 换行）',
}

const text = ref('')
const textarea = ref(null)
const focused = ref(false)

const canSend = computed(() => !props.disabled && text.value.trim().length > 0)
const placeholder = computed(() => PLACEHOLDERS[props.language] || PLACEHOLDERS.auto)
const length = computed(() => text.value.length)

function resize() {
  const el = textarea.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 200)}px`
}

watch(text, () => nextTick(resize))

function submit() {
  if (!canSend.value) return
  const value = text.value.trim()
  if (!value) return
  text.value = ''
  nextTick(resize)
  emit('send', value)
}

function onKeydown(event) {
  if (event.key !== 'Enter') return
  if (event.shiftKey) return
  if (event.isComposing || event.keyCode === 229) return
  event.preventDefault()
  submit()
}

function setText(value) {
  text.value = value
  nextTick(() => {
    resize()
    textarea.value?.focus()
  })
}

function focus() {
  textarea.value?.focus()
}

function pickLanguage(value) {
  emit('update:language', value)
  focus()
}

function toggleStream() {
  emit('update:streaming', !props.streaming)
}

defineExpose({ focus, setText })
</script>

<template>
  <div class="composer">
    <transition name="phase">
      <div v-if="phase" class="phase" aria-live="polite">
        <span class="phase-dot"></span>
        {{ phase }}
      </div>
    </transition>

    <div class="box" :class="{ focused, busy: disabled }">
      <textarea
        ref="textarea"
        v-model="text"
        class="input"
        rows="1"
        :placeholder="placeholder"
        :maxlength="maxLength"
        spellcheck="false"
        aria-label="输入你的问题"
        @keydown="onKeydown"
        @focus="focused = true"
        @blur="focused = false"
      ></textarea>

      <div class="actions">
        <div class="left">
          <div class="lang-group" role="group" aria-label="目标语言">
            <button
              v-for="option in LANGUAGES"
              :key="option.value"
              type="button"
              class="lang"
              :class="{ active: language === option.value }"
              @click="pickLanguage(option.value)"
            >
              {{ option.label }}
            </button>
          </div>

          <button
            type="button"
            class="stream-toggle"
            :class="{ on: streaming }"
            :aria-pressed="streaming"
            title="流式输出：逐字返回，可随时停止"
            @click="toggleStream"
          >
            <span class="track"><span class="knob"></span></span>
            流式
          </button>
        </div>

        <div class="right">
          <span v-if="length > 0" class="count" :class="{ limit: length > maxLength * 0.9 }">
            {{ length }}
          </span>

          <button
            v-if="!disabled"
            type="button"
            class="send"
            :disabled="!canSend"
            title="发送（Enter）"
            aria-label="发送"
            @click="submit"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M4.5 12h14M12.5 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </button>

          <button v-else type="button" class="stop" title="停止生成（Esc）" aria-label="停止生成" @click="emit('stop')">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" />
            </svg>
          </button>
        </div>
      </div>
    </div>

    <p class="hint">
      <span><kbd>Enter</kbd> 发送</span>
      <span><kbd>Shift</kbd> + <kbd>Enter</kbd> 换行</span>
      <span><kbd>Esc</kbd> 停止</span>
      <span class="hint-accent">生成后自动做静态语法校验</span>
    </p>
  </div>
</template>

<style scoped>
.composer {
  padding: 10px 28px calc(16px + env(safe-area-inset-bottom));
  background: linear-gradient(180deg, transparent, var(--bg) 26%);
}

.phase {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin: 0 auto 8px;
  padding: 4px 11px;
  border-radius: 999px;
  border: 1px solid var(--accent-soft);
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 12px;
  width: fit-content;
}

.phase-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse-dot 1s ease-in-out infinite;
}

.box {
  max-width: 860px;
  margin: 0 auto;
  padding: 10px 10px 8px 14px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  background: var(--panel);
  box-shadow: var(--shadow-md);
  transition:
    border-color 0.2s var(--ease),
    box-shadow 0.2s var(--ease);
}

.box.focused {
  border-color: rgba(34, 211, 238, 0.45);
  box-shadow:
    0 0 0 3px var(--accent-soft),
    var(--shadow-md);
}

.box.busy {
  border-color: rgba(34, 211, 238, 0.3);
}

.input {
  display: block;
  width: 100%;
  min-height: 26px;
  max-height: 200px;
  padding: 4px 4px 6px;
  border: 0;
  background: transparent;
  color: var(--text);
  font-size: 14.5px;
  line-height: 1.7;
  resize: none;
  outline: none;
  overflow-y: auto;
}

.input::placeholder {
  color: var(--text-faint);
}

.actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding-top: 6px;
}

.left,
.right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.lang-group {
  display: inline-flex;
  padding: 3px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--panel-2);
}

.lang {
  height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  color: var(--text-faint);
  font-size: 11.8px;
  font-weight: 500;
  transition:
    color 0.16s var(--ease),
    background 0.16s var(--ease);
}

.lang:hover {
  color: var(--text);
}

.lang.active {
  background: var(--panel-3);
  color: var(--text);
  box-shadow: var(--shadow-sm);
}

.stream-toggle {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 27px;
  padding: 0 9px 0 6px;
  border-radius: 999px;
  color: var(--text-faint);
  font-size: 11.8px;
  transition: color 0.16s var(--ease);
}

.stream-toggle:hover {
  color: var(--text);
}

.stream-toggle.on {
  color: var(--accent);
}

.track {
  position: relative;
  width: 26px;
  height: 15px;
  border-radius: 999px;
  background: var(--panel-3);
  border: 1px solid var(--border);
  transition: background 0.18s var(--ease);
}

.stream-toggle.on .track {
  background: var(--accent-soft);
  border-color: rgba(34, 211, 238, 0.4);
}

.knob {
  position: absolute;
  top: 1px;
  left: 1px;
  width: 11px;
  height: 11px;
  border-radius: 50%;
  background: var(--text-faint);
  transition:
    transform 0.18s var(--ease),
    background 0.18s var(--ease);
}

.stream-toggle.on .knob {
  transform: translateX(11px);
  background: var(--accent);
}

.count {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-faint);
}

.count.limit {
  color: var(--amber);
}

.send,
.stop {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 12px;
  transition:
    transform 0.16s var(--ease),
    opacity 0.16s var(--ease),
    filter 0.16s var(--ease);
}

.send {
  background: var(--accent-gradient);
  color: #06111c;
  box-shadow: 0 8px 22px -12px rgba(99, 102, 241, 0.9);
}

.send:hover:not(:disabled) {
  filter: brightness(1.08);
  transform: translateY(-1px);
}

.send:disabled {
  opacity: 0.35;
  box-shadow: none;
}

.send svg,
.stop svg {
  width: 19px;
  height: 19px;
}

.stop {
  background: var(--panel-3);
  border: 1px solid var(--border-strong);
  color: var(--red);
}

.stop:hover {
  border-color: var(--red);
}

.hint {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 14px;
  max-width: 860px;
  margin: 9px auto 0;
  color: var(--text-faint);
  font-size: 11.5px;
}

.hint span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.hint kbd {
  padding: 1px 5px;
  border-radius: 5px;
  border: 1px solid var(--border);
  background: var(--panel-2);
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--text-muted);
}

.hint-accent {
  margin-left: auto;
  color: var(--accent);
  opacity: 0.8;
}

.phase-enter-active,
.phase-leave-active {
  transition:
    opacity 0.18s ease,
    transform 0.18s ease;
}

.phase-enter-from,
.phase-leave-to {
  opacity: 0;
  transform: translateY(4px);
}

@media (max-width: 760px) {
  .composer {
    padding: 8px 12px calc(12px + env(safe-area-inset-bottom));
  }

  .hint {
    display: none;
  }

  .lang {
    padding: 0 8px;
  }
}
</style>
