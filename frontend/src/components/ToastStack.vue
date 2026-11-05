<script setup>
defineProps({
  items: { type: Array, default: () => [] },
})

defineEmits(['dismiss'])
</script>

<template>
  <div class="toasts" aria-live="polite">
    <transition-group name="toast">
      <div v-for="item in items" :key="item.id" class="toast" :class="item.type">
        <span class="t-icon" aria-hidden="true">
          <svg v-if="item.type === 'success'" viewBox="0 0 24 24">
            <path d="M5 12.5l4.5 4.5L19 6.5" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <svg v-else viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2" />
            <path d="M12 7.5V13M12 16.4v.4" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" />
          </svg>
        </span>
        <div class="t-body">
          <strong v-if="item.title">{{ item.title }}</strong>
          <p>{{ item.text }}</p>
        </div>
        <button type="button" class="t-close" aria-label="关闭提示" @click="$emit('dismiss', item.id)">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M6 6l12 12M18 6 6 18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
          </svg>
        </button>
      </div>
    </transition-group>
  </div>
</template>

<style scoped>
.toasts {
  position: fixed;
  right: 22px;
  bottom: 22px;
  z-index: 80;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: min(420px, calc(100vw - 32px));
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 11px 12px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-strong);
  background: var(--panel);
  box-shadow: var(--shadow-lg);
  pointer-events: auto;
}

.toast.error {
  border-color: rgba(251, 113, 133, 0.35);
}

.toast.success {
  border-color: rgba(52, 211, 153, 0.3);
}

.t-icon {
  flex: none;
  width: 17px;
  height: 17px;
  margin-top: 1px;
  color: var(--red);
}

.toast.success .t-icon {
  color: var(--green);
}

.t-icon svg {
  width: 100%;
  height: 100%;
}

.t-body {
  flex: 1;
  min-width: 0;
}

.t-body strong {
  display: block;
  font-size: 12.5px;
  margin-bottom: 1px;
}

.t-body p {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--text-muted);
}

.t-close {
  flex: none;
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  color: var(--text-faint);
}

.t-close:hover {
  background: var(--panel-2);
  color: var(--text);
}

.t-close svg {
  width: 13px;
  height: 13px;
}

.toast-enter-active,
.toast-leave-active {
  transition:
    opacity 0.2s var(--ease),
    transform 0.2s var(--ease);
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(8px) scale(0.98);
}

.toast-move {
  transition: transform 0.2s var(--ease);
}

@media (max-width: 760px) {
  .toasts {
    right: 12px;
    left: 12px;
    bottom: 12px;
    max-width: none;
  }
}
</style>
