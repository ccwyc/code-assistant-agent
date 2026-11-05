<script setup>
import { computed, ref } from 'vue'
import { languageLabel } from '../utils/markdown'

const props = defineProps({
  validation: { type: Object, required: true },
})

const expanded = ref(props.validation.valid !== true)

const valid = computed(() => props.validation.valid === true)
const errors = computed(() => props.validation.errors || [])
const warnings = computed(() => props.validation.warnings || [])
const suggestion = computed(() => props.validation.suggestion || '')
const language = computed(() => languageLabel(props.validation.language || ''))
const checker = computed(() => props.validation.checker || 'static')
const title = computed(() =>
  valid.value ? '语法校验通过' : `语法校验未通过 · ${errors.value.length} 个问题`
)

function locationOf(issue) {
  if (issue.line == null) return '全局'
  return issue.column != null ? `L${issue.line}:${issue.column}` : `L${issue.line}`
}
</script>

<template>
  <section class="validation" :class="valid ? 'is-ok' : 'is-bad'">
    <button type="button" class="v-head" @click="expanded = !expanded">
      <span class="v-icon" aria-hidden="true">
        <svg v-if="valid" viewBox="0 0 24 24">
          <path d="M5 12.5l4.5 4.5L19 6.5" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        <svg v-else viewBox="0 0 24 24">
          <path d="M12 7v6.5M12 17.2v.3" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" />
          <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2.2" />
        </svg>
      </span>
      <span class="v-title">{{ title }}</span>
      <span class="v-meta">{{ language }} · {{ checker }}</span>
      <svg class="v-caret" :class="{ open: expanded }" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>

    <transition name="fold">
      <div v-if="expanded" class="v-body">
        <p v-if="suggestion" class="v-suggestion">{{ suggestion }}</p>

        <ul v-if="errors.length" class="v-errors">
          <li v-for="(issue, index) in errors" :key="`${issue.line}-${index}`">
            <span class="v-loc">{{ locationOf(issue) }}</span>
            <span class="v-msg">{{ issue.message }}</span>
            <span v-if="issue.hint" class="v-hint">{{ issue.hint }}</span>
          </li>
        </ul>

        <div v-if="warnings.length" class="v-warnings">
          <p class="v-sub">质量提示（不阻塞）</p>
          <ul>
            <li v-for="(issue, index) in warnings" :key="`w-${index}`">
              <span class="v-loc warn">{{ locationOf(issue) }}</span>
              <span class="v-msg">{{ issue.message }}</span>
            </li>
          </ul>
        </div>
      </div>
    </transition>
  </section>
</template>

<style scoped>
.validation {
  margin-top: 12px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--panel-2);
  overflow: hidden;
}

.validation.is-ok {
  border-color: var(--green-soft);
  background: linear-gradient(0deg, var(--green-soft), transparent 70%), var(--panel-2);
}

.validation.is-bad {
  border-color: rgba(251, 113, 133, 0.28);
  background: linear-gradient(0deg, var(--red-soft), transparent 70%), var(--panel-2);
}

.v-head {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 9px 12px;
  text-align: left;
}

.v-icon {
  display: inline-flex;
  width: 16px;
  height: 16px;
  color: var(--green);
}

.is-bad .v-icon {
  color: var(--red);
}

.v-icon svg {
  width: 100%;
  height: 100%;
}

.v-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.v-meta {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--text-faint);
}

.v-caret {
  width: 14px;
  height: 14px;
  color: var(--text-faint);
  transition: transform 0.18s var(--ease);
}

.v-caret.open {
  transform: rotate(180deg);
}

.v-body {
  padding: 2px 14px 13px;
  border-top: 1px dashed var(--border);
}

.v-suggestion {
  margin: 10px 0;
  font-size: 13px;
  color: var(--text-muted);
}

.v-errors,
.v-warnings ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.v-errors li,
.v-warnings li {
  display: flex;
  align-items: baseline;
  gap: 9px;
  font-size: 12.8px;
  line-height: 1.6;
}

.v-loc {
  flex: none;
  min-width: 56px;
  padding: 1px 7px;
  border-radius: 6px;
  background: var(--red-soft);
  color: var(--red);
  font-family: var(--font-mono);
  font-size: 11.5px;
  text-align: center;
}

.v-loc.warn {
  background: var(--amber-soft);
  color: var(--amber);
}

.v-msg {
  color: var(--text);
}

.v-hint {
  display: block;
  flex-basis: 100%;
  padding-left: 65px;
  color: var(--text-faint);
  font-size: 12.2px;
}

.v-warnings {
  margin-top: 12px;
}

.v-sub {
  margin: 0 0 6px;
  font-size: 11.5px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-faint);
}

.fold-enter-active,
.fold-leave-active {
  transition:
    opacity 0.16s ease,
    transform 0.16s ease;
}

.fold-enter-from,
.fold-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
