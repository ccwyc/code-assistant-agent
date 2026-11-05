"""Agent 图测试：校验闭环、多轮记忆、流式事件、调用配额（全部使用假模型，不联网）。"""

from __future__ import annotations

import unittest
from typing import Any

from langchain_core.messages import AIMessage

from app.agent import CodeAssistant, build_agent, build_middleware
from app.config import Settings
from tests.fake_model import ScriptedChatModel

BAD_PY = "def add(a, b)\n    return a + b\n"
GOOD_PY = "def add(a: int, b: int) -> int:\n    return a + b\n"

FINAL_ANSWER = (
    "### 功能说明\n实现两数相加，时间复杂度 O(1)。\n\n"
    "### 代码\n```python\ndef add(a: int, b: int) -> int:\n    return a + b\n```\n\n"
    "### 关键点\n- 补充了类型注解与缺失的冒号。\n\n"
    "### 运行说明\n保存为 add.py 后执行 `python add.py`。"
)


def make_settings(**overrides: Any) -> Settings:
    base = {
        "deepseek_api_key": "sk-test-key",
        "enable_summarization": False,
        "max_validation_retries": 2,
        "temperature": 0.0,
    }
    base.update(overrides)
    return Settings(**base)


def make_responses() -> list[AIMessage]:
    return [
        AIMessage(
            content="先写一版并做静态校验。",
            tool_calls=[
                {
                    "name": "validate_code",
                    "args": {"code": BAD_PY, "language": "python"},
                    "id": "call_bad",
                }
            ],
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "validate_code",
                    "args": {"code": GOOD_PY, "language": "python"},
                    "id": "call_good",
                }
            ],
        ),
        AIMessage(content=FINAL_ANSWER),
    ]


class ToolLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_validate_fix_loop(self) -> None:
        """生成 → 校验失败 → 修正 → 校验通过 → 输出最终答案。"""
        model = ScriptedChatModel(responses=make_responses())
        assistant = CodeAssistant(make_settings(), model=model)

        result = await assistant.ainvoke("loop-1", "写一个 add 函数", "python")

        self.assertEqual(model.calls, 3)
        self.assertIn("### 代码", result["answer"])
        self.assertEqual(result["validation"]["valid"], True)
        self.assertEqual(result["language"], "python")

    async def test_validation_payload_is_structured(self) -> None:
        model = ScriptedChatModel(responses=make_responses())
        assistant = CodeAssistant(make_settings(), model=model)
        result = await assistant.ainvoke("loop-2", "写个加法函数")
        validation = result["validation"]
        self.assertIsNotNone(validation)
        self.assertIn("errors", validation)
        self.assertIn("suggestion", validation)
        self.assertEqual(validation["language"], "python")

    async def test_validation_is_scoped_to_current_turn(self) -> None:
        """上一轮有校验结果时，纯问答的下一轮不应复用它。"""
        responses = [
            *make_responses(),
            AIMessage(content="这是纯概念解释，不需要校验代码。"),
        ]
        model = ScriptedChatModel(responses=responses)
        assistant = CodeAssistant(make_settings(), model=model)

        first = await assistant.ainvoke("loop-3", "写个加法函数", "python")
        self.assertTrue(first["validation"]["valid"])

        second = await assistant.ainvoke("loop-3", "解释一下什么是装饰器", "python")
        self.assertIsNone(second["validation"])
        self.assertIn("概念解释", second["answer"])

    async def test_language_hint_injected_into_user_message(self) -> None:
        model = ScriptedChatModel(responses=[AIMessage(content="好的")])
        assistant = CodeAssistant(make_settings(), model=model)
        await assistant.ainvoke("lang-1", "写个排序", "java")
        first_call = model.seen_messages[0]
        self.assertIn("java", first_call[-1].content.lower())


class MemoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_multi_turn_context_is_reused(self) -> None:
        first = AIMessage(content="第一轮：这里是一个 Python 函数。")
        second = AIMessage(content="第二轮：已按上文改成递归版本。")
        model = ScriptedChatModel(responses=[first, second])
        assistant = CodeAssistant(make_settings(), model=model)

        await assistant.ainvoke("mem-1", "写一个阶乘函数", "python")
        await assistant.ainvoke("mem-1", "把上面的函数改成递归", "python")

        second_turn_messages = model.seen_messages[-1]
        contents = [message.content for message in second_turn_messages]
        self.assertTrue(any("阶乘" in str(item) for item in contents))
        self.assertIn("第一轮：这里是一个 Python 函数。", contents)

    async def test_threads_are_isolated(self) -> None:
        model = ScriptedChatModel(
            responses=[AIMessage(content="会话 A 的回答"), AIMessage(content="会话 B 的回答")]
        )
        assistant = CodeAssistant(make_settings(), model=model)

        await assistant.ainvoke("thread-a", "问题 A", "python")
        await assistant.ainvoke("thread-b", "问题 B", "python")

        messages_b = [str(message.content) for message in model.seen_messages[-1]]
        self.assertFalse(any("问题 A" in item for item in messages_b))

    async def test_history_and_reset(self) -> None:
        model = ScriptedChatModel(responses=[AIMessage(content="回答一")])
        assistant = CodeAssistant(make_settings(), model=model)
        await assistant.ainvoke("hist-1", "你好", "python")

        history = await assistant.history("hist-1")
        self.assertGreaterEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[-1]["role"], "assistant")

        self.assertTrue(await assistant.reset_thread("hist-1"))
        self.assertEqual(await assistant.history("hist-1"), [])

    async def test_history_hides_injected_language_hint(self) -> None:
        """历史接口返回用户原始输入，不暴露注入给模型的「（目标语言：…）」前缀。"""
        model = ScriptedChatModel(responses=[AIMessage(content="好的")])
        assistant = CodeAssistant(make_settings(), model=model)

        await assistant.ainvoke("hist-2", "写个冒泡排序", "python")
        history = await assistant.history("hist-2")

        user_message = next(item for item in history if item["role"] == "user")
        self.assertEqual(user_message["content"], "写个冒泡排序")

        # 模型侧仍然能看到语言提示
        first_call = model.seen_messages[0][-1].content
        self.assertIn("目标语言", first_call)

    async def test_history_without_language_hint(self) -> None:
        model = ScriptedChatModel(responses=[AIMessage(content="好的")])
        assistant = CodeAssistant(make_settings(), model=model)
        await assistant.ainvoke("hist-3", "解释一下装饰器")
        history = await assistant.history("hist-3")
        self.assertEqual(history[0]["content"], "解释一下装饰器")


class StreamingTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_emits_tokens_tools_and_done(self) -> None:
        model = ScriptedChatModel(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "validate_code",
                            "args": {"code": GOOD_PY, "language": "python"},
                            "id": "call_1",
                        }
                    ],
                ),
                AIMessage(content="### 功能说明\n完成。\n\n### 代码\n```python\nprint(1)\n```"),
            ],
            stream_tokens=True,
        )
        assistant = CodeAssistant(make_settings(), model=model)

        events = [event async for event in assistant.astream("stream-1", "写个 print", "python")]
        kinds = [event["type"] for event in events]

        self.assertIn("token", kinds)
        self.assertIn("tool_call", kinds)
        self.assertIn("tool_result", kinds)
        self.assertEqual(kinds[-1], "done")

        done = events[-1]
        self.assertIn("### 代码", done["answer"])
        self.assertTrue(done["validation"]["valid"])
        self.assertIn("elapsed_ms", done["usage"])

        token_text = "".join(event["content"] for event in events if event["type"] == "token")
        self.assertEqual(token_text, done["answer"])

    async def test_stream_tool_result_marks_invalid(self) -> None:
        model = ScriptedChatModel(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "validate_code",
                            "args": {"code": BAD_PY, "language": "python"},
                            "id": "call_bad",
                        }
                    ],
                ),
                AIMessage(content="已修正"),
            ]
        )
        assistant = CodeAssistant(make_settings(), model=model)
        events = [event async for event in assistant.astream("stream-2", "写个函数", "python")]
        tool_results = [event for event in events if event["type"] == "tool_result"]
        self.assertTrue(tool_results)
        self.assertFalse(tool_results[0]["valid"])
        self.assertIn("冒号", tool_results[0]["content"])


class GuardrailTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_call_limit_stops_runaway_loop(self) -> None:
        """模型反复调用工具时，ModelCallLimitMiddleware 兜底，不会无限循环。"""
        endless = AIMessage(
            content="",
            tool_calls=[
                {"name": "validate_code", "args": {"code": GOOD_PY}, "id": "call_x"}
            ],
        )
        model = ScriptedChatModel(responses=[endless])
        assistant = CodeAssistant(make_settings(max_model_calls_per_run=2), model=model)

        result = await assistant.ainvoke("guard-1", "写个函数", "python")
        self.assertLessEqual(model.calls, 3)
        self.assertTrue(result["answer"])

    def test_middleware_stack(self) -> None:
        settings = make_settings()
        model = ScriptedChatModel(responses=[AIMessage(content="x")])
        middleware = build_middleware(settings, model)
        names = [type(item).__name__ for item in middleware]
        self.assertIn("ModelCallLimitMiddleware", names)
        self.assertIn("ToolCallLimitMiddleware", names)

    def test_summarization_middleware_enabled(self) -> None:
        """开启摘要中间件后，状态 Schema 合并正常、图仍可执行。"""
        settings = make_settings(
            enable_summarization=True,
            summarization_trigger_tokens=50,
            summarization_keep_messages=2,
        )
        model = ScriptedChatModel(responses=[AIMessage(content="回答")])
        assistant = CodeAssistant(settings, model=model)
        self.assertIn("SummarizationMiddleware.before_model", assistant.agent.get_graph().nodes)

    async def test_run_with_summarization_enabled(self) -> None:
        settings = make_settings(
            enable_summarization=True,
            summarization_trigger_tokens=50,
            summarization_keep_messages=2,
        )
        model = ScriptedChatModel(responses=[AIMessage(content="第一轮"), AIMessage(content="第二轮")])
        assistant = CodeAssistant(settings, model=model)
        await assistant.ainvoke("sum-1", "你好", "python")
        second = await assistant.ainvoke("sum-1", "继续", "python")
        self.assertEqual(second["answer"], "第二轮")

    def test_build_agent_with_fake_model(self) -> None:
        settings = make_settings()
        model = ScriptedChatModel(responses=[AIMessage(content="x")])
        agent = build_agent(settings=settings, model=model)
        nodes = set(agent.get_graph().nodes)
        self.assertIn("model", nodes)
        self.assertIn("tools", nodes)


if __name__ == "__main__":
    unittest.main()
