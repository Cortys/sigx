"""Transform orchestration engine for discovered decorated callables."""

from __future__ import annotations

import ast
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import cast

from sigx.model import TransformKind
from sigx_gen.model.diagnostics import Diagnostic, DiagnosticLevel
from sigx_gen.model.signature import SignatureIR
from sigx_gen.model.symbols import DiscoveredFunction
from sigx_gen.model.transform_api import (
    BoundArgumentsView,
    DecoratorApplication,
    DecoratorFactoryApplication,
    TargetInfo,
    TransformContext,
    TransformFactoryContext,
)
from sigx_gen.pipeline.discovery import extract_signature_from_node
from sigx_gen.pipeline.evaluator import DecoratorEvaluationError, evaluate_factory_arguments
from sigx_gen.pipeline.loader import load_module, load_transform_callable, load_transform_metadata
from sigx_gen.pipeline.resolver import resolve_decorator


@dataclass(frozen=True, slots=True)
class TransformedFunction:
    """Function result with its final transformed signature set.

    Attributes:
        module_name: Source module name.
        file_path: Source file path.
        qualname: Function qualname.
        function_name: Function name.
        class_name: Class name for methods.
        is_method: Whether this entry is a method.
        signatures: Final transformed signatures.
    """

    module_name: str
    file_path: Path
    qualname: str
    function_name: str
    class_name: str | None
    is_method: bool
    signatures: tuple[SignatureIR, ...]


@dataclass(frozen=True, slots=True)
class TransformerResult:
    """Aggregate output from transform execution.

    Attributes:
        functions: Successfully transformed function signatures.
        diagnostics: Non-fatal issues collected during processing.
    """

    functions: tuple[TransformedFunction, ...]
    diagnostics: tuple[Diagnostic, ...]


def apply_transforms(discovered_functions: tuple[DiscoveredFunction, ...]) -> TransformerResult:
    """Apply registered transforms to discovered functions.

    Args:
        discovered_functions: Functions discovered from source scanning.

    Returns:
        Engine output containing transformed signatures and diagnostics.
    """
    transformed: list[TransformedFunction] = []
    diagnostics: list[Diagnostic] = []
    module_cache: dict[str, ModuleType] = {}

    for function in discovered_functions:
        current_signatures: tuple[SignatureIR, ...] = (extract_signature_from_node(function.node),)
        target = _build_target_info(function)
        applied_any_transform = False

        for decorator_expr in reversed(function.decorators):
            did_apply, current_signatures = _apply_decorator_application(
                function=function,
                decorator_expr=decorator_expr,
                target=target,
                current_signatures=current_signatures,
                module_cache=module_cache,
                diagnostics=diagnostics,
            )
            applied_any_transform = applied_any_transform or did_apply

        if applied_any_transform:
            transformed.append(
                TransformedFunction(
                    module_name=function.module_name,
                    file_path=function.file_path,
                    qualname=function.qualname,
                    function_name=function.function_name,
                    class_name=function.class_name,
                    is_method=function.is_method,
                    signatures=current_signatures,
                )
            )

    return TransformerResult(functions=tuple(transformed), diagnostics=tuple(diagnostics))


