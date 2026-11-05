"""Agent 可调用的工具（PRD 5.6 / 5.4）。

两个工具都采用 ``response_format="content_and_artifact"``：
- ``content``：给模型看的紧凑文本（省 token，便于它直接复述错误）；
- ``artifact``：结构化字典，供 API 层回传前端做高亮展示。

工具只做静态分析，绝不执行用户代码（PRD 4.2 / 9）。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from langchain_core.tools import tool
from pydantic import Field

from app.reviewer import review_code_snippet
from app.validator import SUPPORTED_LANGUAGES, validate_code_snippet

LanguageArg = Literal["auto", "python", "java", "javascript"]

_CODE_DESC = (
    "待校验的代码正文。可以直接传代码本身，也可以传包含 ``` 代码围栏的整段回答；"
    "多代码块时优先校验与 language 匹配的块。"
)


def _json(data: dict[str, Any]) -> str:
    """紧凑 JSON，避免中文被转义（\\uXXXX 会浪费 token）。"""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


@tool(response_format="content_and_artifact")
def validate_code(
    code: Annotated[str, Field(description=_CODE_DESC)],
    language: Annotated[
        LanguageArg,
        Field(description="代码语言；不确定时传 auto，由工具根据特征自动识别"),
    ] = "auto",
) -> tuple[str, dict[str, Any]]:
    """对生成的代码做静态语法校验，不执行代码。

    何时使用：每次生成 / 修改 Python、Java、JavaScript 代码之后**必须**调用一次，
    以确认语法正确；用户粘贴报错代码时也应先调用，用于定位问题行。

    返回内容包含 valid（是否通过）、errors（错误列表，含行号/列号/原因/修复提示）、
    suggestion（修复建议）。若 valid 为 false，请根据 errors 修正代码后重新调用本工具，
    最多重试 max_validation_retries 次；仍失败时如实告知用户问题所在，不要编造「已通过」。
    """
    result = validate_code_snippet(code, language)
    payload = result.to_dict()
    return result.feedback(), payload


@tool(response_format="content_and_artifact")
def review_code(
    code: Annotated[str, Field(description=_CODE_DESC)],
    language: Annotated[
        LanguageArg,
        Field(description="代码语言；不确定时传 auto"),
    ] = "auto",
) -> tuple[str, dict[str, Any]]:
    """从可读性、性能、健壮性三个维度评审代码并给出可执行的优化建议。

    何时使用：用户要求「优化代码 / 代码评审 / 提升性能 / 增加健壮性」时先调用本工具，
    再按返回的 suggestions 逐条改写代码。每条建议都包含 issue（问题）、
    why（为什么改）、how（改了什么 / 怎么改），请把这些信息组织进最终回答，
    不要自行编造工具没有发现的优化点。
    """
    review = review_code_snippet(code, language)
    payload = review.to_dict()
    return review.feedback(), payload


TOOLS = [validate_code, review_code]


def tool_names() -> list[str]:
    return [item.name for item in TOOLS]


def supported_languages() -> list[str]:
    return list(SUPPORTED_LANGUAGES)
