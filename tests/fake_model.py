"""测试专用的脚本化 ChatModel（不访问网络）。

继承 ``BaseChatModel`` 并实现 ``bind_tools``，让 ``create_agent`` 能正常拿到
「支持工具调用」的模型；``responses`` 按顺序回放，用于驱动完整的
「生成 → 校验 → 修正」流程与多轮记忆测试。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import PrivateAttr


class ScriptedChatModel(BaseChatModel):
    """按顺序回放预设 AIMessage 的假模型。

    ``stream_tokens=True`` 时把回复内容按字符切成 chunk 流式产出，
    用于验证 ``stream_mode="messages"`` 的 token 事件链路。
    """

    responses: list[AIMessage] = []
    calls: int = 0
    stream_tokens: bool = False

    _seen_messages: list[list[BaseMessage]] = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    @property
    def seen_messages(self) -> list[list[BaseMessage]]:
        return self._seen_messages

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ScriptedChatModel":
        return self

    def _next_message(self) -> AIMessage:
        index = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return self.responses[index] if self.responses else AIMessage(content="")

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self._seen_messages.append(list(messages))
        message = self._next_message()
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        self._seen_messages.append(list(messages))
        message = self._next_message()

        if message.tool_calls:
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {
                            "name": call["name"],
                            "args": json.dumps(call.get("args", {}), ensure_ascii=False),
                            "id": call.get("id"),
                            "index": index,
                        }
                        for index, call in enumerate(message.tool_calls)
                    ],
                )
            )
            return

        text = message.content if isinstance(message.content, str) else ""
        if self.stream_tokens and text:
            for char in text:
                yield ChatGenerationChunk(message=AIMessageChunk(content=char))
            return
        yield ChatGenerationChunk(message=AIMessageChunk(content=text))
