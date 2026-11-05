# ============================================================================
# 代码辅助开发 Agent · 前端镜像（Vue 3 + Vite → Nginx）
# 构建：docker build -t code-assistant-frontend:1.0.0 ./frontend
# 运行：docker run --rm -p 8080:80 --network <backend-network> code-assistant-frontend:1.0.0
# 说明：nginx.conf 将 /api 反代到 compose 中的 code-assistant:8000
# ============================================================================
FROM node:22-alpine AS build

WORKDIR /app

# 依赖安装（利用 layer 缓存）
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# 构建产物
COPY . .
RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
