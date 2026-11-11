"""Safe arithmetic calculator tool (no `eval`)."""

from __future__ import annotations

import ast
import math
import operator
from collections.abc import Callable
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool, ToolException

_BIN_OPS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS: dict[type[ast.unaryop], Callable[[Any], Any]] = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS: dict[str, Callable[..., Any]] = {
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
}
_CONSTS = {"pi": math.pi, "e": math.e}
_MAX_POWER = 10_000


def _eval(node: ast.AST) -> Any:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_POWER:
            raise ToolException(f"Exponent too large (max {_MAX_POWER}).")
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
        if node.keywords:
            raise ToolException("Keyword arguments are not supported.")
        return _FUNCS[node.func.id](*[_eval(a) for a in node.args])
    raise ToolException(f"Unsupported expression element: {type(node).__name__}.")


def evaluate(expression: str) -> float | int:
    """Evaluate an arithmetic expression safely."""
    if len(expression) > 500:
        raise ToolException("Expression too long (max 500 characters).")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise ToolException(f"Invalid expression: {e.msg}.") from e
    try:
        result = _eval(tree)
    except ZeroDivisionError as e:
        raise ToolException("Division by zero.") from e
    except (ValueError, OverflowError, TypeError) as e:
        raise ToolException(f"Math error: {e}.") from e
    if not isinstance(result, int | float):
        raise ToolException("Expression did not produce a number.")
    return result


def make_calculator() -> BaseTool:
    """Build the calculator tool."""

    def calculator(expression: str) -> str:
        """Evaluate an arithmetic expression and return the numeric result.

        Supports + - * / // % **, parentheses, constants pi and e, and the functions
        sqrt, log, log10, exp, sin, cos, tan, abs, round, min, max.
        Example: "sqrt(16) * (2 + 3)".
        """
        return str(evaluate(expression))

    return StructuredTool.from_function(
        func=calculator,
        name="builtin__calculator",
        description=calculator.__doc__ or "",
        handle_tool_error=True,
    )
