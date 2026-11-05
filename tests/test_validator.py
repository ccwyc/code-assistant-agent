"""校验器单元测试：覆盖三种语言的「通过 / 不通过 / 自动识别 / 错误定位」。"""

from __future__ import annotations

import unittest

from app.validator import (
    detect_language,
    extract_code_blocks,
    strip_code_fences,
    validate_code_snippet,
)

VALID_PYTHON = '''
from functools import lru_cache


@lru_cache(maxsize=None)
def fib(n: int) -> int:
    """递归求斐波那契数列（带缓存）。"""
    if n < 0:
        raise ValueError("n 必须为非负整数")
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)


if __name__ == "__main__":
    print([fib(i) for i in range(10)])
'''

VALID_JAVASCRIPT = r"""
'use strict';

/**
 * 二分查找，返回下标，找不到返回 -1
 */
function binarySearch(arr, target) {
  let left = 0;
  let right = arr.length - 1;
  while (left <= right) {
    const mid = Math.floor((left + right) / 2);
    if (arr[mid] === target) {
      return mid;
    }
    if (arr[mid] < target) {
      left = mid + 1;
    } else {
      right = mid - 1;
    }
  }
  return -1;
}

const data = [1, 3, 5, 7, 9];
console.log(binarySearch(data, 7));
"""

VALID_JAVA = r"""
package com.example;

import java.util.ArrayList;
import java.util.List;

/**
 * 斐波那契数列示例
 */
public class Fibonacci {

    private static final String NAME = "fib";

    public static long fib(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("n >= 0");
        }
        long a = 0;
        long b = 1;
        for (int i = 2; i <= n; i++) {
            long next = a + b;
            a = b;
            b = next;
        }
        return b;
    }

    public static void main(String[] args) {
        List<Long> values = new ArrayList<>();
        for (int i = 0; i < 10; i++) {
            values.add(fib(i));
        }
        System.out.println(values);
    }
}
"""


class ValidCodeTests(unittest.TestCase):
    def test_python_valid(self) -> None:
        result = validate_code_snippet(VALID_PYTHON)
        self.assertTrue(result.valid, [issue.describe() for issue in result.errors])
        self.assertEqual(result.language, "python")
        self.assertIn("校验通过", result.suggestion)

    def test_javascript_valid(self) -> None:
        result = validate_code_snippet(VALID_JAVASCRIPT)
        self.assertTrue(result.valid, [issue.describe() for issue in result.errors])
        self.assertEqual(result.language, "javascript")

    def test_java_valid(self) -> None:
        result = validate_code_snippet(VALID_JAVA)
        self.assertTrue(result.valid, [issue.describe() for issue in result.errors])
        self.assertEqual(result.language, "java")

    def test_result_shape_matches_prd(self) -> None:
        """PRD 5.6：工具必须返回 {valid, errors, suggestion}。"""
        payload = validate_code_snippet("def f():\n    return 1\n").to_dict()
        for key in ("valid", "errors", "suggestion"):
            self.assertIn(key, payload)
        self.assertIsInstance(payload["valid"], bool)
        self.assertIsInstance(payload["errors"], list)
        self.assertIsInstance(payload["suggestion"], str)


