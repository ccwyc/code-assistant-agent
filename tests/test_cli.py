"""CLI 测试：参数解析与输出渲染（使用假模型，不发起网络请求）。"""

from __future__ import annotations

import contextlib
import io
import unittest

from langchain_core.messages import AIMessage

from app.agent import CodeAssistant
from cli import Console, _ask_once, _print_status, build_parser
from tests.fake_model import ScriptedChatModel
from tests.test_agent import FINAL_ANSWER, make_settings


class ParserTests(unittest.TestCase):
    def test_defaults(self) -> None:
        args = build_parser().parse_args([])
        self.assertIsNone(args.message)
        self.assertIsNone(args.thread_id)
        self.assertIsNone(args.language)
        self.assertFalse(args.no_stream)
        self.assertFalse(args.check)

    def test_language_choices(self) -> None:
        args = build_parser().parse_args(["-m", "写个函数", "--language", "java", "--no-stream"])
        self.assertEqual(args.language, "java")
        self.assertTrue(args.no_stream)

    def test_check_flag(self) -> None:
        args = build_parser().parse_args(["--check"])
        self.assertTrue(args.check)


class OutputTests(unittest.TestCase):
    def test_console_paint_plain_when_no_tty(self) -> None:
        console = Console()
        console.color = False
        self.assertEqual(console.paint("hi", "\033[31m"), "hi")

    def test_status_renders_core_fields(self) -> None:
        console = Console()
        console.color = False
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            _print_status(console)
        output = buffer.getvalue()
        for keyword in ("模型", "API Key", "记忆后端", "支持语言", "python"):
            self.assertIn(keyword, output)


class AskOnceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.console = Console()
        self.console.color = False

    async def test_stream_mode_prints_answer_and_footer(self) -> None:
        model = ScriptedChatModel(responses=[AIMessage(content=FINAL_ANSWER)], stream_tokens=True)
        service = CodeAssistant(make_settings(), model=model)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            await _ask_once(service, "写个加法函数", "cli-1", "python", True, self.console)
        output = buffer.getvalue()
        self.assertIn("### 代码", output)
        self.assertIn("耗时", output)

    async def test_non_stream_mode(self) -> None:
        model = ScriptedChatModel(responses=[AIMessage(content=FINAL_ANSWER)])
        service = CodeAssistant(make_settings(), model=model)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            await _ask_once(service, "写个加法函数", "cli-2", None, False, self.console)
        output = buffer.getvalue()
        self.assertIn("### 功能说明", output)
        self.assertIn("thread=cli-2", output)

    async def test_stream_shows_tool_events(self) -> None:
        model = ScriptedChatModel(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "validate_code",
                            "args": {"code": "def f():\n    return 1\n", "language": "python"},
                            "id": "c1",
                        }
                    ],
                ),
                AIMessage(content="完成"),
            ],
            stream_tokens=True,
        )
        service = CodeAssistant(make_settings(), model=model)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            await _ask_once(service, "写个函数", "cli-3", "python", True, self.console)
        output = buffer.getvalue()
        self.assertIn("调用工具 validate_code", output)
        self.assertIn("通过", output)


if __name__ == "__main__":
    unittest.main()
