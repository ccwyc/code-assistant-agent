<script setup>
const props = defineProps({
  configured: { type: Boolean, default: true },
  online: { type: Boolean, default: false },
  model: { type: String, default: '' },
})

const emit = defineEmits(['example'])

const EXAMPLES = [
  {
    tag: 'Python',
    title: '带缓存的斐波那契',
    desc: '递归 + 类型注解 + 复杂度说明',
    language: 'python',
    text: '写一个 Python 函数，递归求斐波那契数列，带缓存优化，补充类型注解和注释，并说明时间/空间复杂度。',
  },
  {
    tag: 'Java',
    title: '线程安全单例',
    desc: '双重检查锁 · 为什么需要 volatile',
    language: 'java',
    text: '用 Java 实现线程安全的单例模式，使用双重检查锁，并解释为什么需要 volatile 关键字。',
  },
  {
    tag: 'JavaScript',
    title: '防抖函数',
    desc: 'immediate 选项 + JSDoc',
    language: 'javascript',
    text: '写一个 JavaScript 防抖函数，支持 immediate 立即执行选项，补全 JSDoc 注释并给出使用示例。',
  },
  {
    tag: 'Bug 排查',
    title: '定位 KeyError',
    desc: '给报错代码，定位到具体行',
    language: 'python',
    text: '这段代码运行报 KeyError，帮我定位问题并给出修复方案：\n```python\ndef get_name(user):\n    return user["profile"]["name"]\n```',
  },
  {
    tag: '代码优化',
    title: '列表推导式重构',
    desc: '性能 + 可读性 + 资源释放',
    language: 'python',
    text: '从可读性、性能、健壮性三个维度优化这段代码：\n```python\ndef load(path):\n    fh = open(path)\n    data = []\n    for line in fh:\n        data.append(line.strip())\n    print(data)\n    return data\n```',
  },
  {
    tag: '语法解释',
    title: '装饰器是什么',
    desc: '是什么 · 为什么 · 怎么用 · 注意事项',
    language: 'python',
    text: '用「是什么、为什么、怎么用、注意事项」四要素解释 Python 装饰器，并给一个可运行的示例。',
  },
]
</script>

<template>
  <div class="welcome">
    <div class="hero">
      <div class="kicker">
        <span class="k-dot"></span>
        LangChain 1.x · LangGraph · DeepSeek
      </div>
      <h1>
        让想法直接变成
        <span class="grad">可运行的代码</span>
      </h1>
      <p class="lead">
        Python / Java / JavaScript 多语言代码生成、语法解释、Bug 排查与代码优化。
        每次输出都会经过静态语法校验，附带关键点注释与运行说明。
      </p>
    </div>

    <div v-if="!online" class="notice">
      <div class="notice-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24">
          <path d="M12 8v5M12 16.6v.4" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" />
          <path d="M10.3 3.9 2.8 17a2 2 0 0 0 1.7 3h15a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round" />
        </svg>
      </div>
      <div>
        <strong>未连接到后端服务</strong>
        <p>
          请确认 FastAPI 已启动（默认 <code>http://127.0.0.1:8000</code>），然后刷新页面。
          启动命令：<code>python -m app.main</code>
        </p>
      </div>
    </div>

    <div v-else-if="!configured" class="notice">
      <div class="notice-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24">
          <path d="M12 8v5M12 16.6v.4" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" />
          <path d="M10.3 3.9 2.8 17a2 2 0 0 0 1.7 3h15a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round" />
        </svg>
      </div>
      <div>
        <strong>后端已连接，但尚未配置 DEEPSEEK_API_KEY</strong>
        <p>
          在项目根目录的 <code>.env</code> 中填写 <code>DEEPSEEK_API_KEY=sk-...</code>
          并重启后端服务，即可开始对话。健康检查接口当前返回 <code>degraded</code>。
        </p>
      </div>
    </div>

    <div class="examples">
      <button
        v-for="item in EXAMPLES"
        :key="item.title"
        type="button"
        class="example"
        @click="emit('example', { text: item.text, language: item.language })"
      >
        <span class="e-top">
          <span class="e-tag">{{ item.tag }}</span>
          <svg class="e-arrow" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M6 18 18 6M9 6h9v9" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </span>
        <span class="e-title">{{ item.title }}</span>
        <span class="e-desc">{{ item.desc }}</span>
      </button>
    </div>

    <div class="capabilities">
      <div class="cap">
        <span class="cap-num">3</span>
        <span class="cap-label">语言支持</span>
      </div>
      <div class="cap">
        <span class="cap-num">100%</span>
        <span class="cap-label">生成即校验</span>
      </div>
      <div class="cap">
        <span class="cap-num">∞</span>
        <span class="cap-label">多轮上下文</span>
      </div>
      <div class="cap">
        <span class="cap-num">{{ model || 'DeepSeek' }}</span>
        <span class="cap-label">当前模型</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.welcome {
  max-width: 840px;
  margin: 0 auto;
  padding: 42px 4px 24px;
  animation: fade-up 0.4s var(--ease) both;
}