class InvalidCodeTests(unittest.TestCase):
    def test_python_missing_colon_reports_line(self) -> None:
        result = validate_code_snippet("def add(a, b)\n    return a + b\n", "python")
        self.assertFalse(result.valid)
        self.assertEqual(result.errors[0].line, 1)
        self.assertIn("冒号", result.errors[0].hint or "")

    def test_python_indentation_error(self) -> None:
        code = "def f():\nreturn 1\n"
        result = validate_code_snippet(code, "python")
        self.assertFalse(result.valid)
        self.assertEqual(result.errors[0].line, 2)

    def test_python_fullwidth_punctuation(self) -> None:
        code = "def f（x）：\n    return x\n"
        result = validate_code_snippet(code, "python")
        self.assertFalse(result.valid)
        self.assertIn("全角标点", result.errors[0].hint or "")

    def test_javascript_unclosed_brace(self) -> None:
        code = "function greet(name) {\n  console.log(name);\n"
        result = validate_code_snippet(code, "javascript")
        self.assertFalse(result.valid)
        codes = {issue.code for issue in result.errors}
        self.assertIn("unclosed-delimiter", codes)
        self.assertEqual(result.errors[0].line, 1)

    def test_javascript_unterminated_string(self) -> None:
        code = "const msg = 'hello;\nconsole.log(msg);\n"
        result = validate_code_snippet(code, "javascript")
        self.assertFalse(result.valid)
        self.assertIn("unterminated-string", {issue.code for issue in result.errors})

    def test_javascript_missing_expression(self) -> None:
        code = "let total = ;\n"
        result = validate_code_snippet(code, "javascript")
        self.assertFalse(result.valid)

    def test_javascript_control_keyword_needs_parens(self) -> None:
        result = validate_code_snippet("if x > 0 {\n  console.log(1);\n}\n", "javascript")
        self.assertFalse(result.valid)
        self.assertIn("missing-condition-parens", {issue.code for issue in result.errors})

    def test_javascript_for_await_is_valid(self) -> None:
        code = "async function run(items) {\n  for await (const item of items) {\n    console.log(item);\n  }\n}\n"
        result = validate_code_snippet(code, "javascript")
        self.assertTrue(result.valid, [issue.describe() for issue in result.errors])

    def test_javascript_multiline_assignment_is_valid(self) -> None:
        code = "const total =\n  first +\n  second;\nconsole.log(total);\n"
        result = validate_code_snippet(code, "javascript")
        self.assertTrue(result.valid, [issue.describe() for issue in result.errors])

    def test_java_missing_semicolon(self) -> None:
        code = (
            "public class Main {\n"
            "    public static void main(String[] args) {\n"
            '        System.out.println("hi")\n'
            "        return\n"
            "    }\n"
            "}\n"
        )
        result = validate_code_snippet(code, "java")
        self.assertFalse(result.valid)
        messages = " ".join(issue.message for issue in result.errors)
        self.assertIn("分号", messages)

    def test_java_missing_type_declaration(self) -> None:
        result = validate_code_snippet("int x = 1;\n", "java")
        self.assertFalse(result.valid)
        self.assertIn("missing-type-declaration", {issue.code for issue in result.errors})

    def test_empty_code_is_invalid(self) -> None:
        result = validate_code_snippet("   \n")
        self.assertFalse(result.valid)
        self.assertEqual(result.errors[0].code, "empty-code")


class FenceAndDetectionTests(unittest.TestCase):
    def test_extract_code_blocks(self) -> None:
        text = "说明\n```python\nprint(1)\n```\n结束\n```javascript\nconsole.log(2);\n```"
        blocks = extract_code_blocks(text)
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0][0], "python")
        self.assertIn("print(1)", blocks[0][1])

    def test_validates_fenced_answer(self) -> None:
        answer = (
            "### 功能说明\n相加。\n\n### 代码\n```python\ndef add(a: int, b: int) -> int:\n"
            "    return a + b\n```\n\n### 运行说明\npython add.py\n"
        )
        result = validate_code_snippet(answer)
        self.assertTrue(result.valid, [issue.describe() for issue in result.errors])
        self.assertEqual(result.language, "python")

    def test_prefers_matching_fence(self) -> None:
        text = "```python\nx = 1\n```\n```java\npublic class A {}\n```"
        code, language = strip_code_fences(text, "java")
        self.assertEqual(language, "java")
        self.assertIn("public class A", code)

    def test_detect_language(self) -> None:
        self.assertEqual(detect_language(VALID_PYTHON), "python")
        self.assertEqual(detect_language(VALID_JAVASCRIPT), "javascript")
        self.assertEqual(detect_language(VALID_JAVA), "java")

    def test_detect_defaults_to_python(self) -> None:
        self.assertEqual(detect_language("x = 1"), "python")

    def test_explicit_language_overrides_detection(self) -> None:
        result = validate_code_snippet("public class Demo { }", "java")
        self.assertEqual(result.language, "java")
        self.assertTrue(result.valid)


class PythonWarningTests(unittest.TestCase):
    def test_bare_except_and_none_comparison(self) -> None:
        code = (
            "def check(value):\n"
            "    if value == None:\n"
            "        return False\n"
            "    try:\n"
            "        return int(value)\n"
            "    except:\n"
            "        return False\n"
        )
        result = validate_code_snippet(code, "python")
        self.assertTrue(result.valid)
        codes = {issue.code for issue in result.warnings}
        self.assertIn("bare-except", codes)
        self.assertIn("none-comparison", codes)

    def test_mutable_default_warning(self) -> None:
        code = "def add(item, bucket=[]):\n    bucket.append(item)\n    return bucket\n"
        result = validate_code_snippet(code, "python")
        self.assertIn("mutable-default", {issue.code for issue in result.warnings})


if __name__ == "__main__":
    unittest.main()
