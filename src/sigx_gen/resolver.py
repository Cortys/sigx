"""Decorator reference resolution for supported AST forms."""

from __future__ import annotations

import ast
from dataclasses import dataclass

from sigx_gen.diagnostics import Diagnostic, DiagnosticLevel
from sigx_gen.discovery import ImportAlias


@dataclass(frozen=True, slots=True)
class ResolvedDecoratorRef:
    """Resolved module/object reference for a decorator expression.

    Attributes:
        module_name: Module path containing the decorator symbol.
        object_name: Dotted object path within ``module_name``.
        is_call: Whether the source decorator used call syntax.
        display_name: Human-readable resolved expression name.
    """

    module_name: str | None
    object_name: str | None
    is_call: bool
    display_name: str


def resolve_decorator(
    decorator_expr: ast.expr,
    *,
    module_name: str,
    imports: tuple[ImportAlias, ...],
) -> tuple[ResolvedDecoratorRef | None, tuple[Diagnostic, ...]]:
    """Resolve a supported decorator AST expression.

    Args:
        decorator_expr: Raw decorator expression from AST.
        module_name: Current source module name.
        imports: Import alias table for the module.

    Returns:
        A resolved reference or ``None`` plus diagnostics.
    """
    alias_map = {alias.local_name: alias for alias in imports}
    if isinstance(decorator_expr, ast.Call):
        is_call = True
        target_expr: ast.expr = decorator_expr.func
    else:
        is_call = False
        target_expr = decorator_expr

    if isinstance(target_expr, ast.Name):
        alias = alias_map.get(target_expr.id)
        if alias is None:
            return (
                ResolvedDecoratorRef(
                    module_name=module_name,
                    object_name=target_expr.id,
                    is_call=is_call,
                    display_name=target_expr.id,
                ),
                (),
            )

        if alias.resolved_module is None or alias.resolved_attr is None:
            return (
                None,
                (
                    Diagnostic(
                        level=DiagnosticLevel.WARNING,
                        code="SX001",
                        message=f"Could not resolve decorator name: {target_expr.id}",
                        module_name=module_name,
                    ),
                ),
            )

        return (
            ResolvedDecoratorRef(
                module_name=alias.resolved_module,
                object_name=alias.resolved_attr,
                is_call=is_call,
                display_name=target_expr.id,
            ),
            (),
        )

    if isinstance(target_expr, ast.Attribute) and isinstance(target_expr.value, ast.Name):
        base_alias = alias_map.get(target_expr.value.id)
        if base_alias is None or base_alias.resolved_module is None:
            return (
                None,
                (
                    Diagnostic(
                        level=DiagnosticLevel.WARNING,
                        code="SX001",
                        message=f"Could not resolve decorator base: {target_expr.value.id}",
                        module_name=module_name,
                    ),
                ),
            )

        if base_alias.resolved_attr is None:
            object_name = target_expr.attr
        else:
            object_name = f"{base_alias.resolved_attr}.{target_expr.attr}"

        return (
            ResolvedDecoratorRef(
                module_name=base_alias.resolved_module,
                object_name=object_name,
                is_call=is_call,
                display_name=ast.unparse(target_expr),
            ),
            (),
        )

    return (
        None,
        (
            Diagnostic(
                level=DiagnosticLevel.WARNING,
                code="SX002",
                message=f"Unsupported decorator syntax: {ast.unparse(decorator_expr)}",
                module_name=module_name,
            ),
        ),
    )
