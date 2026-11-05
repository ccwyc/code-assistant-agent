"""评审器与 Prompt 约定测试（对应 PRD 5.2 / 5.4 / 5.7 / 12）。"""

from __future__ import annotations

import unittest

from app.prompts import build_system_prompt, build_user_message
from app.reviewer import review_code_snippet


class ReviewerTests(unittest.TestCase):
    def test_python_review_finds_issues(self) -> None:
        code = (
            "def load(path):\n"
            "    fh = open(path)\n"
            "    data = []\n"
            "    for line in fh:\n"
            "        data.append(line.strip())\n"
            "    print(data)\n"
            "    return data\n"
        )
        result = review_code_snippet(code, "python")
        self.assertEqual(result.language, "python")
        self.assertLess(result.score, 100)
        issues = " ".join(item.issue for item in result.suggestions)
        self.assertIn("with", issues)  # 未使用上下文管理器
        for item in result.suggestions:
            self.assertIn(item.dimension, {"可读性", "性能", "健壮性"})
            self.assertTrue(item.why and item.how)

    def test_python_clean_code_scores_high(self) -> None:
        code = (
            '"""工具模块。"""\n\n\n'
            "def add(a: int, b: int) -> int:\n"
            '    """返回两数之和。"""\n'
            "    return a + b\n"
        )
        result = review_code_snippet(code, "python")
        self.assertGreaterEqual(result.score, 90)

    def test_javascript_review(self) -> None:
        code = (
            "var total = 0;\n"
            "function sum(list) {\n"
            "  for (var i = 0; i < list.length; i++) {\n"
            "    if (list[i] == null) { continue; }\n"
            "    total = total + list[i];\n"
            "  }\n"
            "  console.log(total);\n"
            "  return total;\n"
            "}\n"
        )
        result = review_code_snippet(code, "javascript")
        issues = " ".join(item.issue for item in result.suggestions)
        self.assertIn("var", issues)
        self.assertIn("==", issues)

    def test_java_review_empty_catch(self) -> None:
        code = (
            "public class Demo {\n"
            "    public void run() {\n"
            "        try {\n"
            '            System.out.println("x");\n'
            "        } catch (Exception e) { }\n"
            "    }\n"
            "}\n"
        )
        result = review_code_snippet(code, "java")
        issues = " ".join(item.issue for item in result.suggestions)
        self.assertIn("catch", issues)
        self.assertIn("System.out", issues)

    def test_empty_input(self) -> None:
        result = review_code_snippet("")
        self.assertEqual(result.score, 0)
        self.assertEqual(result.suggestions, [])

    def test_review_dict_shape(self) -> None:
        payload = review_code_snippet("print('hi')\n", "python").to_dict()
        for key in ("language", "score", "metrics", "suggestions", "summary"):
            self.assertIn(key, payload)


class PromptContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.prompt = build_system_prompt(max_retries=3)

    def test_required_sections(self) -> None:
        for keyword in ("功能说明", "关键点", "运行说明", "代码", "validate_code"):
            self.assertIn(keyword, self.prompt)

    def test_anti_hallucination_rules(self) -> None:
        self.assertIn("反幻觉", self.prompt)
        self.assertIn("静态校验", self.prompt)
        self.assertIn("不要声称", self.prompt.replace("禁止声称", "不要声称"))

    def test_retry_budget_injected(self) -> None:
        self.assertIn("最多重试 3 次", self.prompt)

    def test_language_injection(self) -> None:
        prompt = build_system_prompt(language="java")
        self.assertIn("JAVA", prompt)
        self.assertIn("目标语言", prompt)

    def test_explanation_four_elements(self) -> None:
        self.assertIn("是什么", self.prompt)
        self.assertIn("注意事项", self.prompt)

    def test_user_message_prefix(self) -> None:
        self.assertTrue(build_user_message("写个函数", "java").startswith("（目标语言：java）"))
        self.assertEqual(build_user_message("写个函数", None), "写个函数")
        self.assertEqual(build_user_message("写个函数", "auto"), "写个函数")


if __name__ == "__main__":
    unittest.main()
