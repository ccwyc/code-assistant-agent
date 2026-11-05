"""FastAPI 入口（PRD 第 10 节）。

接口：
- ``GET  /``                     服务信息
- ``GET  /health``               健康检查（含配置自检）
- ``POST /chat``                 普通对话，返回完整答案
- ``POST /chat/stream``          流式对话（SSE，打字机效果）
- ``GET  /threads/{id}/history`` 读取会话历史
- ``DELETE /threads/{id}``       清空会话（删除 checkpoint）

设计要点：
- 依赖注入 ``get_service``，测试时可整体替换为假模型驱动的实例；
- 统一异常映射：未配置 → 503、超时 → 504、其余 → 500（均带可读 hint）；
- 用信号量限制并发请求数，配合 Agent 内部的 ModelCallLimitMiddleware 形成双层保护。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from app import __version__
from app.agent import CodeAssistant, NotConfiguredError, get_assistant
from app.config import Settings, configure_logging, get_settings
from app.schemas import (
    ChatRequest,
    ChatResponse,
    DeleteThreadResponse,
    HealthResponse,
    HistoryResponse,
    MessageItem,
    Usage,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 生命周期
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    cfg = get_settings()
    configure_logging(cfg.log_level)
    app.state.settings = cfg
    app.state.semaphore = asyncio.Semaphore(cfg.max_concurrent_requests)
    if cfg.is_configured:
        logger.info(
            "code-assistant-agent 启动：model=%s base_url=%s tracing=%s",
            cfg.deepseek_model,
            cfg.deepseek_base_url,
            cfg.langsmith_tracing,
        )
    else:
        logger.warning(
            "未检测到 DEEPSEEK_API_KEY：服务可启动，/health 返回 degraded，/chat 将返回 503。"
            "请复制 .env.example 为 .env 并填写 Key。"
        )
    yield
    logger.info("code-assistant-agent 已停止")


app = FastAPI(
    title="代码辅助开发 Agent",
    version=__version__,
    description=(
        "多语言（Python / Java / JavaScript）代码生成、语法解释、Bug 排查与代码优化助手。"
        "基于 LangChain 1.x create_agent + LangGraph，实现「生成 → 校验 → 修正」闭环。"
    ),
    lifespan=lifespan,
)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_context(request: Request, call_next: Any) -> Any:
    """注入 request-id 并记录耗时，便于排查（对应 PRD 9「可观测」）。"""
    request_id = request.headers.get("x-request-id") or f"req-{uuid.uuid4().hex[:12]}"
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("未捕获异常 %s %s request_id=%s", request.method, request.url.path, request_id)
        raise
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-ms"] = str(elapsed_ms)
    logger.info(
        "%s %s -> %s (%sms) request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
        request_id,
    )
    return response


# --------------------------------------------------------------------------- #
# 异常映射
# --------------------------------------------------------------------------- #
@app.exception_handler(NotConfiguredError)
async def handle_not_configured(request: Request, exc: NotConfiguredError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": str(exc),
            "hint": getattr(exc, "hint", "请在 .env 中配置 DEEPSEEK_API_KEY 后重启服务。"),
        },
    )


@app.exception_handler(asyncio.TimeoutError)
async def handle_timeout(request: Request, exc: asyncio.TimeoutError) -> JSONResponse:
    return JSONResponse(
        status_code=504,
        content={"detail": "模型调用超时", "hint": "可调大 REQUEST_TIMEOUT 或简化问题后重试。"},
    )


# --------------------------------------------------------------------------- #
# 依赖
# --------------------------------------------------------------------------- #
def get_service() -> CodeAssistant | None:
    """返回进程级 Agent 单例；未配置 Key 时返回 None。

    这里刻意不直接抛 NotConfiguredError：FastAPI 会先求解依赖再做请求体校验，
    依赖抛异常会让「message 为空白」这类 422 请求被误报成 503。
    配置检查因此下沉到各端点内部（请求体校验之后）。
    """
    try:
        return get_assistant()
    except NotConfiguredError:
        return None


def require_service(service: CodeAssistant | None) -> CodeAssistant:
    if service is None:
        raise NotConfiguredError()
    return service


def get_semaphore() -> asyncio.Semaphore:
    """并发闸门；lifespan 未执行时（如部分测试场景）惰性创建。"""
    semaphore = getattr(app.state, "semaphore", None)
    if semaphore is None:
        semaphore = asyncio.Semaphore(get_settings().max_concurrent_requests)
        app.state.semaphore = semaphore
    return semaphore


def _check_message_size(payload: ChatRequest, cfg: Settings) -> None:
    if len(payload.message) > cfg.max_message_chars:
        raise HTTPException(
            status_code=413,
            detail=f"message 过长（{len(payload.message)} 字符），上限为 {cfg.max_message_chars} 字符",
        )


# --------------------------------------------------------------------------- #
# 路由
# --------------------------------------------------------------------------- #
@app.get("/", include_in_schema=False)
async def root() -> dict[str, Any]:
    return {
        "name": "code-assistant-agent",
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
        "endpoints": ["/chat", "/chat/stream", "/threads/{thread_id}/history"],
    }


@app.get("/health", response_model=HealthResponse, summary="健康检查")
async def health() -> HealthResponse:
    cfg = get_settings()
    return HealthResponse(
        status="ok" if cfg.is_configured else "degraded",
        version=__version__,
        model=cfg.deepseek_model,
        api_key_configured=cfg.is_configured,
        memory_backend="InMemorySaver",
        tracing=bool(cfg.langsmith_tracing and cfg.langsmith_api_key),
    )


@app.post("/chat", response_model=ChatResponse, summary="普通对话（返回完整答案）")
async def chat(
    payload: ChatRequest,
    service: CodeAssistant | None = Depends(get_service),
) -> ChatResponse:
    cfg = get_settings()
    _check_message_size(payload, cfg)
    service = require_service(service)

    async with get_semaphore():
        try:
            result = await service.ainvoke(
                thread_id=payload.thread_id,
                message=payload.message,
                language=payload.language,
            )
        except NotConfiguredError:
            raise
        except asyncio.TimeoutError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一转成 502，避免泄漏内部堆栈
            logger.exception("对话失败 thread_id=%s", payload.thread_id)
            raise HTTPException(status_code=502, detail=f"模型调用失败：{exc}") from exc

    return ChatResponse(
        thread_id=result["thread_id"],
        answer=result["answer"],
        language=result.get("language"),
        validation=result.get("validation"),
        usage=Usage(**result.get("usage", {})),
    )


@app.post("/chat/stream", summary="流式对话（SSE）")
async def chat_stream(
    payload: ChatRequest,
    service: CodeAssistant | None = Depends(get_service),
) -> EventSourceResponse:
    cfg = get_settings()
    _check_message_size(payload, cfg)
    service = require_service(service)

    async def event_generator() -> AsyncIterator[dict[str, Any]]:
        yield {
            "event": "meta",
            "data": json.dumps(
                {
                    "thread_id": payload.thread_id,
                    "model": cfg.deepseek_model,
                    "language": payload.language,
                },
                ensure_ascii=False,
            ),
        }
        try:
            async with get_semaphore():
                async for event in service.astream(
                    thread_id=payload.thread_id,
                    message=payload.message,
                    language=payload.language,
                ):
                    yield {
                        "event": event.pop("type", "message"),
                        "data": json.dumps(event, ensure_ascii=False),
                    }
        except NotConfiguredError as exc:
            yield {
                "event": "error",
                "data": json.dumps(
                    {"detail": str(exc), "hint": getattr(exc, "hint", None)}, ensure_ascii=False
                ),
            }
        except asyncio.CancelledError:
            logger.info("客户端断开流式连接 thread_id=%s", payload.thread_id)
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("流式对话失败 thread_id=%s", payload.thread_id)
            yield {
                "event": "error",
                "data": json.dumps({"detail": f"模型调用失败：{exc}"}, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator(), ping=15)


@app.get(
    "/threads/{thread_id}/history",
    response_model=HistoryResponse,
    summary="读取会话历史",
)
async def thread_history(
    thread_id: str,
    service: CodeAssistant | None = Depends(get_service),
) -> HistoryResponse:
    messages = await require_service(service).history(thread_id)
    return HistoryResponse(
        thread_id=thread_id,
        messages=[MessageItem(**item) for item in messages],
        message_count=len(messages),
    )


@app.delete(
    "/threads/{thread_id}",
    response_model=DeleteThreadResponse,
    summary="清空会话（删除 checkpoint）",
)
async def delete_thread(
    thread_id: str,
    service: CodeAssistant | None = Depends(get_service),
) -> DeleteThreadResponse:
    deleted = await require_service(service).reset_thread(thread_id)
    return DeleteThreadResponse(thread_id=thread_id, deleted=deleted)


def run() -> None:
    """``python -m app.main`` 以开发模式启动。"""
    import uvicorn

    cfg = get_settings()
    uvicorn.run("app.main:app", host=cfg.app_host, port=cfg.app_port, reload=False)


if __name__ == "__main__":
    run()
