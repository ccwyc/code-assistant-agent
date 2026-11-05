"""应用配置：统一从环境变量 / ``.env`` 读取。

设计要点：
1. 使用 ``pydantic-settings`` 做类型校验，缺失项有合理默认值，保证「没配 Key 也能起服务」
   （此时 ``/health`` 返回 degraded，``/chat`` 返回 503 并给出可读提示）。
2. ``python-dotenv`` 在导入阶段加载 ``.env``，让 LangSmith 等第三方库能读到同名变量。
3. 所有可调参数集中在此，避免散落在 agent / api 层。
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

# 尽早加载 .env，LangSmith / OpenAI SDK 等直接读 os.environ 的组件也能生效
load_dotenv(BASE_DIR / ".env", override=False)

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """集中式配置（字段名即环境变量名，大小写不敏感）。"""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------ 模型
    deepseek_api_key: str | None = Field(default=None, description="DeepSeek API Key")
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com/v1", description="OpenAI 兼容 Base URL"
    )
    deepseek_model: str = Field(default="deepseek-v4-flash", description="默认对话模型")
    deepseek_summary_model: str | None = Field(
        default=None, description="用于长对话摘要的模型，缺省复用主模型"
    )
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=4096, gt=0)
    request_timeout: float = Field(default=120.0, gt=0, description="单次模型调用超时（秒）")

    # -------------------------------------------------------------- 可观测性
    langsmith_tracing: bool = Field(default=False, description="是否开启 LangSmith 追踪")
    langsmith_api_key: str | None = None
    langsmith_project: str = Field(default="code-assistant-agent")
    langsmith_endpoint: str | None = Field(default=None, description="自建 LangSmith 地址")

    # ------------------------------------------------------------ Agent 行为
    enable_summarization: bool = Field(default=True, description="长对话摘要中间件开关")
    summarization_trigger_tokens: int = Field(default=8000, gt=0)
    summarization_keep_messages: int = Field(default=12, ge=2)
    max_validation_retries: int = Field(
        default=2, ge=0, le=10, description="代码校验失败后的最大修正次数"
    )
    max_model_calls_per_run: int = Field(
        default=12, ge=1, description="单次请求允许的最大模型调用次数（防死循环 / 限流）"
    )
    max_tool_calls_per_run: int = Field(default=8, ge=1, description="单次请求校验工具调用上限")

    # ---------------------------------------------------------------- 接口层
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    cors_origins: str = Field(default="*", description="逗号分隔；* 表示允许全部")
    max_message_chars: int = Field(default=20_000, gt=0)
    max_concurrent_requests: int = Field(
        default=8, ge=1, description="进程内同时处理的请求上限（配合模型调用配额形成双层保护）"
    )
    log_level: str = "INFO"

    # ---------------------------------------------------------------- 派生值
    @property
    def is_configured(self) -> bool:
        """是否具备真实调用大模型的最小配置。"""
        return bool(self.deepseek_api_key and self.deepseek_api_key.strip())

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def summary_model_name(self) -> str:
        return self.deepseek_summary_model or self.deepseek_model

    @field_validator("deepseek_api_key", "langsmith_api_key", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        """把空字符串 / 占位符视为未配置，避免假装有 Key。"""
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned or cleaned.lower() in {"your-api-key", "sk-xxx", "changeme", "none"}:
                return None
            return cleaned
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """进程内单例；测试可调用 ``get_settings.cache_clear()`` 重置。"""
    return Settings()


def configure_logging(level: str | None = None) -> None:
    """统一的日志格式（幂等）。"""
    resolved = (level or get_settings().log_level).upper()
    logging.basicConfig(
        level=getattr(logging, resolved, logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        force=False,
    )


def sync_langsmith_env(settings: Settings | None = None) -> None:
    """把配置写回 ``os.environ``，供 LangSmith SDK 读取。

    必须在模型调用前执行；LangSmith 只认环境变量，不接受运行时参数。
    """
    cfg = settings or get_settings()
    tracing = "true" if cfg.langsmith_tracing and cfg.langsmith_api_key else "false"
    os.environ["LANGSMITH_TRACING"] = tracing
    # 兼容旧变量名
    os.environ["LANGCHAIN_TRACING_V2"] = tracing
    if cfg.langsmith_api_key:
        # 显式赋值而不是 setdefault：.env 里常见 `LANGSMITH_API_KEY=` 的空值，
        # setdefault 会让空值遮蔽真实配置。
        os.environ["LANGSMITH_API_KEY"] = cfg.langsmith_api_key
        os.environ["LANGCHAIN_API_KEY"] = cfg.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = cfg.langsmith_project
    os.environ["LANGCHAIN_PROJECT"] = cfg.langsmith_project
    if cfg.langsmith_endpoint:
        os.environ["LANGSMITH_ENDPOINT"] = cfg.langsmith_endpoint

    if cfg.langsmith_tracing and not cfg.langsmith_api_key:
        logger.warning(
            "LANGSMITH_TRACING=true 但缺少 LANGSMITH_API_KEY，已自动关闭追踪"
        )
