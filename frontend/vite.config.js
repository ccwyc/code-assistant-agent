import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

/**
 * 开发环境：`/api/*` 反向代理到 FastAPI（默认 127.0.0.1:8000），规避跨域并支持 SSE 直通。
 * 生产环境：默认同样使用 `/api` 前缀，由 Nginx 反代（见 frontend/nginx.conf）；
 *          也可通过 VITE_API_BASE 直接指定后端地址，例如 https://api.example.com。
 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const proxyTarget = env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000'

  return {
    plugins: [vue()],
    resolve: {
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    server: {
      host: '127.0.0.1',
      port: 5173,
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
          // 流式响应不能被缓冲，否则 SSE 会「攒完才一次性到达」
          configure: (proxy) => {
            proxy.on('proxyRes', (proxyRes) => {
              proxyRes.headers['cache-control'] = 'no-cache'
            })
          },
        },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: false,
      chunkSizeWarningLimit: 900,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes('node_modules/markdown-it') || id.includes('node_modules/highlight.js')) {
              return 'markdown'
            }
            return undefined
          },
        },
      },
    },
  }
})
