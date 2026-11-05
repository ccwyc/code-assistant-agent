"""代码静态校验引擎（不做任何代码执行）。

PRD 5.6 要求：
- Python 用 ``ast.parse`` 做真语法校验；
- JavaScript / Java 用规则校验（括号 / 分号 / 关键字 / 字符串闭合）；
- 输出 ``{"valid": bool, "errors": [...], "suggestion": str}``，供 Agent 决定是否重试。

实现策略：
1. 先剥离 Markdown 代码围栏，避免把 ```` ```python ```` 当作语法错误；
2. Python：``ast.parse`` + 常见错误的中文归因提示；
3. JS / Java：一遍扫描把字符串与注释「抹白」得到 masked 文本（保留字符位置），
   在同一遍扫描中捕获未闭合字符串 / 注释，再在 masked 文本上做括号配对与关键字规则检查，
   这样正则不会误伤字符串内容，报错行号也保持准确。
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any, Literal

SUPPORTED_LANGUAGES: tuple[str, ...] = ("python", "java", "javascript")

_LANGUAGE_ALIASES: dict[str, str] = {
    "py": "python",
    "python3": "python",
    "python2": "python",
    "java8": "java",
    "js": "javascript",
    "node": "javascript",
    "nodejs": "javascript",
    "ts": "javascript",
    "typescript": "javascript",
    "es6": "javascript",
}

_FENCE_RE = re.compile(r"```([A-Za-z0-9_+#.-]*)[ \t]*\r?\n(.*?)```", re.DOTALL)


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class Issue:
    """单条校验问题。``line`` / ``column`` 从 1 开始，未知时为 None。"""

    message: str
    line: int | None = None
    column: int | None = None
    code: str | None = None
    severity: Literal["error", "warning"] = "error"
    hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "column": self.column,
            "message": self.message,
            "code": self.code,
            "severity": self.severity,
            "hint": self.hint,
        }

    def describe(self) -> str:
        """人类可读的一行描述，便于直接回灌给模型。"""
        location = ""
        if self.line is not None:
            location = f"第 {self.line} 行"
            if self.column is not None:
                location += f"第 {self.column} 列"
            location = f"[{location}] "
        return f"{location}{self.message}"


@dataclass(slots=True)
class ValidationResult:
    valid: bool
    language: str
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    suggestion: str = ""
    checker: str = "python-ast"

    @property
    def error_count(self) -> int:
        return len(self.errors)

    def to_dict(self) -> dict[str, Any]:
        """PRD 约定的工具返回结构（另附 language / warnings / checker 便于观测）。"""
        return {
            "valid": self.valid,
            "language": self.language,
            "errors": [issue.to_dict() for issue in self.errors],
            "warnings": [issue.to_dict() for issue in self.warnings],
            "error_count": self.error_count,
            "suggestion": self.suggestion,
            "checker": self.checker,
        }

    def feedback(self) -> str:
        """给模型看的紧凑反馈文本（不含 JSON 噪声）。"""
        lines = [
            f"校验结论：{'通过' if self.valid else '未通过'}（语言：{self.language}，检查器：{self.checker}）"
        ]
        if self.errors:
            lines.append("错误：")
            lines.extend(f"- {issue.describe()}" for issue in self.errors[:10])
        if self.warnings:
            lines.append("提示：")
            lines.extend(f"- {issue.describe()}" for issue in self.warnings[:5])
        if self.suggestion:
            lines.append(f"修复建议：{self.suggestion}")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 语言 / 代码块工具
# --------------------------------------------------------------------------- #
def normalize_language(language: str | None) -> str:
    """归一化语言名；无法识别时回落到 python（PRD 5.1：未指定默认 Python）。"""
    if not language:
        return "python"
    key = str(language).strip().lower().lstrip(".")
    if key in {"", "auto", "text", "unknown", "none"}:
        return "python"
    return _LANGUAGE_ALIASES.get(key, key if key in SUPPORTED_LANGUAGES else "python")


def extract_code_blocks(text: str, language: str | None = None) -> list[tuple[str, str]]:
    """抽取 Markdown 代码围栏中的代码块，返回 ``[(lang, code), ...]``。

    若没有围栏，则把整段文本视为一个语言未知的代码块。
    """
    blocks: list[tuple[str, str]] = []
    for match in _FENCE_RE.finditer(text or ""):
        lang = (match.group(1) or "").strip().lower()
        blocks.append((normalize_language(lang) if lang else "", match.group(2)))
    if blocks:
        return blocks
    if text and text.strip():
        return [("", text)]
    return []


def strip_code_fences(text: str, language: str | None = None) -> tuple[str, str | None]:
    """取出用于校验的代码正文。

    多代码块时优先选择与目标语言匹配的块，其次选择最长的一块（通常是主实现）。
    返回 ``(code, fence_language)``。
    """
    blocks = extract_code_blocks(text, language)
    if not blocks:
        return "", None
    if len(blocks) == 1:
        lang, code = blocks[0]
        return code, lang or None

    target = normalize_language(language) if language else None
    if target:
        matched = [code for lang, code in blocks if lang == target]
        if matched:
            return max(matched, key=len), target
    lang, code = max(blocks, key=lambda item: len(item[1]))
    return code, lang or None


_PYTHON_MARKERS: tuple[tuple[str, float], ...] = (
    (r"^\s*def\s+\w+\s*\(", 3.0),
    (r"^\s*class\s+\w+\s*(?:\([^)]*\))?\s*:", 3.0),
    (r"^\s*from\s+[\w.]+\s+import\s+", 3.0),
    (r"^\s*import\s+[\w.]+\s*$", 2.5),
    (r"\belif\b", 2.5),
    (r"\bself\.", 1.5),
    (r"\bNone\b", 1.2),
    (r"\bprint\s*\(", 0.8),
    (r"^\s*@\w+", 1.0),
    (r"\bf\"", 1.0),
    (r"^\s*if\s+.*:\s*$", 1.2),
)

_JAVA_MARKERS: tuple[tuple[str, float], ...] = (
    (r"\bpublic\s+(?:final\s+|abstract\s+)?(?:class|interface|enum|record)\b", 4.0),
    (r"\bSystem\.out\.print", 3.0),
    (r"\bpublic\s+static\s+void\s+main\b", 4.0),
    (r"^\s*package\s+[\w.]+\s*;", 3.0),
    (r"^\s*import\s+(?:java|javax|com|org)\.", 3.0),
    (r"\bprivate\s+(?:static\s+)?[A-Z]\w*\s+\w+\s*;", 2.0),
    (r"\bString\[\]\s+\w+", 2.0),
    (r"\b(?:ArrayList|HashMap|StringBuilder)\b", 1.5),
    (r"\bnew\s+[A-Z]\w*\s*\(", 1.0),
)

_JS_MARKERS: tuple[tuple[str, float], ...] = (
    (r"\bconst\s+\w+\s*=", 3.0),
    (r"\blet\s+\w+\s*=", 3.0),
    (r"=>", 3.0),
    (r"\bconsole\.(?:log|error|warn)\s*\(", 3.5),
    (r"\bfunction\s*\w*\s*\(", 2.0),
    (r"\bundefined\b", 2.0),
    (r"===|!==", 1.5),
    (r"\b(?:document|window|module\.exports|require)\b", 1.5),
    (r"\b(?:async|await)\s", 1.0),
)


def detect_language(code: str) -> str:
    """基于特征打分做语言识别；全部为 0 时默认 Python。"""
    masked = _mask(code, line_comment=None, block_comments=True).masked
    scores: dict[str, float] = {"python": 0.0, "java": 0.0, "javascript": 0.0}
    for lang, markers in (
        ("python", _PYTHON_MARKERS),
        ("java", _JAVA_MARKERS),
        ("javascript", _JS_MARKERS),
    ):
        for pattern, weight in markers:
            if re.search(pattern, masked, re.MULTILINE):
                scores[lang] += weight

    # 弱特征：python 的行尾冒号 + 不含分号；java 的分号密度
    if re.search(r":\s*$", masked, re.MULTILINE) and ";" not in masked:
        scores["python"] += 1.0
    if masked.count(";") >= 2 and re.search(r"\b(?:public|private|protected)\b", masked):
        scores["java"] += 1.0
    if "{" in masked and "}" in masked and ";" not in masked:
        scores["javascript"] += 0.5

    best = max(scores.items(), key=lambda item: item[1])
    return best[0] if best[1] > 0 else "python"


# --------------------------------------------------------------------------- #
# 掩码扫描：抹白字符串 / 注释，同时捕获未闭合问题
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class _Scan:
    masked: str
    issues: list[Issue]


def _line_col(text: str, index: int) -> tuple[int, int]:
    line = text.count("\n", 0, index) + 1
    last_newline = text.rfind("\n", 0, index)
    column = index - last_newline if last_newline >= 0 else index + 1
    return line, column


def _mask(
    code: str,
    *,
    line_comment: str | None,
    block_comments: bool,
    hash_comments: bool = False,
    backtick_strings: bool = True,
) -> _Scan:
    """把字符串与注释替换为占位符 ``~``（保留换行与字符位置），便于后续规则检查。

    使用非空白占位符而不是空格，是为了避免 ``const s = `x`;`` 这类代码
    在被抹白后出现「= 后面直接跟分号」的假象，从而误报「赋值号右侧缺少表达式」。
    """
    n = len(code)
    out = list(code)
    issues: list[Issue] = []
    placeholder = "~"

    def blank(start: int, end: int) -> None:
        for k in range(start, min(end, n)):
            if out[k] != "\n":
                out[k] = placeholder

    i = 0
    while i < n:
        ch = code[i]
        nxt = code[i + 1] if i + 1 < n else ""

        if line_comment and code.startswith(line_comment, i):
            end = code.find("\n", i)
            end = n if end == -1 else end
            blank(i, end)
            i = end
            continue

        if hash_comments and ch == "#":
            end = code.find("\n", i)
            end = n if end == -1 else end
            blank(i, end)
            i = end
            continue

        if block_comments and ch == "/" and nxt == "*":
            end = code.find("*/", i + 2)
            if end == -1:
                line, column = _line_col(code, i)
                issues.append(
                    Issue(
                        message="块注释 /* ... */ 未闭合",
                        line=line,
                        column=column,
                        code="unterminated-comment",
                        hint="补上 '*/' 或删除注释起始符",
                    )
                )
                blank(i, n)
                break
            blank(i, end + 2)
            i = end + 2
            continue

        if ch in {"'", '"', "`"}:
            if ch == "`" and not backtick_strings:
                i += 1
                continue
            quote = ch
            j = i + 1
            closed = False
            while j < n:
                current = code[j]
                if current == "\\":
                    j += 2
                    continue
                if quote != "`" and current == "\n":
                    break  # 普通字符串不允许跨行
                if current == quote:
                    closed = True
                    j += 1
                    break
                j += 1
            if not closed:
                line, column = _line_col(code, i)
                issues.append(
                    Issue(
                        message=(
                            "字符串字面量未闭合："
                            f"第 {line} 行开始于 {quote} 的字符串在行内没有结束引号"
                        ),
                        line=line,
                        column=column,
                        code="unterminated-string",
                        hint="补全结束引号；若需跨行请使用字符串拼接或模板字符串",
                    )
                )
                end = min(j, n)
            else:
                end = j
            blank(i, end)
            i = end
            continue

        i += 1

    return _Scan("".join(out), issues)


def _check_delimiters(code: str, masked: str) -> list[Issue]:
    """括号配对检查（基于 masked 文本，忽略字符串/注释干扰）。"""
    pairs = {")": "(", "]": "[", "}": "{"}
    names = {"(": "小括号 ()", "[": "中括号 []", "{": "花括号 {}"}
    stack: list[tuple[str, int]] = []
    issues: list[Issue] = []

    for index, ch in enumerate(masked):
        if ch in "([{":
            stack.append((ch, index))
        elif ch in ")]}":
            if not stack:
                line, column = _line_col(code, index)
                issues.append(
                    Issue(
                        message=f"多余的右括号 '{ch}'，没有与之匹配的左括号",
                        line=line,
                        column=column,
                        code="unmatched-closing",
                        hint="删除多余的右括号，或检查是否漏写了对应的左括号",
                    )
                )
                continue
            opener, open_index = stack.pop()
            if opener != pairs[ch]:
                line, column = _line_col(code, index)
                open_line, open_column = _line_col(code, open_index)
                issues.append(
                    Issue(
                        message=(
                            f"括号不匹配：第 {open_line} 行第 {open_column} 列的 "
                            f"'{opener}' 被 '{ch}' 关闭"
                        ),
                        line=line,
                        column=column,
                        code="mismatched-delimiter",
                        hint=f"检查第 {open_line} 行附近的 {names.get(opener, opener)} 是否配对",
                    )
                )

    for opener, index in reversed(stack):
        line, column = _line_col(code, index)
        issues.append(
            Issue(
                message=f"{names.get(opener, opener)} 未闭合：此处 '{opener}' 缺少对应的右括号",
                line=line,
                column=column,
                code="unclosed-delimiter",
                hint="补全右括号；注意方法/类的结尾是否被截断",
            )
        )
    return issues


# --------------------------------------------------------------------------- #
# Python
# --------------------------------------------------------------------------- #
_PYTHON_HINTS: tuple[tuple[str, str], ...] = (
    (r"expected ':'", "if/for/while/def/class/else 等语句块的末尾缺少冒号 ':'"),
    (r"unexpected indent", "缩进不一致：请统一 4 空格缩进，检查是否多缩进了一层"),
    (r"expected an indented block", "语句块（if/def/for/try 等）下方缺少缩进的主体代码"),
    (r"unterminated (?:string|triple-quoted)|EOL while scanning", "字符串缺少结束引号"),
    (
        r"was never closed|does not match opening|closing parenthesis",
        "括号未配对，请检查左右括号是否成对出现",
    ),
    (r"invalid syntax", "存在非法语法，检查该行的运算符、括号、关键字拼写是否正确"),
    (r"invalid character", "出现非法字符：常见原因是中文全角标点（，：；（））或不可见字符"),
    (r"cannot assign to|is an illegal target", "赋值目标非法：'=' 左侧必须是可以赋值的变量/属性"),
    (r"missing parentheses in call", "函数调用缺少括号，例如 print 需要写成 print(...)"),
    (r"unexpected EOF|unexpected end", "代码结尾不完整：缺少括号、冒号或语句块"),
    (r"unknown syntax|invalid decimal literal", "数字/标识符写法非法，检查是否以数字开头的变量名"),
    (r"leading zeros", "数字不能有前导零（如 08），请改为 0o10 或去掉前导零"),
)

_FULLWIDTH_PUNCT = re.compile(r"[，。：；（）【】｛｝“”‘’、！？]")


def _python_hint(message: str) -> str:
    lower = message.lower()
    for pattern, hint in _PYTHON_HINTS:
        if re.search(pattern, lower):
            return hint
    return "根据错误提示修正该行语法"


def _python_warnings(tree: ast.AST) -> list[Issue]:
    """轻量语义提示：不阻塞生成，只用于提升代码质量。"""
    warnings: list[Issue] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            warnings.append(
                Issue(
                    message="使用了裸 except：会吞掉包括 KeyboardInterrupt 在内的所有异常",
                    line=node.lineno,
                    column=node.col_offset + 1,
                    code="bare-except",
                    severity="warning",
                    hint="改为 except Exception as exc: 并记录日志",
                )
            )
        elif isinstance(node, ast.Compare):
            for op, right in zip(node.ops, node.comparators):
                is_none = isinstance(right, ast.Constant) and right.value is None
                if is_none and isinstance(op, (ast.Eq, ast.NotEq)):
                    warnings.append(
                        Issue(
                            message="与 None 比较使用了 ==/!=，应使用 is / is not",
                            line=getattr(node, "lineno", None),
                            column=(getattr(node, "col_offset", 0) + 1),
                            code="none-comparison",
                            severity="warning",
                            hint="None 是单例，使用 'is None' / 'is not None' 更准确",
                        )
                    )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defaults = node.args.defaults + [
                default for default in node.args.kw_defaults if default is not None
            ]
            if any(isinstance(default, (ast.List, ast.Dict, ast.Set)) for default in defaults):
                warnings.append(
                    Issue(
                        message="函数参数使用了可变对象作为默认值（list/dict/set 字面量）",
                        line=node.lineno,
                        column=node.col_offset + 1,
                        code="mutable-default",
                        severity="warning",
                        hint="默认值改为 None，在函数体内初始化（if arg is None: arg = []）",
                    )
                )
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in {"eval", "exec"}:
                warnings.append(
                    Issue(
                        message=f"调用了 {func.id}()，存在代码注入风险",
                        line=node.lineno,
                        column=node.col_offset + 1,
                        code="unsafe-eval",
                        severity="warning",
                        hint="避免 eval/exec；改用 ast.literal_eval 或显式解析",
                    )
                )
    return warnings


def _validate_python(code: str) -> ValidationResult:
    try:
        tree = ast.parse(code, filename="<generated>")
    except SyntaxError as exc:
        message = exc.msg or "语法错误"
        hint = _python_hint(message)
        error_line = ""
        if exc.lineno and exc.lineno <= len(code.splitlines()):
            error_line = code.splitlines()[exc.lineno - 1]
        if _FULLWIDTH_PUNCT.search(error_line or ""):
            hint = "第 %s 行存在中文全角标点（，：；（）等），请替换为英文半角符号" % exc.lineno
            message = f"{message}（该行含全角标点）"
        issue = Issue(
            message=message,
            line=exc.lineno,
            column=exc.offset,
            code=type(exc).__name__.lower(),
            hint=hint,
        )
        suggestion = f"{hint}；请对照第 {exc.lineno} 行修正后重新校验"
        return ValidationResult(
            valid=False,
            language="python",
            errors=[issue],
            suggestion=suggestion,
            checker="python-ast",
        )
    except (ValueError, MemoryError) as exc:  # 空字符 / 超深嵌套等
        return ValidationResult(
            valid=False,
            language="python",
            errors=[Issue(message=f"无法解析代码：{exc}", code="parse-error")],
            suggestion="检查是否包含空字节或过深的嵌套结构",
            checker="python-ast",
        )

    warnings = _python_warnings(tree)
    suggestion = "语法校验通过，可以运行 `python <文件名>.py` 验证"
    if warnings:
        suggestion += f"；另有 {len(warnings)} 条代码质量提示（不阻塞）"
    return ValidationResult(
        valid=True,
        language="python",
        warnings=warnings,
        suggestion=suggestion,
        checker="python-ast",
    )


# --------------------------------------------------------------------------- #
# JavaScript
# --------------------------------------------------------------------------- #
def _next_code_line(lines: list[str], current_index_1_based: int) -> str:
    """返回下一行非空代码（``current_index_1_based`` 为当前行号，从 1 开始）。"""
    for candidate in lines[current_index_1_based:]:
        if candidate.strip():
            return candidate.strip()
    return ""


_JS_CONTROL_KEYWORDS = re.compile(r"^\s*(?:\}\s*)?(?P<kw>if|for|while|switch)\b")


def _validate_javascript(code: str) -> ValidationResult:
    scan = _mask(code, line_comment="//", block_comments=True, backtick_strings=True)
    masked = scan.masked
    errors: list[Issue] = list(scan.issues)
    errors.extend(_check_delimiters(code, masked))

    lines = masked.split("\n")
    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue

        next_line = _next_code_line(lines, line_no)

        # 控制流关键字后必须跟条件括号（`for await (...)` 是合法特例）
        control = _JS_CONTROL_KEYWORDS.match(line)
        if control:
            rest = line[control.end() :].lstrip()
            if not rest.startswith("(") and not rest.startswith("await"):
                errors.append(
                    Issue(
                        message=f"{control.group('kw')} 语句缺少条件括号 '('",
                        line=line_no,
                        column=control.end() + 1,
                        code="missing-condition-parens",
                        hint=f"写成 {control.group('kw')} (条件) {{ ... }}",
                    )
                )

        # function 关键字后必须紧跟函数名或参数列表
        match = re.search(r"\bfunction\b(?!\s*[\w$*])", line)
        if match:
            errors.append(
                Issue(
                    message="function 关键字后缺少函数名或参数列表",
                    line=line_no,
                    column=match.start() + 1,
                    code="function-syntax",
                    hint="写成 function name(...) 或 function(...)",
                )
            )

        # 声明语句缺少变量名（`const` 独占一行属于折行写法，交给下面的规则判断）
        match = re.search(r"\b(?:const|let|var)\s*(?==|;|$)", line)
        if match and not (stripped in {"const", "let", "var"}):
            errors.append(
                Issue(
                    message="声明语句缺少变量名",
                    line=line_no,
                    column=match.start() + 1,
                    code="missing-declaration-name",
                    hint="写成 const name = value;",
                )
            )

        # 赋值右侧为空：`= ;` 一定是错误；`=` 出现在行尾时只有在下一行紧接着
        # 结束符（; } )）时才算缺少表达式，避免误伤合法的折行写法。
        match = re.search(r"(?<![=!<>+\-*/%&|^])=(?!=)[ \t]*(?P<tail>;|$)", line)
        if match:
            at_eol = match.group("tail") == ""
            next_is_terminator = next_line == "" or next_line.startswith((";", "}", ")"))
            if not at_eol or next_is_terminator:
                errors.append(
                    Issue(
                        message="赋值号右侧缺少表达式",
                        line=line_no,
                        column=match.start() + 1,
                        code="missing-expression",
                        hint="补上等号右边的值，例如 const x = 0;",
                    )
                )

    warnings: list[Issue] = []
    if re.search(r"\b(?:var)\s+\w+", masked):
        first = re.search(r"\bvar\s+\w+", masked)
        line_no = masked.count("\n", 0, first.start()) + 1 if first else None
        warnings.append(
            Issue(
                message="使用了 var：存在变量提升与函数级作用域问题",
                line=line_no,
                code="use-var",
                severity="warning",
                hint="优先使用 const，需要重新赋值时用 let",
            )
        )
    if re.search(r"[^=!]==[^=]", masked) and "===" not in masked:
        first = re.search(r"[^=!]==[^=]", masked)
        line_no = masked.count("\n", 0, first.start()) + 1 if first else None
        warnings.append(
            Issue(
                message="使用了宽松相等 ==，可能触发隐式类型转换",
                line=line_no,
                code="loose-equality",
                severity="warning",
                hint="改用严格相等 === / !==",
            )
        )

    errors = _dedupe(errors)
    suggestion = (
        "语法结构检查通过；建议用 `node --check <文件名>.js` 做最终确认"
        if not errors
        else _build_suggestion(errors, "javascript")
    )
    return ValidationResult(
        valid=not errors,
        language="javascript",
        errors=errors,
        warnings=warnings,
        suggestion=suggestion,
        checker="js-rules",
    )


# --------------------------------------------------------------------------- #
# Java
# --------------------------------------------------------------------------- #
_JAVA_CONTROL = re.compile(
    r"^\s*(?:\}\s*)?(?:if|for|while|switch|catch|synchronized|try|else|do)\b"
)
# 行尾是这些符号时，说明语句还没写完（续行）
_JAVA_CONTINUATION_ENDINGS = (
    "(",
    ",",
    "+",
    "-",
    "*",
    "/",
    "%",
    "&",
    "|",
    "^",
    "?",
    ":",
    "=",
    ".",
    "[",
    "{",
    "&&",
    "||",
    "->",
)
# 行首是这些符号时，说明上一行的语句还没写完
_JAVA_CONTINUATION_STARTS = (".", "+", "-", "*", "/", "%", "&", "|", "^", "?", ":", ",", "->")


def _is_java_continuation(stripped: str, next_line: str) -> bool:
    """判断当前行是否只是折行的一部分（避免误报「缺少分号」）。"""
    if stripped.endswith(_JAVA_CONTINUATION_ENDINGS):
        return True
    if next_line.startswith(_JAVA_CONTINUATION_STARTS):
        return True
    if next_line.startswith((")", "]", "}")) and not stripped.endswith("{"):
        return True
    return False


def _validate_java(code: str) -> ValidationResult:
    scan = _mask(code, line_comment="//", block_comments=True, backtick_strings=False)
    masked = scan.masked
    errors: list[Issue] = list(scan.issues)
    errors.extend(_check_delimiters(code, masked))

    if not re.search(r"\b(?:class|interface|enum|record)\s+\w+", masked):
        errors.append(
            Issue(
                message="未找到类/接口/枚举/record 声明",
                line=1,
                column=1,
                code="missing-type-declaration",
                hint="Java 代码必须包含至少一个类型声明，如 public class Main { ... }",
            )
        )
    else:
        name = re.search(r"\b(?:public\s+)?(?:final\s+|abstract\s+)?(?:class|record)\s+(\w+)", masked)
        if name and not re.search(
            r"\b(?:public\s+)?(?:final\s+|abstract\s+)?(?:class|record)\s+\w+\s*"
            r"(?:\([^)]*\))?\s*(?:extends[^{]*|implements[^{]*)?\{",
            masked,
        ):
            errors.append(
                Issue(
                    message="类声明后缺少起始花括号 '{'",
                    line=masked.count("\n", 0, name.start()) + 1,
                    column=1,
                    code="missing-class-body",
                    hint="类名后需要 '{' 开始类体，并以 '}' 结束",
                )
            )

    lines = masked.split("\n")
    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue

        next_line = _next_code_line(lines, line_no)

        # import / package 必须以分号结束
        if re.match(r"^(?:import|package)\b", stripped) and not stripped.endswith(";"):
            errors.append(
                Issue(
                    message="import/package 语句缺少分号 ';'",
                    line=line_no,
                    column=len(line.rstrip()) + 1,
                    code="missing-semicolon",
                    hint="在语句末尾补上 ';'",
                )
            )
            continue

        # 语句被折行（下一行以 . 开头 / 当前行以运算符结尾）时不做分号推断
        if _is_java_continuation(stripped, next_line):
            continue

        # return 语句必须以分号结束
        if re.match(r"^return\b", stripped) and not stripped.endswith(";"):
            errors.append(
                Issue(
                    message="return 语句缺少分号 ';'",
                    line=line_no,
                    column=len(line.rstrip()) + 1,
                    code="missing-semicolon",
                    hint="在语句末尾补上 ';'",
                )
            )
            continue

        # 以 ')' 结尾的语句（方法调用）：排除控制流与方法声明
        if stripped.endswith(")") and not _JAVA_CONTROL.match(stripped):
            is_method_decl = next_line.startswith("{") or bool(
                re.search(
                    r"\b(?:void|int|long|double|float|boolean|char|byte|short|String|var)\s+\w+\s*\($",
                    stripped,
                )
            )
            is_annotation_or_record = stripped.startswith("@") or bool(re.search(r"\bthrows\b", stripped))
            has_assignment = bool(re.search(r"(?<![=!<>])=(?!=)", stripped))
            if not is_method_decl and not is_annotation_or_record and not has_assignment:
                errors.append(
                    Issue(
                        message="语句缺少分号 ';'（以 ')' 结尾的调用语句需要以 ';' 结束）",
                        line=line_no,
                        column=len(line.rstrip()) + 1,
                        code="missing-semicolon",
                        hint="在语句末尾补上 ';'",
                    )
                )

        # 赋值语句必须以分号结尾（排除 for 循环头部与续行）
        elif re.search(r"(?<![=!<>+\-*/%&|^])=(?!=)", stripped) and not stripped.endswith(";"):
            if not _JAVA_CONTROL.match(stripped):
                errors.append(
                    Issue(
                        message="赋值语句缺少分号 ';'",
                        line=line_no,
                        column=len(line.rstrip()) + 1,
                        code="missing-semicolon",
                        hint="在语句末尾补上 ';'",
                    )
                )

    errors = _dedupe(errors)
    suggestion = (
        "语法结构检查通过；建议用 `javac <文件名>.java` 做最终编译确认"
        if not errors
        else _build_suggestion(errors, "java")
    )
    return ValidationResult(
        valid=not errors,
        language="java",
        errors=errors,
        warnings=[],
        suggestion=suggestion,
        checker="java-rules",
    )


# --------------------------------------------------------------------------- #
# 汇总
# --------------------------------------------------------------------------- #
def _dedupe(issues: list[Issue]) -> list[Issue]:
    seen: set[tuple[int | None, str]] = set()
    unique: list[Issue] = []
    for issue in issues:
        key = (issue.line, issue.message[:40])
        if key in seen:
            continue
        seen.add(key)
        unique.append(issue)
    unique.sort(key=lambda item: (item.line or 0, item.column or 0))
    return unique


def _build_suggestion(errors: list[Issue], language: str) -> str:
    hints: list[str] = []
    for issue in errors:
        if issue.hint and issue.hint not in hints:
            hints.append(issue.hint)
    if not hints:
        hints.append(f"根据错误列表逐条修正后重新校验（{language}）")
    head = "；".join(hints[:3])
    tail = "" if len(errors) <= 1 else f"（共 {len(errors)} 个问题，请先修第 1 个再复查）"
    return f"{head}{tail}"


def validate_code_snippet(code: str, language: str | None = None) -> ValidationResult:
    """校验一段代码。``language`` 为 None/auto 时自动识别。"""
    raw = (code or "").strip()
    if not raw:
        return ValidationResult(
            valid=False,
            language=normalize_language(language),
            errors=[Issue(message="代码为空：没有可校验的内容", code="empty-code")],
            suggestion="请提供需要校验的代码片段",
            checker="none",
        )

    body, fence_language = strip_code_fences(raw, language)
    if not body.strip():
        return ValidationResult(
            valid=False,
            language=normalize_language(language),
            errors=[Issue(message="代码块为空：仅有 Markdown 围栏而没有代码", code="empty-code")],
            suggestion="请提供需要校验的代码片段",
            checker="none",
        )

    resolved = (
        normalize_language(language)
        if language and str(language).strip().lower() not in {"", "auto"}
        else (fence_language or detect_language(body))
    )
    resolved = normalize_language(resolved)

    if resolved == "python":
        return _validate_python(body)
    if resolved == "javascript":
        return _validate_javascript(body)
    if resolved == "java":
        return _validate_java(body)

    # 理论上不可达，作为扩展语言的兜底
    return ValidationResult(
        valid=False,
        language=resolved,
        errors=[Issue(message=f"暂不支持校验语言：{resolved}", code="unsupported-language")],
        suggestion="目前支持 Python / Java / JavaScript，请指定其中之一",
        checker="none",
    )
