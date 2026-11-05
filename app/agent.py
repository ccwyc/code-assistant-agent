"""Agent 构建与执行封装（PRD 第 6 / 7 节）。

职责：
1. 组装 ``ChatDeepSeek`` + ``create_agent``（LangGraph 图）+ 中间件 + 记忆 checkpointer；
2. 对上层（FastAPI / CLI）暴露统一接口：``ainvoke`` / ``astream`` / ``history`` / ``reset_thread``；
3. 把 LangGraph 的原始事件翻译成稳定的业务事件（token / tool_call / tool_result / done）。
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ModelRetryMiddleware,
    SummarizationMiddleware,
    ToolCallLimitMiddleware,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_deepseek import ChatDeepSeek
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph

from app.config import Settings, configure_logging, get_settings, sync_langsmith_env
from app.prompts import build_system_prompt, build_user_message
from app.schemas import SUPPORTED_LANGUAGES
from app.tools import TOOLS

logger = logging.getLogger(__name__)


class AssistantError(RuntimeError):
    """Agent 执行期的可预期错误基类。"""


class NotConfiguredError(AssistantError):
    """缺少 DEEPSEEK_API_KEY 等必要配置。"""

    def __init__(self, message: str = "未配置 DEEPSEEK_API_KEY，无法调用大模型") -> None:
        super().__init__(message)
        self.hint = (
            "请复制 .env.example 为 .env，并填写 DEEPSEEK_API_KEY；"
            "本地可用 `python cli.py --check` 检查配置是否生效。"
        )


def build_model(
    settings: Settings | None = None,
    model_name: str | None = None,
    **overrides: Any,
) -> BaseChatModel:
    """构造 ChatDeepSeek 客户端；未配置 API Key 时抛出 NotConfiguredError。"""
    cfg = settings or get_settings()
    if not cfg.is_configured:
        raise NotConfiguredError()

    sync_langsmith_env(cfg)
    params: dict[str, Any] = {
        "model": model_name or cfg.deepseek_model,
        "api_key": cfg.deepseek_api_key,
        "api_base": cfg.deepseek_base_url,
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
        "timeout": cfg.request_timeout,
        "max_retries": 1,
    }
    params.update(overrides)
    return ChatDeepSeek(**params)


def build_middleware(settings: Settings, model: BaseChatModel) -> list[Any]:
    """按「摘要 → 调用配额 → 工具配额 → 重试」的顺序装配中间件。"""
    middleware: list[Any] = []
    if settings.enable_summarization:
        middleware.append(
            SummarizationMiddleware(
                model=model,
                trigger=("tokens", settings.summarization_trigger_tokens),
                keep=("messages", settings.summarization_keep_messages),
            )
        )
    middleware.extend(
        [
            ModelCallLimitMiddleware(
                run_limit=settings.max_model_calls_per_run,
                exit_behavior="end",
            ),
            ToolCallLimitMiddleware(
                tool_name="validate_code",
                run_limit=settings.max_tool_calls_per_run,
                exit_behavior="continue",
            ),
            ModelRetryMiddleware(max_retries=2, on_failure="continue"),
        ]
    )
    return middleware


def build_agent(
    *,
    settings: Settings | None = None,
    model: BaseChatModel | None = None,
    checkpointer: Any | None = None,
    system_prompt: str | None = None,
    language: str | None = None,
) -> CompiledStateGraph:
    """构建并编译 LangGraph 图。

    ``model`` / ``checkpointer`` 可注入，便于测试时替换为假模型与独立内存。
    """
    cfg = settings or get_settings()
    resolved_model = model or build_model(cfg)
    prompt = system_prompt or build_system_prompt(
        max_retries=cfg.max_validation_retries, language=language
    )
    return create_agent(
        resolved_model,
        tools=TOOLS,
        system_prompt=prompt,
        middleware=build_middleware(cfg, resolved_model),
        checkpointer=checkpointer if checkpointer is not None else InMemorySaver(),
        name="code_assistant",
    )


# --------------------------------------------------------------------------- #
# 事件 / 消息工具
# --------------------------------------------------------------------------- #
def _message_text(message: BaseMessage) -> str:
    """把 content（str 或 block list）统一成纯文本。"""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    parts.append(block["text"])
                elif isinstance(block.get("text"), str):
                    parts.append(block["text"])
        return "".join(parts)
    return str(content) if content is not None else ""


def _role_of(message: BaseMessage) -> str:
    if isinstance(message, HumanMessage):
        return "user"
    if isinstance(message, AIMessage):
        return "assistant"
    if isinstance(message, ToolMessage):
        return "tool"
    return "system"


_LANGUAGE_HINT_RE = re.compile(r"^（目标语言：[^）]*）\s*\n+")


def _strip_language_hint(text: str) -> str:
    """去掉注入给模型的语言提示，保证历史接口返回的是用户原始输入。

    ``build_user_message`` 会把「（目标语言：java）」拼在用户消息前（让模型明确目标语言），
    这个前缀对模型有用，但不该出现在前端的历史消息里。
    """
    return _LANGUAGE_HINT_RE.sub("", text, count=1).strip()


def _extract_validation(message: ToolMessage) -> dict[str, Any] | None:
    artifact = getattr(message, "artifact", None)
    if isinstance(artifact, dict) and "valid" in artifact:
        return artifact
    return None


# --------------------------------------------------------------------------- #
# 会话封装
# --------------------------------------------------------------------------- #
class CodeAssistant:
    """对 LangGraph 图的薄封装，屏蔽 LangChain 的细节。"""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        model: BaseChatModel | None = None,
        checkpointer: Any | None = None,
        agent: CompiledStateGraph | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        sync_langsmith_env(self.settings)
        self.checkpointer = checkpointer if checkpointer is not None else InMemorySaver()
        if agent is not None:
            self.agent = agent
        else:
            self.agent = build_agent(
                settings=self.settings, model=model, checkpointer=self.checkpointer
            )

    # ---------------------------------------------------------------- 生命周期
    @property
    def model_name(self) -> str:
        return self.settings.deepseek_model

    def describe(self) -> dict[str, Any]:
        return {
            "model": self.model_name,
            "api_key_configured": self.settings.is_configured,
            "memory_backend": "InMemorySaver",
            "tracing": bool(self.settings.langsmith_tracing and self.settings.langsmith_api_key),
            "supported_languages": list(SUPPORTED_LANGUAGES),
        }

    # ---------------------------------------------------------------- 内部工具
    def _config(self, thread_id: str, run_name: str = "chat") -> dict[str, Any]:
        return {
            "configurable": {"thread_id": thread_id},
            "run_name": f"code-assistant/{run_name}",
            "tags": ["code-assistant-agent", f"thread:{thread_id}"],
            "metadata": {"thread_id": thread_id, "model": self.model_name},
            "recursion_limit": 40,
        }

    @staticmethod
    def _inputs(message: str, language: str | None) -> dict[str, Any]:
        return {"messages": [HumanMessage(content=build_user_message(message, language))]}

    @staticmethod
    def _current_turn(messages: list[BaseMessage]) -> list[BaseMessage]:
        """只保留最后一轮用户输入之后的消息，避免把上一轮的答案/校验结果当成本轮结果。"""
        for index in range(len(messages) - 1, -1, -1):
            if isinstance(messages[index], HumanMessage):
                return messages[index + 1 :]
        return list(messages)

    @classmethod
    def _select_answer(cls, messages: list[BaseMessage]) -> str:
        turn = cls._current_turn(messages)
        candidates = [
            message
            for message in turn
            if isinstance(message, AIMessage) and not message.tool_calls
        ] or [message for message in turn if isinstance(message, AIMessage)]
        for message in reversed(candidates):
            text = _message_text(message).strip()
            if text:
                return text
        return ""

    @classmethod
    def _select_validation(cls, messages: list[BaseMessage]) -> dict[str, Any] | None:
        for message in reversed(cls._current_turn(messages)):
            if isinstance(message, ToolMessage):
                found = _extract_validation(message)
                if found is not None:
                    return found
        return None

    # ---------------------------------------------------------------- 主流程
    async def ainvoke(
        self,
        thread_id: str,
        message: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        """普通对话：一次性返回完整答案。"""
        started = time.perf_counter()
        result = await self.agent.ainvoke(
            self._inputs(message, language),
            config=self._config(thread_id, "chat"),
        )
        messages: list[BaseMessage] = list(result.get("messages", []))
        answer = self._select_answer(messages) or "（模型未返回内容，请重试或换一种描述方式）"
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {
            "thread_id": thread_id,
            "answer": answer,
            "language": language if language and language != "auto" else None,
            "validation": self._select_validation(messages),
            "usage": {"elapsed_ms": elapsed_ms, "model_calls": None},
        }

    async def astream(
        self,
        thread_id: str,
        message: str,
        language: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """流式对话：逐个产出业务事件，最后一个事件为 ``done``。"""
        started = time.perf_counter()
        chunks: list[str] = []
        validation: dict[str, Any] | None = None
        answer_from_state: str = ""

        async for mode, payload in self.agent.astream(
            self._inputs(message, language),
            config=self._config(thread_id, "stream"),
            stream_mode=["messages", "updates"],
        ):
            if mode == "messages":
                chunk, metadata = payload
                if not isinstance(chunk, AIMessageChunk):
                    continue
                if (metadata or {}).get("langgraph_node") != "model":
                    continue
                text = chunk.text
                if text:
                    chunks.append(text)
                    yield {"type": "token", "content": text}
                continue

            if mode == "updates" and isinstance(payload, dict):
                for update in payload.values():
                    if not isinstance(update, dict):
                        continue
                    for item in update.get("messages", []) or []:
                        if isinstance(item, AIMessage) and item.tool_calls:
                            for call in item.tool_calls:
                                yield {
                                    "type": "tool_call",
                                    "name": call.get("name"),
                                    "args": _truncate_args(call.get("args", {})),
                                }
                        elif isinstance(item, ToolMessage):
                            found = _extract_validation(item)
                            if found is not None:
                                validation = found
                            yield {
                                "type": "tool_result",
                                "name": item.name or "tool",
                                "valid": None if found is None else found.get("valid"),
                                "content": _message_text(item)[:1200],
                            }
                    answer_from_state = self._select_answer(
                        list(update.get("messages", []) or [])
                    ) or answer_from_state

        answer = "".join(chunks).strip() or answer_from_state
        if not answer:
            answer = "（模型未返回内容，请重试或换一种描述方式）"
            yield {"type": "error", "message": answer}

        yield {
            "type": "done",
            "thread_id": thread_id,
            "answer": answer,
            "language": language if language and language != "auto" else None,
            "validation": validation,
            "usage": {"elapsed_ms": int((time.perf_counter() - started) * 1000)},
        }

    # ---------------------------------------------------------------- 记忆管理
    async def history(self, thread_id: str) -> list[dict[str, Any]]:
        """读取某个会话的历史消息（来自 LangGraph checkpointer）。"""
        try:
            snapshot = await self.agent.aget_state(self._config(thread_id))
        except Exception as exc:  # noqa: BLE001 - 状态读取失败不应影响主流程
            logger.warning("读取会话历史失败 thread_id=%s: %s", thread_id, exc)
            return []
        messages = (snapshot.values or {}).get("messages", []) if snapshot else []
        rendered: list[dict[str, Any]] = []
        for message in messages:
            text = _message_text(message).strip()
            if not text:
                continue
            role = _role_of(message)
            if role == "user":
                text = _strip_language_hint(text)
            rendered.append(
                {
                    "role": role,
                    "content": text,
                    "name": getattr(message, "name", None),
                }
            )
        return rendered

    async def reset_thread(self, thread_id: str) -> bool:
        """删除某个会话的全部 checkpoint。"""
        try:
            await self.checkpointer.adelete_thread(thread_id)
            return True
        except AttributeError:
            # 生产 checkpointer（如 PostgresSaver）可能未实现 adelete_thread
            self.checkpointer.delete_thread(thread_id)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("删除会话失败 thread_id=%s: %s", thread_id, exc)
            return False


def _truncate_args(args: Any, limit: int = 400) -> Any:
    """工具参数里通常是整段代码，事件流里只回传预览，避免 SSE 消息过大。"""
    if isinstance(args, dict):
        trimmed: dict[str, Any] = {}
        for key, value in args.items():
            if isinstance(value, str) and len(value) > limit:
                trimmed[key] = value[:limit] + f"…（共 {len(value)} 字符）"
            else:
                trimmed[key] = value
        return trimmed
    return args


@lru_cache(maxsize=1)
def get_assistant() -> CodeAssistant:
    """进程级单例；测试可 ``get_assistant.cache_clear()``。"""
    configure_logging()
    return CodeAssistant()


def reset_assistant() -> None:
    """清空单例（配置变更 / 测试隔离用）。"""
    get_assistant.cache_clear()
