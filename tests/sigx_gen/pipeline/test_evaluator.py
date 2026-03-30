from __future__ import annotations

import ast
from types import ModuleType

import pytest

from sigx_gen.pipeline.evaluator import DecoratorEvaluationError, evaluate_factory_arguments


def _decorator_call(source: str) -> ast.Call:
    module = ast.parse(source)
    function = module.body[0]
    assert isinstance(function, ast.FunctionDef)
    decorator = function.decorator_list[0]
    assert isinstance(decorator, ast.Call)
    return decorator


def test_literal_positional_args() -> None:
    module_obj = ModuleType("mod")

    def factory(a: int, b: int) -> object:
        return object()

    bound = evaluate_factory_arguments(module_obj, _decorator_call("@dec(1, 2)\ndef f():\n    pass\n"), factory)
    assert bound.arguments == {"a": 1, "b": 2}


def test_literal_keyword_args() -> None:
    module_obj = ModuleType("mod")

    def factory(*, debug: bool, trace: bool) -> object:
        return object()

    bound = evaluate_factory_arguments(
        module_obj,
        _decorator_call("@dec(debug=True, trace=False)\ndef f():\n    pass\n"),
        factory,
    )
    assert bound.arguments == {"debug": True, "trace": False}


def test_module_constant_lookup() -> None:
    module_obj = ModuleType("mod")
    module_obj.__dict__["FLAG"] = "debug"

    def factory(name: str) -> object:
        return object()

    bound = evaluate_factory_arguments(module_obj, _decorator_call("@dec(FLAG)\ndef f():\n    pass\n"), factory)
    assert bound.arguments == {"name": "debug"}


def test_bound_args_mapping() -> None:
    module_obj = ModuleType("mod")

    def factory(a: int, *, b: int = 3) -> object:
        return object()

    bound = evaluate_factory_arguments(module_obj, _decorator_call("@dec(1, b=2)\ndef f():\n    pass\n"), factory)
    assert set(bound.arguments) == {"a", "b"}


def test_evaluation_failure_raises_expected_error() -> None:
    module_obj = ModuleType("mod")

    def factory(a: int) -> object:
        return object()

    with pytest.raises(DecoratorEvaluationError):
        evaluate_factory_arguments(module_obj, _decorator_call("@dec(MISSING)\ndef f():\n    pass\n"), factory)
