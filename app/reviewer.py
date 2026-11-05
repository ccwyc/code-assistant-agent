"""代码质量评审（对应 PRD 5.4「代码优化」与 5.7「反幻觉」）。

校验器只回答「能不能跑」，评审器回答「写得好不好」：从可读性、性能、健壮性
三个维度给出「为什么改、改了什么」，作为 ``review_code`` 工具的实现。
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any

from app.validator import detect_language, normalize_language, strip_code_fences

@dataclass(slots=True)
class Suggestion:
    dimension: str
    issue: str
    why: str
    how: str
    line: int | None = None
    severity: str = "minor"  # minor / major

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "line": self.line,
            "issue": self.issue,
            "why": self.why,
            "how": self.how,
            "severity": self.severity,
        }


@dataclass(slots=True)
class ReviewResult:
    language: str
    score: int
    metrics: dict[str, Any] = field(default_factory=dict)
    suggestions: list[Suggestion] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if not self.suggestions:
            return "未发现明显可优化项，代码质量良好。"
        majors = sum(1 for item in self.suggestions if item.severity == "major")
        return (
            f"共 {len(self.suggestions)} 条优化建议（其中 {majors} 条建议优先处理），"
            f"综合评分 {self.score}/100。"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "score": self.score,
            "summary": self.summary,
            "metrics": self.metrics,
            "suggestions": [item.to_dict() for item in self.suggestions],
        }

    def feedback(self) -> str:
        """给模型阅读的紧凑文本（便于它直接组织「优化项逐条列出」的回答）。"""
        lines = [f"语言：{self.language}｜评分：{self.score}/100｜{self.summary}"]
        for index, item in enumerate(self.suggestions[:12], start=1):
            location = f"第 {item.line} 行" if item.line else "全局"
            lines.append(
                f"{index}. [{item.dimension}] {location}：{item.issue}\n"
                f"   为什么：{item.why}\n   怎么改：{item.how}"
            )
        return "\n".join(lines)


_LONG_LINE = 100
_DEEP_NESTING = 4


def _comment_line_count(code: str, language: str) -> int:
    if language == "python":
        return sum(1 for line in code.splitlines() if line.strip().startswith("#"))
    return sum(1 for line in code.splitlines() if line.strip().startswith(("//", "/*", "*")))


def _shared_checks(code: str, language: str) -> tuple[list[Suggestion], dict[str, Any]]:
    """与语言无关的检查：行长、TODO、空白行、魔法数字。"""
    suggestions: list[Suggestion] = []
    lines = code.splitlines()
    metrics: dict[str, Any] = {
        "total_lines": len(lines),
        "blank_lines": sum(1 for line in lines if not line.strip()),
        "comment_lines": _comment_line_count(code, language),
        "max_line_length": max((len(line) for line in lines), default=0),
    }

    for index, line in enumerate(lines, start=1):
        if len(line) > _LONG_LINE:
            suggestions.append(
                Suggestion(
                    dimension="可读性",
                    line=index,
                    issue=f"单行长度 {len(line)} 字符，超过 {_LONG_LINE} 字符建议阈值",
                    why="过长的行在代码评审 / 小屏幕下需要横向滚动，容易漏看逻辑分支",
                    how="按运算符或参数换行，保持每个参数 / 条件占一行",
                    severity="minor",
                )
            )
            break

    todo = [
        (index, line.strip())
        for index, line in enumerate(lines, start=1)
        if re.search(r"\b(TODO|FIXME|XXX|HACK)\b", line)
    ]
    if todo:
        line_no, text = todo[0]
        suggestions.append(
            Suggestion(
                dimension="健壮性",
                line=line_no,
                issue=f"存在未完成的标记：{text[:40]}",
                why="TODO/FIXME 意味着未实现的边界处理，上线后容易变成隐藏 bug",
                how="补齐实现或改用 issue 跟踪，并在交付说明中显式标注",
                severity="major",
            )
        )

    if metrics["blank_lines"] == 0 and metrics["total_lines"] > 25:
        suggestions.append(
            Suggestion(
                dimension="可读性",
                issue="代码块之间没有空行分隔",
                why="紧凑的长代码块难以快速定位函数 / 逻辑段边界",
                how="在函数之间、逻辑段落之间插入一个空行",
                severity="minor",
            )
        )
    return suggestions, metrics


def _review_python(code: str) -> tuple[list[Suggestion], dict[str, Any]]:
    suggestions, metrics = _shared_checks(code, "python")
    try:
        tree = ast.parse(code)
    except SyntaxError:
        metrics.update({"functions": 0, "classes": 0, "max_nesting": 0, "avg_function_lines": 0})
        return suggestions, metrics

    functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    lengths = [
        (getattr(node, "end_lineno", node.lineno) - node.lineno + 1) for node in functions
    ]

    metrics.update(
        {
            "functions": len(functions),
            "classes": len(classes),
            "avg_function_lines": round(sum(lengths) / len(lengths), 1) if lengths else 0,
            "max_nesting": _python_max_nesting(tree),
            "has_module_docstring": bool(ast.get_docstring(tree)),
        }
    )

    for node in functions:
        length = getattr(node, "end_lineno", node.lineno) - node.lineno + 1
        if length > 50:
            suggestions.append(
                Suggestion(
                    dimension="可读性",
                    line=node.lineno,
                    issue=f"函数 {node.name} 长达 {length} 行",
                    why="长函数承担了过多职责，单测与复用成本高",
                    how="按步骤拆分为多个小函数，每个函数只做一件事",
                    severity="major",
                )
            )
        if not ast.get_docstring(node) and length > 8:
            suggestions.append(
                Suggestion(
                    dimension="可读性",
                    line=node.lineno,
                    issue=f"函数 {node.name} 缺少 docstring",
                    why="没有注释的函数需要读者反向推导入参含义与副作用",
                    how="补一行 docstring：说明作用、参数、返回值与异常",
                    severity="minor",
                )
            )
        args = node.args.args
        typed = [arg for arg in args if arg.annotation is not None]
        if args and len(typed) < len(args) and node.name != "__init__":
            suggestions.append(
                Suggestion(
                    dimension="健壮性",
                    line=node.lineno,
                    issue=f"函数 {node.name} 缺少完整的类型注解",
                    why="类型注解让调用方与静态检查工具更早发现传参错误",
                    how="为参数与返回值补充类型注解（Python 3.11+ 可直接用内置泛型）",
                    severity="minor",
                )
            )

    if metrics["max_nesting"] > _DEEP_NESTING:
        suggestions.append(
            Suggestion(
                dimension="可读性",
                issue=f"存在嵌套深度 {metrics['max_nesting']} 层的代码块",
                why="深层嵌套会显著增加认知负担，且容易漏掉分支",
                how="使用提前返回（early return）或提取子函数降低层级",
                severity="major",
            )
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.For):
            body_text = ast.dump(node)
            if "attr='append'" in body_text:
                suggestions.append(
                    Suggestion(
                        dimension="性能",
                        line=node.lineno,
                        issue="使用 for 循环逐个 append 构建列表",
                        why="Python 层的循环 + 方法调用开销远高于列表推导 / 生成器",
                        how="改写为列表推导式，或用生成器表达式喂给需要可迭代对象的函数",
                        severity="minor",
                    )
                )

    if re.search(r"\bprint\s*\(", code) and "__main__" not in code:
        suggestions.append(
            Suggestion(
                dimension="可读性",
                issue="业务代码中直接使用 print 输出",
                why="print 无法分级过滤，生产环境会污染标准输出",
                how="改用 logging.getLogger(__name__) 并按级别输出",
                severity="minor",
            )
        )
    if re.search(r"\btime\.sleep\s*\(", code):
        suggestions.append(
            Suggestion(
                dimension="性能",
                line=next(
                    (i for i, line in enumerate(code.splitlines(), 1) if "time.sleep(" in line),
                    None,
                ),
                issue="使用 time.sleep 做等待",
                why="阻塞式睡眠会占满线程，无法并发处理其它请求",
                how="改用事件驱动 / 异步等待（asyncio.sleep、条件变量或回调）",
                severity="minor",
            )
        )
    if re.search(r"\bopen\s*\(", code) and "with open" not in code:
        suggestions.append(
            Suggestion(
                dimension="健壮性",
                issue="打开文件未使用 with 上下文管理器",
                why="异常路径下文件句柄可能无法释放，导致句柄泄漏",
                how="使用 with open(...) as fh: 自动关闭文件",
                severity="major",
            )
        )
    return suggestions, metrics


def _python_max_nesting(tree: ast.AST) -> int:
    """粗略计算最大嵌套深度（只统计控制流语句）。"""
    control = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.AsyncFor, ast.AsyncWith)

    def depth(node: ast.AST, current: int = 0) -> int:
        best = current
        for child in ast.iter_child_nodes(node):
            if isinstance(child, control):
                best = max(best, depth(child, current + 1))
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                best = max(best, depth(child, current))
            else:
                best = max(best, depth(child, current))
        return best

    return depth(tree)


def _review_java(code: str) -> tuple[list[Suggestion], dict[str, Any]]:
    suggestions, metrics = _shared_checks(code, "java")
    metrics.update(
        {
            "classes": len(re.findall(r"\b(?:class|interface|enum|record)\s+\w+", code)),
            "methods": len(
                re.findall(
                    r"\b(?:public|private|protected|static|final|synchronized|abstract|native|\s)+"
                    r"[\w<>\[\],.]+\s+\w+\s*\([^;]*?\)\s*(?:throws [\w, ]+)?\{",
                    code,
                )
            ),
            "has_package": bool(re.search(r"^\s*package\s+", code, re.MULTILINE)),
        }
    )

    if re.search(r"\bcatch\s*\([^)]*\)\s*\{\s*\}", code):
        line = next(
            (
                index
                for index, raw in enumerate(code.splitlines(), 1)
                if re.search(r"\bcatch\s*\([^)]*\)\s*\{\s*\}", raw)
            ),
            None,
        )
        suggestions.append(
            Suggestion(
                dimension="健壮性",
                line=line,
                issue="存在空的 catch 块",
                why="吞掉异常会让故障静默发生，排查时无任何线索",
                how="至少记录日志（logger.error / e.printStackTrace）并说明降级策略",
                severity="major",
            )
        )
    if re.search(r"\bSystem\.(?:out|err)\.print", code):
        suggestions.append(
            Suggestion(
                dimension="可读性",
                issue="使用 System.out.println 输出日志",
                why="标准输出无级别、无时间戳，生产环境难以过滤和归档",
                how="改用 SLF4J / Log4j2 的 logger.info / logger.error",
                severity="minor",
            )
        )
    if re.search(r"\b(?:ArrayList|HashMap|StringBuilder)\s*\(\s*\)", code):
        suggestions.append(
            Suggestion(
                dimension="性能",
                issue="集合初始化时未预估容量",
                why="默认容量不足时会触发多次扩容与数组拷贝",
                how="已知数据规模时传入初始容量，如 new ArrayList<>(list.size())",
                severity="minor",
            )
        )
    if re.search(r"\bwhile\s*\(\s*true\s*\)", code):
        suggestions.append(
            Suggestion(
                dimension="健壮性",
                line=next(
                    (i for i, line in enumerate(code.splitlines(), 1) if "while (true)" in line or "while(true)" in line),
                    None,
                ),
                issue="使用 while (true) 死循环",
                why="缺少退出条件时线程无法结束，容易造成资源泄漏",
                how="改用带条件的循环，或显式定义退出标志 / break 条件",
                severity="minor",
            )
        )
    return suggestions, metrics


def _review_javascript(code: str) -> tuple[list[Suggestion], dict[str, Any]]:
    suggestions, metrics = _shared_checks(code, "javascript")
    metrics.update(
        {
            "functions": len(re.findall(r"\bfunction\b|=>", code)),
            "classes": len(re.findall(r"\bclass\s+\w+", code)),
            "has_strict_mode": "use strict" in code or "module.exports" in code,
        }
    )

    if re.search(r"\bvar\s+\w+", code):
        suggestions.append(
            Suggestion(
                dimension="健壮性",
                line=next(
                    (i for i, line in enumerate(code.splitlines(), 1) if re.search(r"\bvar\s+\w+", line)),
                    None,
                ),
                issue="使用 var 声明变量",
                why="var 是函数级作用域且会变量提升，容易造成意外的变量覆盖",
                how="改用 const（首选）或 let",
                severity="major",
            )
        )
    if re.search(r"[^=!<>]==[^=]", code):
        suggestions.append(
            Suggestion(
                dimension="健壮性",
                line=next(
                    (
                        i
                        for i, line in enumerate(code.splitlines(), 1)
                        if re.search(r"[^=!<>]==[^=]", line)
                    ),
                    None,
                ),
                issue="使用宽松相等 ==",
                why="== 会做隐式类型转换（'1' == 1 为 true），容易产生隐蔽逻辑错误",
                how="改用严格相等 === / !==",
                severity="major",
            )
        )
    if re.search(r"console\.(?:log|error|warn)\s*\(", code) and "//" not in code.split("console", 1)[0]:
        suggestions.append(
            Suggestion(
                dimension="可读性",
                issue="代码中保留了 console.log 调试输出",
                why="调试语句会污染生产日志，且可能泄漏敏感数据",
                how="改用统一日志库（winston / pino）或在提交前移除",
                severity="minor",
            )
        )
    if re.search(r"\bcatch\s*\([^)]*\)\s*\{\s*\}", code):
        line = next(
            (
                index
                for index, raw in enumerate(code.splitlines(), 1)
                if re.search(r"\bcatch\s*\([^)]*\)\s*\{\s*\}", raw)
            ),
            None,
        )
        suggestions.append(
            Suggestion(
                dimension="健壮性",
                line=line,
                issue="存在空的 catch 块",
                why="异常被静默吞掉，问题难以定位",
                how="记录日志或向上抛出（throw error），并给出降级处理",
                severity="major",
            )
        )
    if re.search(r"\bfor\s*\([^;]*;[^;]*\.length\s*;", code):
        suggestions.append(
            Suggestion(
                dimension="性能",
                issue="for 循环每次都读取 .length",
                why="虽然引擎会优化，但可读性上不如缓存长度或用 for...of",
                how="改用 for...of / map / filter，或把长度缓存到局部变量",
                severity="minor",
            )
        )
    if re.search(r"\basync\s+function|\basync\s*\(", code) and "try" not in code:
        suggestions.append(
            Suggestion(
                dimension="健壮性",
                issue="异步函数中没有 try/catch",
                why="Promise 拒绝未被捕获会变成 unhandledRejection，进程可能退出",
                how="用 try/catch 包裹 await，或在调用链末端补 .catch()",
                severity="major",
            )
        )
    return suggestions, metrics


def review_code_snippet(code: str, language: str | None = None) -> ReviewResult:
    """从可读性 / 性能 / 健壮性三个维度评审代码。"""
    raw = (code or "").strip()
    if not raw:
        return ReviewResult(language=normalize_language(language), score=0, metrics={}, suggestions=[])

    body, fence_language = strip_code_fences(raw, language)
    resolved = (
        normalize_language(language)
        if language and str(language).strip().lower() not in {"", "auto"}
        else (fence_language or detect_language(body))
    )
    resolved = normalize_language(resolved)

    if resolved == "python":
        suggestions, metrics = _review_python(body)
    elif resolved == "java":
        suggestions, metrics = _review_java(body)
    else:
        suggestions, metrics = _review_javascript(body)

    # 评分：major 扣 12 分，minor 扣 4 分，最低 40 分（0 分留给空输入/不可解析）
    penalty = sum(12 if item.severity == "major" else 4 for item in suggestions)
    score = max(40, 100 - penalty)
    metrics["suggestion_count"] = len(suggestions)

    return ReviewResult(
        language=resolved,
        score=score,
        metrics=metrics,
        suggestions=suggestions,
    )
