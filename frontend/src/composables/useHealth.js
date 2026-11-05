import { computed, ref } from 'vue'
import { fetchHealth } from '../api/client'

/**
 * 健康检查：进入页面检查一次，之后每 30s 轮询一次，窗口重新聚焦时再查。
 * 用于在界面上提示「服务在线 / 未配置 API Key」。
 */
const health = ref(null)
const checking = ref(false)
const error = ref('')

let timer = null
let inflight = false

async function check() {
  if (inflight) return health.value
  inflight = true
  checking.value = true
  try {
    health.value = await fetchHealth()
    error.value = ''
  } catch (err) {
    error.value = err.message || '健康检查失败'
    health.value = null
  } finally {
    checking.value = false
    inflight = false
  }
  return health.value
}

function start(intervalMs = 30000) {
  stop()
  check()
  timer = setInterval(check, intervalMs)
}

function stop() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

export function useHealth() {
  const online = computed(() => Boolean(health.value))
  const configured = computed(() => Boolean(health.value?.api_key_configured))
  const model = computed(() => health.value?.model || '未知模型')
  const degraded = computed(() => online.value && !configured.value)

  return {
    health,
    checking,
    error,
    online,
    configured,
    model,
    degraded,
    check,
    start,
    stop,
    interval: 30000,
  }
}
