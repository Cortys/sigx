"""Decorator factory argument evaluation in module execution context."""

from __future__ import annotations

import ast
from collections.abc import Callable
import inspect
from types import ModuleType

from sigx_gen.model.transform_api import BoundArgumentsView


class DecoratorEvaluationError(Exception):
    """Raised when decorator factory argument evaluation fails."""


def evaluate_factory_arguments(
    module_obj: ModuleType,
    decorator_call: ast.Call,
    factory_callable: Callable[..., object],
) -> BoundArgumentsView:
    """Evaluate and bind decorator factory arguments.

    Args:
        module_obj: Module containing the decorated function.
        decorator_call: Decorator call AST node.
        factory_callable: Decorator factory callable.

    Returns:
        Bound argument view for transform context usage.

    Raises:
        DecoratorEvaluationError: If expression evaluation or argument binding fails.
    """
    globals_dict = vars(module_obj)

    try:
        positional_args = [_eval_expr(expr, globals_dict) for expr in decorator_call.args]
        keyword_args: dict[str, object] = {}
        for keyword in decorator_call.keywords:
            if keyword.arg is None:
                raise DecoratorEvaluationError("Decorator factory call does not support **kwargs unpacking in v0.1")
            keyword_args[keyword.arg] = _eval_expr(keyword.value, globals_dict)

        bound = inspect.signature(factory_callable).bind(*positional_args, **keyword_args)
    except DecoratorEvaluationError:
        raise
    except Exception as exc:
        raise DecoratorEvaluationError(str(exc)) from exc

    return BoundArgumentsView(arguments=dict(bound.arguments))


def _eval_expr(expr: ast.expr, globals_dict: dict[str, object]) -> object:
    compiled = compile(ast.Expression(body=expr), filename="<sigx-eval>", mode="eval")
    return eval(compiled, globals_dict, None)  # noqa: S307
