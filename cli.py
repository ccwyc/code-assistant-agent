"""命令行交互客户端（PRD 4.1「CLI 交互」）。

用法示例：
    python cli.py                        # 进入多轮交互（默认流式输出）
    python cli.py -m "写个 Python 快排"   # 单次提问
    python cli.py --thread-id demo-01    # 指定会话（同一 ID 共享上下文）
    python cli.py --language java        # 强制目标语言
    python cli.py --check                # 只做配置检查

交互内可用命令：/help /new /thread <id> /lang <lang> /history /stream on|off /check /exit
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid

from app.agent import CodeAssistant, NotConfiguredError, get_assistant
from app.config import configure_logging, get_settings
from app.schemas import SUPPORTED_LANGUAGES

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"

HELP_TEXT = f"""\
{BOLD}可用命令{RESET}
  /help            显示本帮助
  /new             开启新会话（自动生成 thread_id）
  /thread <id>     切换到指定会话
  /lang <lang>     设置目标语言：{", ".join(SUPPORTED_LANGUAGES)} 或 auto
  /history         查看当前会话的历史消息
  /stream on|off   切换流式 / 普通输出
  /check           查看模型与配置状态
  /exit            退出（也可用 Ctrl+C / Ctrl+D）
"""

BANNER = f"""{BOLD}{CYAN}
╭──────────────────────────────────────────────────────╮
│   代码辅助开发 Agent · Python / Java / JavaScript    │
│   生成 → 校验 → 修正，多轮上下文迭代                  │
╰──────────────────────────────────────────────────────╯{RESET}
输入 /help 查看命令，直接输入需求开始对话。
"""


def _enable_ansi() -> None:
    """在 Windows 控制台启用 ANSI 颜色（无副作用）。"""
    if os.name == "nt":
        os.system("")


def _supports_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


class Console:
    """极简着色输出；非 TTY 时自动退化为纯文本（便于管道 / 日志）。"""

    def __init__(self) -> None:
        self.color = _supports_color()

    def paint(self, text: str, color: str) -> str:
        return f"{color}{text}{RESET}" if self.color else text

    def info(self, text: str) -> None:
        print(self.paint(text, CYAN))

    def ok(self, text: str) -> None:
        print(self.paint(text, GREEN))

    def warn(self, text: str) -> None:
        print(self.paint(text, YELLOW))

    def error(self, text: str) -> None:
        print(self.paint(text, RED), file=sys.stderr)

    def dim(self, text: str) -> None:
        print(self.paint(text, DIM))

    def token(self, text: str) -> None:
        sys.stdout.write(text)
        sys.stdout.flush()

    def tool(self, text: str) -> None:
        print(self.paint(f"\n  ⟳ {text}", MAGENTA))


async def _ask_once(
    service: CodeAssistant,
    message: str,
    thread_id: str,
    language: str | None,
    stream: bool,
    console: Console,
) -> None:
    """执行一轮问答（流式或普通）。"""
    if not stream:
        result = await service.ainvoke(thread_id, message, language)
        print()
        print(result["answer"])
        usage = result.get("usage", {})
        console.dim(f"\n（耗时 {usage.get('elapsed_ms', 0)} ms · thread={thread_id}）")
        return

    answer_parts: list[str] = []
    wrote_any = False
    async for event in service.astream(thread_id, message, language):
        kind = event.get("type")
        if kind == "token":
            content = event.get("content", "")
            answer_parts.append(content)
            console.token(content)
            wrote_any = True
        elif kind == "tool_call":
            console.tool(f"调用工具 {event.get('name')} 做静态校验…")
        elif kind == "tool_result":
            verdict = "通过" if event.get("valid") else "未通过"
            console.tool(f"{event.get('name')} 返回：{verdict}")
        elif kind == "error":
            console.error(f"\n{event.get('message')}")
        elif kind == "done":
            if not wrote_any:
                print(event.get("answer", ""))
            usage = event.get("usage", {})
            print()
            console.dim(f"\n（耗时 {usage.get('elapsed_ms', 0)} ms · thread={thread_id}）")


async def repl(
    service: CodeAssistant,
    thread_id: str,
    language: str | None,
    stream: bool,
    console: Console,
) -> None:
    print(BANNER)
    console.dim(
        f"模型：{service.model_name} · 会话：{thread_id} · 语言：{language or 'auto'}"
        f" · 输出：{'流式' if stream else '普通'}"
    )
    while True:
        try:
            prompt = console.paint("你 › ", BOLD + GREEN)
            raw = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            console.info("再见 👋")
            return

        if not raw:
            continue
        if raw.startswith("/"):
            command, _, argument = raw[1:].partition(" ")
            command = command.lower()
            argument = argument.strip()
            if command in {"exit", "quit", "q"}:
                console.info("再见 👋")
                return
            if command == "help":
                print(HELP_TEXT)
                continue
            if command == "new":
                thread_id = f"cli-{uuid.uuid4().hex[:8]}"
                console.ok(f"已开启新会话：{thread_id}")
                continue
            if command == "thread":
                if not argument:
                    console.warn("用法：/thread <id>")
                    continue
                thread_id = argument
                console.ok(f"已切换会话：{thread_id}")
                continue
            if command == "lang":
                if argument.lower() in {"auto", ""}:
                    language = None
                    console.ok("目标语言已设为 auto（由 Agent 判断，缺省 Python）")
                elif argument.lower() in SUPPORTED_LANGUAGES:
                    language = argument.lower()
                    console.ok(f"目标语言已设为 {language}")
                else:
                    console.warn(f"不支持的语言：{argument}（可选：{', '.join(SUPPORTED_LANGUAGES)}）")
                continue
            if command == "history":
                messages = await service.history(thread_id)
                if not messages:
                    console.dim("当前会话还没有历史消息。")
                for item in messages:
                    label = {"user": "你", "assistant": "助手", "tool": "工具", "system": "系统"}.get(
                        item["role"], item["role"]
                    )
                    preview = item["content"].replace("\n", " ")
                    if len(preview) > 120:
                        preview = preview[:120] + "…"
                    print(f"{console.paint(label, BOLD)}: {preview}")
                continue
            if command == "stream":
                if argument.lower() in {"on", "off"}:
                    stream = argument.lower() == "on"
                    console.ok(f"已切换为{'流式' if stream else '普通'}输出")
                else:
                    console.warn("用法：/stream on|off")
                continue
            if command == "check":
                _print_status(console)
                continue
            console.warn(f"未知命令：/{command}，输入 /help 查看帮助")
            continue

        try:
            await _ask_once(service, raw, thread_id, language, stream, console)
        except NotConfiguredError as exc:
            console.error(str(exc))
            console.warn(getattr(exc, "hint", ""))
            return
        except asyncio.CancelledError:
            console.warn("已取消当前请求")
            raise
        except Exception as exc:  # noqa: BLE001 - CLI 需要保持可继续交互
            console.error(f"请求失败：{exc}")
            console.dim("可以继续输入，或 /new 开启新会话。")


def _print_status(console: Console) -> None:
    cfg = get_settings()
    lines = [
        f"模型          : {cfg.deepseek_model}",
        f"Base URL      : {cfg.deepseek_base_url}",
        f"API Key       : {'已配置' if cfg.is_configured else '未配置（/chat 将返回 503）'}",
        f"记忆后端      : InMemorySaver（生产可换 PostgreSQL checkpointer）",
        f"LangSmith     : {'开启 · ' + cfg.langsmith_project if cfg.langsmith_tracing and cfg.langsmith_api_key else '关闭'}",
        f"校验重试上限  : {cfg.max_validation_retries} 次",
        f"单次模型调用上限: {cfg.max_model_calls_per_run} 次",
        f"长对话摘要    : {'开启，触发阈值 ' + str(cfg.summarization_trigger_tokens) + ' tokens' if cfg.enable_summarization else '关闭'}",
        f"支持语言      : {', '.join(SUPPORTED_LANGUAGES)}",
    ]
    print()
    for line in lines:
        print("  " + console.paint(line, DIM))
    print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="代码辅助开发 Agent 命令行客户端（Python / Java / JavaScript）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("-m", "--message", help="单次提问内容；省略则进入交互模式")
    parser.add_argument("--thread-id", default=None, help="会话 ID（默认自动生成，交互内可 /thread 切换）")
    parser.add_argument(
        "--language",
        choices=[*SUPPORTED_LANGUAGES, "auto"],
        default=None,
        help="强制目标语言；默认 auto（未指定时 Agent 使用 Python）",
    )
    parser.add_argument("--no-stream", action="store_true", help="关闭流式输出，一次性返回完整答案")
    parser.add_argument("--check", action="store_true", help="仅打印配置状态后退出")
    parser.add_argument("--debug", action="store_true", help="输出调试日志")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _enable_ansi()
    configure_logging("DEBUG" if args.debug else get_settings().log_level)
    console = Console()

    if args.check or not get_settings().is_configured:
        _print_status(console)
        if not get_settings().is_configured and not args.check:
            console.warn(
                "提示：未配置 DEEPSEEK_API_KEY，无法调用模型。"
                "请复制 .env.example 为 .env 并填写 Key 后重试。"
            )
            return 2

    if args.check:
        return 0

    language = None if (args.language in (None, "auto")) else args.language
    thread_id = args.thread_id or f"cli-{uuid.uuid4().hex[:8]}"
    stream = not args.no_stream

    try:
        service = get_assistant()
    except NotConfiguredError as exc:
        console.error(str(exc))
        return 2

    try:
        if args.message:
            asyncio.run(_ask_once(service, args.message, thread_id, language, stream, console))
            return 0
        if not sys.stdin.isatty():
            # 管道输入：把全部 stdin 当作一条消息处理
            payload = sys.stdin.read().strip()
            if not payload:
                console.error("stdin 为空")
                return 1
            asyncio.run(_ask_once(service, payload, thread_id, language, stream, console))
            return 0
        asyncio.run(repl(service, thread_id, language, stream, console))
        return 0
    except KeyboardInterrupt:
        print()
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
