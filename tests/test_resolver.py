from __future__ import annotations

import ast

from sigx_gen.discovery import ImportAlias
from sigx_gen.resolver import resolve_decorator


def _decorator_expr(source: str) -> ast.expr:
    module = ast.parse(source)
    function = module.body[0]
    assert isinstance(function, ast.FunctionDef)
    return function.decorator_list[0]


def test_resolve_from_import_name() -> None:
    expr = _decorator_expr("@dec\ndef f():\n    pass\n")
    resolved, diagnostics = resolve_decorator(
        expr,
        module_name="myproj.jobs",
        imports=(ImportAlias(local_name="dec", resolved_module="x", resolved_attr="dec"),),
    )

    assert diagnostics == ()
    assert resolved is not None
    assert resolved.module_name == "x"
    assert resolved.object_name == "dec"


def test_resolve_from_import_alias() -> None:
    expr = _decorator_expr("@alias\ndef f():\n    pass\n")
    resolved, diagnostics = resolve_decorator(
        expr,
        module_name="myproj.jobs",
        imports=(ImportAlias(local_name="alias", resolved_module="x", resolved_attr="dec"),),
    )

    assert diagnostics == ()
    assert resolved is not None
    assert resolved.module_name == "x"
    assert resolved.object_name == "dec"


def test_resolve_import_module_alias_attribute() -> None:
    expr = _decorator_expr("@pm.dec\ndef f():\n    pass\n")
    resolved, diagnostics = resolve_decorator(
        expr,
        module_name="myproj.jobs",
        imports=(ImportAlias(local_name="pm", resolved_module="pkg.mod", resolved_attr=None),),
    )

    assert diagnostics == ()
    assert resolved is not None
    assert resolved.module_name == "pkg.mod"
    assert resolved.object_name == "dec"


def test_resolve_unresolved_name_falls_back_to_local_module() -> None:
    expr = _decorator_expr("@local_dec\ndef f():\n    pass\n")
    resolved, diagnostics = resolve_decorator(expr, module_name="myproj.jobs", imports=())

    assert diagnostics == ()
    assert resolved is not None
    assert resolved.module_name == "myproj.jobs"
    assert resolved.object_name == "local_dec"


def test_unsupported_expression_emits_diagnostic() -> None:
    expr = _decorator_expr("@registry['dec']\ndef f():\n    pass\n")
    resolved, diagnostics = resolve_decorator(expr, module_name="myproj.jobs", imports=())

    assert resolved is None
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "SX002"
