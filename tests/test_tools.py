"""工具层测试：``@tool`` 的 content/artifact 双通道与结构化返回。"""

from __future__ import annotations

import unittest

from langchain_core.messages import ToolMessage

from app.tools import TOOLS, review_code, supported_languages, tool_names, validate_code
from tests.test_agent import BAD_PY, GOOD_PY

VALID_JAVA_CODE = r"""
public class Demo {
    public static void main(String[] args) {
        System.out.println("hello");
    }
}
"""


class ValidateCodeToolTests(unittest.TestCase):
    def _invoke(self, code: str, language: str = "auto") -> ToolMessage:
        """以 ToolCall 形式调用，才能拿到带 artifact 的 ToolMessage（与 Agent 内部一致）。"""
        result = validate_code.invoke(
            {
                "name": "validate_code",
                "args": {"code": code, "language": language},
                "id": "call-test",
                "type": "tool_call",
            }
        )
        self.assertIsInstance(result, ToolMessage)
        return result

    def test_plain_dict_invoke_returns_content(self) -> None:
        output = validate_code.invoke({"code": GOOD_PY, "language": "python"})
        self.assertIsInstance(output, str)
        self.assertIn("通过", output)

    def test_tool_metadata(self) -> None:
        self.assertEqual(validate_code.name, "validate_code")
        self.assertEqual(validate_code.response_format, "content_and_artifact")
        self.assertEqual(tool_names(), ["validate_code", "review_code"])
        self.assertEqual(len(TOOLS), 2)
        self.assertEqual(set(supported_languages()), {"python", "java", "javascript"})

    def test_valid_python_payload(self) -> None:
        message = self._invoke(GOOD_PY, "python")
        self.assertIsInstance(message.artifact, dict)
        self.assertTrue(message.artifact["valid"])
        self.assertIn("通过", message.content)

    def test_invalid_python_payload(self) -> None:
        message = self._invoke(BAD_PY, "python")
        artifact = message.artifact
        self.assertFalse(artifact["valid"])
        self.assertEqual(artifact["errors"][0]["line"], 1)
        self.assertIn("冒号", artifact["suggestion"])
        # 给模型看的文本里必须有可定位信息，便于它直接修正
        self.assertIn("第 1 行", message.content)

    def test_auto_language_detection(self) -> None:
        message = self._invoke(VALID_JAVA_CODE, "auto")
        self.assertEqual(message.artifact["language"], "java")
        self.assertTrue(message.artifact["valid"])

    def test_fenced_answer_input(self) -> None:
        message = self._invoke("### 代码\n```python\ndef f():\n    return 1\n```")
        self.assertTrue(message.artifact["valid"])

    def test_result_serialisable(self) -> None:
        import json

        message = self._invoke(BAD_PY, "python")
        encoded = json.dumps(message.artifact, ensure_ascii=False)
        self.assertIn("errors", encoded)


class ReviewCodeToolTests(unittest.TestCase):
    def test_review_returns_dimensions(self) -> None:
        code = (
            "def load(path):\n"
            "    fh = open(path)\n"
            "    data = []\n"
            "    for line in fh:\n"
            "        data.append(line.strip())\n"
            "    return data\n"
        )
        result = review_code.invoke(
            {
                "name": "review_code",
                "args": {"code": code, "language": "python"},
                "id": "call-review",
                "type": "tool_call",
            }
        )
        self.assertIsInstance(result, ToolMessage)
        artifact = result.artifact
        self.assertEqual(artifact["language"], "python")
        self.assertIn("metrics", artifact)
        dimensions = {item["dimension"] for item in artifact["suggestions"]}
        self.assertTrue(dimensions)
        self.assertTrue(dimensions.issubset({"可读性", "性能", "健壮性"}))
        for item in artifact["suggestions"]:
            self.assertTrue(item["why"])
            self.assertTrue(item["how"])
        self.assertIn("评分", result.content)


if __name__ == "__main__":
    unittest.main()