def _apply_decorator_application(  # noqa: PLR0911
    *,
    function: DiscoveredFunction,
    decorator_expr: ast.expr,
    target: TargetInfo,
    current_signatures: tuple[SignatureIR, ...],
    module_cache: dict[str, ModuleType],
    diagnostics: list[Diagnostic],
) -> tuple[bool, tuple[SignatureIR, ...]]:
    resolved, resolver_diagnostics = resolve_decorator(
        decorator_expr,
        module_name=function.module_name,
        imports=function.imports,
    )
    diagnostics.extend(_contextualize(function, resolver_diagnostics))
    if resolved is None:
        return False, current_signatures

    if resolved.module_name is None or resolved.object_name is None:
        diagnostics.append(
            _diagnostic(
                code="SX001",
                message=f"Could not resolve decorator reference: {resolved.display_name}",
                function=function,
                level=DiagnosticLevel.WARNING,
            )
        )
        return False, current_signatures

    try:
        decorator_module = _load_cached_module(resolved.module_name, module_cache)
    except Exception as exc:  # noqa: BLE001
        diagnostics.append(
            _diagnostic(
                code="SX003",
                message=f"Failed to import module '{resolved.module_name}': {exc}",
                function=function,
                level=DiagnosticLevel.ERROR,
            )
        )
        return False, current_signatures

    try:
        decorator_object = _resolve_object_path(decorator_module, resolved.object_name)
    except AttributeError as exc:
        diagnostics.append(
            _diagnostic(
                code="SX001",
                message=f"Failed to resolve decorator object '{resolved.object_name}': {exc}",
                function=function,
                level=DiagnosticLevel.WARNING,
            )
        )
        return False, current_signatures

    metadata = load_transform_metadata(decorator_object)
    if metadata is None:
        return False, current_signatures

    try:
        transform_callable = load_transform_callable(metadata.ref)
    except Exception as exc:  # noqa: BLE001
        diagnostics.append(
            _diagnostic(
                code="SX005",
                message=f"Failed to import transform callback '{metadata.ref}': {exc}",
                function=function,
                level=DiagnosticLevel.ERROR,
            )
        )
        return False, current_signatures

    if metadata.kind == TransformKind.DECORATOR:
        if resolved.is_call:
            diagnostics.append(
                _diagnostic(
                    code="SX007",
                    message="Plain decorator transform cannot be applied from call syntax",
                    function=function,
                    level=DiagnosticLevel.ERROR,
                )
            )
            return False, current_signatures

        maybe_updated = _execute_across_branches(
            signatures=current_signatures,
            apply_to_signature=lambda signature: _execute_plain_transform(
                transform_callable=transform_callable,
                signature=signature,
                target=target,
                syntax=ast.unparse(decorator_expr),
                resolved_name=f"{resolved.module_name}.{resolved.object_name}",
                transform_ref=metadata.ref,
                function=function,
                diagnostics=diagnostics,
            ),
        )
        if maybe_updated is None:
            return False, current_signatures
        return True, maybe_updated

    if not callable(decorator_object):
        diagnostics.append(
            _diagnostic(
                code="SX006",
                message="Resolved decorator factory object is not callable",
                function=function,
                level=DiagnosticLevel.ERROR,
            )
        )
        return False, current_signatures
    if not isinstance(decorator_expr, ast.Call):
        diagnostics.append(
            _diagnostic(
                code="SX006",
                message="Decorator factory marker requires call syntax",
                function=function,
                level=DiagnosticLevel.ERROR,
            )
        )
        return False, current_signatures

    try:
        decorated_module = _load_cached_module(function.module_name, module_cache)
        bound_args = evaluate_factory_arguments(
            decorated_module,
            decorator_expr,
            cast("Callable[..., object]", decorator_object),
        )
    except DecoratorEvaluationError as exc:
        diagnostics.append(
            _diagnostic(
                code="SX006",
                message=f"Decorator factory argument evaluation failed: {exc}",
                function=function,
                level=DiagnosticLevel.ERROR,
            )
        )
        return False, current_signatures
    except Exception as exc:  # noqa: BLE001
        diagnostics.append(
            _diagnostic(
                code="SX003",
                message=f"Failed to import decorated module '{function.module_name}': {exc}",
                function=function,
                level=DiagnosticLevel.ERROR,
            )
        )
        return False, current_signatures

    maybe_updated = _execute_across_branches(
        signatures=current_signatures,
        apply_to_signature=lambda signature: _execute_factory_transform(
            transform_callable=transform_callable,
            signature=signature,
            target=target,
            syntax=ast.unparse(decorator_expr),
            resolved_name=f"{resolved.module_name}.{resolved.object_name}",
            transform_ref=metadata.ref,
            decorator_expr=decorator_expr,
            bound_args=bound_args,
            function=function,
            diagnostics=diagnostics,
        ),
    )
    if maybe_updated is None:
        return False, current_signatures
    return True, maybe_updated


def _execute_across_branches(
    *,
    signatures: tuple[SignatureIR, ...],
    apply_to_signature: Callable[[SignatureIR], tuple[SignatureIR, ...] | None],
) -> tuple[SignatureIR, ...] | None:
    next_signatures: list[SignatureIR] = []
    for signature in signatures:
        maybe_transformed = apply_to_signature(signature)
        if maybe_transformed is None:
            return None
        next_signatures.extend(maybe_transformed)
    return _dedupe_signatures(tuple(next_signatures))


def _execute_plain_transform(
    *,
    transform_callable: Callable[..., object],
    signature: SignatureIR,
    target: TargetInfo,
    syntax: str,
    resolved_name: str,
    transform_ref: str,
    function: DiscoveredFunction,
    diagnostics: list[Diagnostic],
) -> tuple[SignatureIR, ...] | None:
    context = TransformContext(
        original=signature,
        target=target,
        decorator=DecoratorApplication(
            syntax=syntax,
            resolved_name=resolved_name,
            transform_ref=transform_ref,
        ),
    )
    transformed, diagnostic = _invoke_transform(
        transform_callable=transform_callable,
        context=context,
        function=function,
    )
    if diagnostic is not None:
        diagnostics.append(diagnostic)
    return transformed


