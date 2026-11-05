import { computed, ref } from 'vue'

const STORAGE_KEY = 'ca.theme.v1'

function initialTheme() {
  const attr = document.documentElement.getAttribute('data-theme')
  if (attr === 'light' || attr === 'dark') return attr
  return 'dark'
}

const theme = ref(initialTheme())

function apply(value) {
  document.documentElement.setAttribute('data-theme', value)
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', value === 'light' ? '#f4f6fb' : '#070b12')
  try {
    localStorage.setItem(STORAGE_KEY, value)
  } catch (error) {
    /* 隐私模式下忽略 */
  }
}

apply(theme.value)

export function useTheme() {
  function toggle() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
    apply(theme.value)
  }

  function set(value) {
    if (value !== 'dark' && value !== 'light') return
    theme.value = value
    apply(value)
  }

  return {
    theme,
    isDark: computed(() => theme.value === 'dark'),
    toggle,
    set,
  }
}
