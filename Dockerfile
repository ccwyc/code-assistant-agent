# syntax=docker/dockerfile:1
# ============================================================================
# 代码辅助开发 Agent · 生产镜像（PRD M4 交付物）
# 构建：docker build -t code-assistant-agent:1.0.0 .
# 运行：docker run --rm -p 8000:8000 --env-file .env code-assistant-agent:1.0.0
# ============================================================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 仅安装本项目所需的最小依赖集（项目 B 的向量库不进入镜像）
COPY requirements-app.txt ./
RUN pip install --no-cache-dir -r requirements-app.txt

# 业务代码
COPY app ./app
COPY cli.py README.md ./

# 以非 root 用户运行
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
