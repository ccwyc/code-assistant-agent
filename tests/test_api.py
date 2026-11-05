"""API 层测试：路由、校验、错误映射与 SSE 流（使用假模型，不联网）。"""

from __future__ import annotations

import json
import unittest
from typing import Any

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.agent import CodeAssistant, NotConfiguredError
from app.config import get_settings
from app.main import app, get_service
from tests.fake_model import ScriptedChatModel
from tests.test_agent import FINAL_ANSWER, make_settings

def build_fake_service(responses: list[AIMessage] | None = None, **overrides: Any) -> tuple[CodeAssistant, ScriptedChatModel]:
    model = ScriptedChatModel(responses=responses or [AIMessage(content=FINAL_ANSWER)])
    service = CodeAssistant(make_settings(**overrides), model=model)
    return service, model


def parse_sse(payload: str) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw_line in payload.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                events.append(current)
                current = {}
            continue
        if line.startswith("event:"):
            current["event"] = line[len("event:") :].strip()
        elif line.startswith("data:"):
            current["data"] = current.get("data", "") + line[len("data:") :].strip()
    if current:
        events.append(current)
    return events


class HealthTests(unittest.TestCase):
    def test_health_reports_configuration(self) -> None:
        with TestClient(app) as client:
            response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn(body["status"], {"ok", "degraded"})
        self.assertEqual(body["api_key_configured"], get_settings().is_configured)
        self.assertIn("python", body["supported_languages"])

    def test_root_and_request_id(self) -> None:
        with TestClient(app) as client:
            response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("X-Request-ID", response.headers)
        self.assertEqual(response.json()["name"], "code-assistant-agent")


class ChatEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service, self.model = build_fake_service()
        app.dependency_overrides[get_service] = lambda: self.service

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_chat_returns_answer(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/chat",
                json={"thread_id": "api-1", "message": "写一个 add 函数", "language": "python"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["thread_id"], "api-1")
        self.assertIn("### 代码", body["answer"])
        self.assertIn("elapsed_ms", body["usage"])

    def test_chat_default_thread_id(self) -> None:
        with TestClient(app) as client:
            response = client.post("/chat", json={"message": "你好"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["thread_id"], "default")

    def test_empty_message_rejected(self) -> None:
        with TestClient(app) as client:
            response = client.post("/chat", json={"thread_id": "x", "message": "   "})
        self.assertEqual(response.status_code, 422)

    def test_invalid_thread_id_rejected(self) -> None:
        with TestClient(app) as client:
            response = client.post("/chat", json={"thread_id": "bad id!", "message": "hi"})
        self.assertEqual(response.status_code, 422)

    def test_too_long_message_rejected(self) -> None:
        limit = get_settings().max_message_chars
        with TestClient(app) as client:
            response = client.post("/chat", json={"message": "a" * (limit + 1)})
        self.assertEqual(response.status_code, 413)

    def test_history_and_delete(self) -> None:
        with TestClient(app) as client:
            client.post("/chat", json={"thread_id": "api-hist", "message": "第一问"})
            history = client.get("/threads/api-hist/history")
            self.assertEqual(history.status_code, 200)
            body = history.json()
            self.assertGreaterEqual(body["message_count"], 2)
            self.assertEqual(body["messages"][0]["role"], "user")

            deleted = client.delete("/threads/api-hist")
            self.assertEqual(deleted.status_code, 200)
            self.assertTrue(deleted.json()["deleted"])

            after = client.get("/threads/api-hist/history").json()
            self.assertEqual(after["message_count"], 0)


class StreamEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        model = ScriptedChatModel(
            responses=[AIMessage(content=FINAL_ANSWER)], stream_tokens=True
        )
        service = CodeAssistant(make_settings(), model=model)
        app.dependency_overrides[get_service] = lambda: service

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_stream_sse_events(self) -> None:
        with TestClient(app) as client:
            with client.stream(
                "POST",
                "/chat/stream",
                json={"thread_id": "sse-1", "message": "写个函数", "language": "python"},
            ) as response:
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/event-stream", response.headers["content-type"])
                payload = "".join(response.iter_text())

        events = parse_sse(payload)
        kinds = [event.get("event") for event in events]
        self.assertIn("meta", kinds)
        self.assertIn("token", kinds)
        self.assertEqual(kinds[-1], "done")

        done = json.loads(events[-1]["data"])
        self.assertIn("### 代码", done["answer"])
        token_text = "".join(
            json.loads(event["data"])["content"] for event in events if event.get("event") == "token"
        )
        self.assertEqual(token_text, done["answer"])


class ErrorMappingTests(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_missing_api_key_returns_503(self) -> None:
        def _raise() -> CodeAssistant:
            raise NotConfiguredError()

        app.dependency_overrides[get_service] = _raise
        with TestClient(app) as client:
            response = client.post("/chat", json={"message": "你好"})
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertIn("DEEPSEEK_API_KEY", body["detail"])
        self.assertIn("hint", body)

    def test_upstream_failure_returns_502(self) -> None:
        class BrokenService:
            async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
                raise RuntimeError("upstream boom")

        app.dependency_overrides[get_service] = lambda: BrokenService()
        with TestClient(app) as client:
            response = client.post("/chat", json={"message": "你好"})
        self.assertEqual(response.status_code, 502)
        self.assertIn("upstream boom", response.json()["detail"])

    def test_stream_errors_are_events(self) -> None:
        class BrokenService:
            async def astream(self, *args: Any, **kwargs: Any):
                raise RuntimeError("stream boom")
                yield  # pragma: no cover - 仅为让函数成为异步生成器

        app.dependency_overrides[get_service] = lambda: BrokenService()
        with TestClient(app) as client:
            response = client.post("/chat/stream", json={"message": "你好"})
        self.assertEqual(response.status_code, 200)
        events = parse_sse(response.text)
        kinds = [event.get("event") for event in events]
        self.assertIn("error", kinds)
        self.assertIn("stream boom", response.text)


if __name__ == "__main__":
    unittest.main()
