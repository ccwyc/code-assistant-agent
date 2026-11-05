<script setup>
import { computed } from 'vue'
import { renderMarkdown } from '../utils/markdown'
import { copyText } from '../utils/format'

const props = defineProps({
  content: { type: String, default: '' },
})

const html = computed(() => renderMarkdown(props.content))

async function handleClick(event) {
  const button = event.target.closest?.('[data-action="copy-code"]')
  if (!button) return
  const code = button.closest('.code-card')?.querySelector('code')?.textContent ?? ''
  const ok = await copyText(code)
  button.textContent = ok ? '已复制' : '复制失败'
  setTimeout(() => {
    button.textContent = '复制'
  }, 1600)
}
</script>

<template>
  <!-- 内容由 markdown-it 渲染且禁用了原始 HTML；代码块复制通过事件委托处理 -->
  <div class="markdown" @click="handleClick" v-html="html"></div>
</template>
