import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js/lib/core'
import bash from 'highlight.js/lib/languages/bash'
import java from 'highlight.js/lib/languages/java'
import javascript from 'highlight.js/lib/languages/javascript'
import json from 'highlight.js/lib/languages/json'
import python from 'highlight.js/lib/languages/python'
import sql from 'highlight.js/lib/languages/sql'
import typescript from 'highlight.js/lib/languages/typescript'
import xml from 'highlight.js/lib/languages/xml'

/**
 * 按需注册语言：只打包本项目会用到的语法，避免 highlight.js 全量语言包（约 250KB）。
 * 未注册的语言会退化为纯文本转义，不影响渲染。
 */
for (const [name, language] of Object.entries({
  python,
  java,
  javascript,
  typescript,
  json,
  bash,
  sql,
  xml,
})) {
  hljs.registerLanguage(name, language)
}
hljs.registerAliases(['py'], { languageName: 'python' })
hljs.registerAliases(['js'], { languageName: 'javascript' })
hljs.registerAliases(['ts'], { languageName: 'typescript' })
hljs.registerAliases(['sh', 'shell'], { languageName: 'bash' })
hljs.registerAliases(['html'], { languageName: 'xml' })

/**
 * Markdown 渲染：
 * - `html: false` 关闭原始 HTML，避免 XSS（回答内容全部来自模型）；
 * - 代码围栏统一渲染为「语言标签 + 复制按钮 + 高亮代码」的卡片；
 * - 链接强制新窗口打开并加 noopener。
 */
const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  typographer: false,
  highlight: (code, language) => highlightCode(code, language),
})

const LANGUAGE_LABELS = {
  python: 'Python',
  py: 'Python',
  java: 'Java',
  javascript: 'JavaScript',
  js: 'JavaScript',
  ts: 'TypeScript',
  typescript: 'TypeScript',
  json: 'JSON',
  bash: 'Bash',
  shell: 'Shell',
  sh: 'Shell',
  sql: 'SQL',
  html: 'HTML',
  css: 'CSS',
  xml: 'XML',
  yaml: 'YAML',
  yml: 'YAML',
  go: 'Go',
  rust: 'Rust',
  c: 'C',
  cpp: 'C++',
  text: 'Text',
  plaintext: 'Text',
}

function normalizeLanguage(language) {
  if (!language) return ''
  const key = String(language).toLowerCase().trim()
  if (key === 'py') return 'python'
  if (key === 'js') return 'javascript'
  if (key === 'ts') return 'typescript'
  if (key === 'sh') return 'bash'
  if (key === 'yml') return 'yaml'
  return key
}

export function languageLabel(language) {
  const key = String(language || '').toLowerCase()
  return LANGUAGE_LABELS[key] || (language ? String(language) : 'Code')
}

function highlightCode(code, language) {
  const key = normalizeLanguage(language)
  if (key && hljs.getLanguage(key)) {
    try {
      return hljs.highlight(code, { language: key, ignoreIllegals: true }).value
    } catch (error) {
      /* 高亮失败时退化为纯文本 */
    }
  }
  return md.utils.escapeHtml(code)
}

md.renderer.rules.fence = (tokens, index) => {
  const token = tokens[index]
  const info = token.info ? md.utils.unescapeAll(token.info).trim() : ''
  const rawLanguage = info.split(/\s+/)[0] || ''
  const language = rawLanguage || 'text'
  const highlighted = highlightCode(token.content, rawLanguage)
  const label = md.utils.escapeHtml(languageLabel(rawLanguage))

  return (
    `<div class="code-card" data-lang="${md.utils.escapeHtml(language)}">` +
    '<div class="code-head">' +
    `<span class="code-lang">${label}</span>` +
    '<button class="code-copy" type="button" data-action="copy-code">复制</button>' +
    '</div>' +
    `<pre class="code-pre"><code class="hljs language-${md.utils.escapeHtml(
      language
    )}">${highlighted}</code></pre>` +
    '</div>'
  )
}

const defaultLinkOpen =
  md.renderer.rules.link_open ||
  ((tokens, index, options, env, self) => self.renderToken(tokens, index, options))

md.renderer.rules.link_open = (tokens, index, options, env, self) => {
  tokens[index].attrSet('target', '_blank')
  tokens[index].attrSet('rel', 'noopener noreferrer')
  return defaultLinkOpen(tokens, index, options, env, self)
}

export function renderMarkdown(text) {
  if (!text) return ''
  try {
    return md.render(String(text))
  } catch (error) {
    return `<p>${md.utils.escapeHtml(String(text))}</p>`
  }
}

export default md