.hero {
  text-align: center;
  margin-bottom: 30px;
}

.kicker {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 11.5px;
  letter-spacing: 0.02em;
}

.k-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 0 4px var(--accent-soft);
}

h1 {
  margin: 18px 0 12px;
  font-size: clamp(28px, 4.2vw, 40px);
  font-weight: 750;
  line-height: 1.22;
  letter-spacing: -0.025em;
}

.grad {
  background: var(--accent-gradient);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.lead {
  max-width: 600px;
  margin: 0 auto;
  color: var(--text-muted);
  font-size: 14.5px;
  line-height: 1.8;
}

.notice {
  display: flex;
  gap: 12px;
  margin: 0 auto 24px;
  padding: 14px 16px;
  border-radius: var(--radius-md);
  border: 1px solid rgba(251, 191, 36, 0.28);
  background: var(--amber-soft);
  text-align: left;
}

.notice-icon {
  flex: none;
  width: 20px;
  height: 20px;
  color: var(--amber);
  margin-top: 1px;
}

.notice-icon svg {
  width: 100%;
  height: 100%;
}

.notice strong {
  font-size: 13.5px;
  color: var(--text);
}

.notice p {
  margin: 4px 0 0;
  font-size: 12.8px;
  color: var(--text-muted);
  line-height: 1.7;
}

.notice code {
  padding: 1px 5px;
  border-radius: 5px;
  background: var(--panel);
  border: 1px solid var(--border);
  font-family: var(--font-mono);
  font-size: 11.5px;
}

.examples {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.example {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 5px;
  padding: 14px 15px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--panel);
  text-align: left;
  transition:
    transform 0.2s var(--ease),
    border-color 0.2s var(--ease),
    background 0.2s var(--ease),
    box-shadow 0.2s var(--ease);
}

.example:hover {
  transform: translateY(-2px);
  border-color: rgba(34, 211, 238, 0.35);
  background: var(--panel-2);
  box-shadow: var(--shadow-md);
}

.e-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  margin-bottom: 4px;
}

.e-tag {
  font-family: var(--font-mono);
  font-size: 10.5px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--accent);
}

.e-arrow {
  width: 14px;
  height: 14px;
  color: var(--text-faint);
  opacity: 0;
  transform: translate(-3px, 3px);
  transition:
    opacity 0.2s var(--ease),
    transform 0.2s var(--ease);
}

.example:hover .e-arrow {
  opacity: 1;
  transform: translate(0, 0);
  color: var(--accent);
}

.e-title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text);
}

.e-desc {
  font-size: 12px;
  color: var(--text-faint);
  line-height: 1.55;
}

.capabilities {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 26px;
  padding-top: 20px;
  border-top: 1px solid var(--border);
}

.cap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.cap-num {
  font-family: var(--font-mono);
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}

.cap-label {
  font-size: 11.5px;
  color: var(--text-faint);
}

@media (max-width: 900px) {
  .examples {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 620px) {
  .welcome {
    padding-top: 24px;
  }

  .examples {
    grid-template-columns: 1fr;
  }

  .capabilities {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    row-gap: 14px;
  }
}
</style>