def _execute_factory_transform(
    *,
    transform_callable: Callable[..., object],
    signature: SignatureIR,
    target: TargetInfo,
    syntax: str,
    resolved_name: str,
    transform_ref: str,
    decorator_expr: ast.Call,
    bound_args: BoundArgumentsView,
    function: DiscoveredFunction,
    diagnostics: list[Diagnostic],
) -> tuple[SignatureIR, ...] | None:
    context = TransformFactoryContext(
        original=signature,
        target=target,
        decorator=DecoratorFactoryApplication(
            syntax=syntax,
            resolved_name=resolved_name,
            transform_ref=transform_ref,
            arg_exprs=tuple(ast.unparse(arg) for arg in decorator_expr.args),
            kwarg_exprs={
                keyword.arg: ast.unparse(keyword.value)
                for keyword in decorator_expr.keywords
                if keyword.arg is not None
            },
        ),
        bound_factory_args=bound_args,
    )
    transformed, diagnostic = _invoke_transform(
        transform_callable=transform_callable,
        context=context,
        function=function,
    )
    if diagnostic is not None:
        diagnostics.append(diagnostic)
    return transformed


def _invoke_transform(
    *,
    transform_callable: Callable[..., object],
    context: TransformContext | TransformFactoryContext,
    function: DiscoveredFunction,
) -> tuple[tuple[SignatureIR, ...] | None, Diagnostic | None]:
    try:
        transformed = transform_callable(context)
    except Exception as exc:  # noqa: BLE001
        return (
            None,
            _diagnostic(
                code="SX007",
                message=f"Transform execution failed: {exc}",
                function=function,
                level=DiagnosticLevel.ERROR,
            ),
        )

    normalized = _normalize_transform_result(transformed)
    if normalized is None:
        return (
            None,
            _diagnostic(
                code="SX008",
                message="Transform returned invalid signature object",
                function=function,
                level=DiagnosticLevel.ERROR,
            ),
        )
    if not normalized:
        return (
            None,
            _diagnostic(
                code="SX008",
                message="Transform returned an empty signature list",
                function=function,
                level=DiagnosticLevel.ERROR,
            ),
        )
    return normalized, None


def _normalize_transform_result(result: object) -> tuple[SignatureIR, ...] | None:
    if isinstance(result, SignatureIR):
        return (result,)
    if not isinstance(result, Sequence):
        return None
    if not all(isinstance(item, SignatureIR) for item in result):
        return None
    return tuple(cast("Sequence[SignatureIR]", result))


def _dedupe_signatures(signatures: tuple[SignatureIR, ...]) -> tuple[SignatureIR, ...]:
    deduped: list[SignatureIR] = []
    seen: set[SignatureIR] = set()
    for signature in signatures:
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append(signature)
    return tuple(deduped)


def _build_target_info(function: DiscoveredFunction) -> TargetInfo:
    return TargetInfo(
        module_name=function.module_name,
        qualname=function.qualname,
        function_name=function.function_name,
        class_name=function.class_name,
        is_async=function.is_async,
        is_method=function.is_method,
        is_classmethod=_has_marker(function.decorators, "classmethod"),
        is_staticmethod=_has_marker(function.decorators, "staticmethod"),
    )


def _has_marker(decorators: tuple[ast.expr, ...], marker: str) -> bool:
    for decorator in decorators:
        candidate = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(candidate, ast.Name) and candidate.id == marker:
            return True
    return False


def _resolve_object_path(module: ModuleType, object_name: str) -> object:
    obj: object = module
    for part in object_name.split("."):
        obj = getattr(obj, part)
    return obj


def _load_cached_module(module_name: str, cache: dict[str, ModuleType]) -> ModuleType:
    if module_name not in cache:
        cache[module_name] = load_module(module_name)
    return cache[module_name]


def _contextualize(function: DiscoveredFunction, diagnostics: tuple[Diagnostic, ...]) -> list[Diagnostic]:
    return [
        Diagnostic(
            level=diagnostic.level,
            code=diagnostic.code,
            message=diagnostic.message,
            module_name=function.module_name,
            qualname=function.qualname,
            file_path=str(function.file_path),
        )
        for diagnostic in diagnostics
    ]


def _diagnostic(
    *,
    code: str,
    message: str,
    function: DiscoveredFunction,
    level: DiagnosticLevel,
) -> Diagnostic:
    return Diagnostic(
        level=level,
        code=code,
        message=message,
        module_name=function.module_name,
        qualname=function.qualname,
        file_path=str(function.file_path),
    )
