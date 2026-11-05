"""API 层数据模型（Pydantic v2）。

请求/响应结构对齐 PRD 第 10 节与第 5 节验收：
- ``/chat``        请求 ``{thread_id, message}``，返回完整答案；
- ``/chat/stream`` SSE 事件流（meta / token / tool_call / tool_result / error / done）；
- ``/health``      健康检查 + 配置自检。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

LanguageHint = Literal["python", "java", "javascript", "auto"]

SUPPORTED_LANGUAGES: tuple[str, ...] = ("python", "java", "javascript")


class ChatRequest(BaseModel):
    """``/chat`` 与 ``/chat/stream`` 的统一请求体。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "thread_id": "u-001",
                "message": "写一个 Python 二分查找，带注释",
                "language": "python",
            }
        }
    )

    thread_id: str = Field(
        default="default",
        min_length=1,
        max_length=128,
        description="会话 ID，相同 ID 共享多轮上下文",
        pattern=r"^[A-Za-z0-9_.:\-]+$",
    )
    message: str = Field(min_length=1, description="用户输入（自然语言 / 代码 / 报错信息）")
    language: LanguageHint | None = Field(
        default=None, description="目标语言；auto / None 表示由 Agent 自判，缺省 Python"
    )

    @field_validator("message")
    @classmethod
    def _strip_message(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("message 不能为空白")
        return cleaned

    @field_validator("language", mode="before")
    @classmethod
    def _normalize_language(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            key = value.strip().lower()
            aliases = {
                "py": "python",
                "python3": "python",
                "js": "javascript",
                "node": "javascript",
                "nodejs": "javascript",
                "ts": "javascript",
                "typescript": "javascript",
                "": None,
            }
            return aliases.get(key, key)
        return value


class Usage(BaseModel):
    """粗略的用量信息（用于观测，不影响业务）。"""

    elapsed_ms: int = Field(default=0, description="端到端耗时（毫秒）")
    model_calls: int | None = Field(default=None, description="本次请求的模型调用次数")


class ChatResponse(BaseModel):
    """``/chat`` 响应。"""

    thread_id: str
    answer: str = Field(description="完整回答（Markdown：功能说明 / 代码 / 关键点 / 运行说明）")
    language: str | None = Field(default=None, description="本次实际使用的目标语言")
    validation: dict[str, Any] | None = Field(
        default=None, description="最近一次代码校验结果，便于前端展示"
    )
    usage: Usage = Field(default_factory=Usage)


class MessageItem(BaseModel):
    """历史消息条目。"""

    role: Literal["user", "assistant", "tool", "system"]
    content: str
    name: str | None = None


class HistoryResponse(BaseModel):
    thread_id: str
    messages: list[MessageItem]
    message_count: int


class HealthResponse(BaseModel):
    """健康检查响应；``status`` 为 ``ok`` / ``degraded``。"""

    status: Literal["ok", "degraded"]
    version: str
    model: str
    api_key_configured: bool
    memory_backend: str
    tracing: bool
    supported_languages: list[str] = Field(default_factory=lambda: list(SUPPORTED_LANGUAGES))
    timestamp: datetime = Field(default_factory=datetime.now)


class DeleteThreadResponse(BaseModel):
    thread_id: str
    deleted: bool


class ErrorResponse(BaseModel):
    detail: str
    hint: str | None = None
