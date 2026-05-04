"""Transform orchestration engine for discovered decorated callables."""

from __future__ import annotations

import ast
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import cast

from sigx.model import TransformKind, TransformMetadata
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
from sigx_gen.pipeline.evaluator import (
    DecoratorEvaluationError,
    evaluate_factory_arguments,
    evaluate_factory_arguments_literal_only,
)
from sigx_gen.pipeline.loader import load_module, load_transform_callable, load_transform_metadata
from sigx_gen.pipeline.resolver import resolve_decorator
from sigx_gen.pipeline.static_markers import (
    StaticMarkerMetadata,
    bind_factory_args_static,
    build_static_marker_index,
    lookup_static_marker,
)

_IGNORED_BUILTIN_DECORATORS = {"classmethod", "staticmethod", "property"}


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


def apply_transforms(
    discovered_functions: tuple[DiscoveredFunction, ...],
    *,
    module_files: dict[str, Path] | None = None,
) -> TransformerResult:
    """Apply registered transforms to discovered functions.

    Args:
        discovered_functions: Functions discovered from source scanning.
        module_files: Optional discovered module->file mapping for import fallback.

    Returns:
        Engine output containing transformed signatures and diagnostics.
    """
    transformed: list[TransformedFunction] = []
    diagnostics: list[Diagnostic] = []
    module_cache: dict[str, ModuleType] = {}
    known_module_files = module_files or {f.module_name: f.file_path for f in discovered_functions}
    static_markers = build_static_marker_index(discovered_functions)

    for function in discovered_functions:
        current_signatures: tuple[SignatureIR, ...] = (extract_signature_from_node(function.node),)
        target = _build_target_info(function)
        applied_any_transform = False

        for decorator_expr in reversed(function.decorators):
            if _is_ignored_builtin_decorator(decorator_expr):
                continue
            did_apply, current_signatures = _apply_decorator_application(
                function=function,
                decorator_expr=decorator_expr,
                target=target,
                current_signatures=current_signatures,
                module_cache=module_cache,
                module_files=known_module_files,
                static_markers=static_markers,
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
    module_files: dict[str, Path],
    static_markers: dict[tuple[str, str], StaticMarkerMetadata],
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

    static_marker = lookup_static_marker(
        static_markers,
        module_name=resolved.module_name,
        object_name=resolved.object_name,
    )

    metadata, decorator_object = _resolve_transform_metadata(
        resolved_module_name=resolved.module_name,
        resolved_object_name=resolved.object_name,
        static_marker=static_marker,
        module_cache=module_cache,
        module_files=module_files,
        function=function,
        diagnostics=diagnostics,
    )
    if metadata is None:
        return False, current_signatures

    try:
        transform_callable = load_transform_callable(metadata.ref, module_files=module_files)
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

    bound_args: BoundArgumentsView | None = None
    argument_eval_failures: list[tuple[str, Exception]] = []
    if callable(decorator_object):
        try:
            decorated_module = _load_cached_module(
                function.module_name,
                module_cache,
                module_files=module_files,
            )
            bound_args = evaluate_factory_arguments(
                decorated_module,
                decorator_expr,
                cast("Callable[..., object]", decorator_object),
            )
        except Exception as exc:  # noqa: BLE001
            argument_eval_failures.append(("Runtime evaluation failed", exc))
            if callable(decorator_object):
                try:
                    bound_args = evaluate_factory_arguments_literal_only(
                        decorator_expr,
                        cast("Callable[..., object]", decorator_object),
                    )
                except DecoratorEvaluationError as literal_exc:
                    argument_eval_failures.append(("Literal fallback failed", literal_exc))
                    bound_args = None

    if bound_args is None and static_marker is not None:
        try:
            bound_args = BoundArgumentsView(
                arguments=bind_factory_args_static(
                    definition=static_marker.definition,
                    decorator_call=decorator_expr,
                )
            )
        except Exception as exc:  # noqa: BLE001
            argument_eval_failures.append(("Static marker fallback failed", exc))

    if bound_args is None:
        diagnostics.append(
            _diagnostic(
                code="SX006",
                message=_fallback_failure_message(
                    "Decorator factory argument evaluation failed",
                    argument_eval_failures,
                ),
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


def _load_cached_module(
    module_name: str,
    cache: dict[str, ModuleType],
    *,
    module_files: dict[str, Path],
) -> ModuleType:
    if module_name not in cache:
        cache[module_name] = load_module(module_name, module_files=module_files)
    return cache[module_name]


def _resolve_transform_metadata(
    *,
    resolved_module_name: str,
    resolved_object_name: str,
    static_marker: StaticMarkerMetadata | None,
    module_cache: dict[str, ModuleType],
    module_files: dict[str, Path],
    function: DiscoveredFunction,
    diagnostics: list[Diagnostic],
) -> tuple[TransformMetadata | None, object | None]:
    runtime_metadata: TransformMetadata | None = None
    decorator_object: object | None = None
    runtime_error: Exception | None = None

    try:
        decorator_module = _load_cached_module(
            resolved_module_name,
            module_cache,
            module_files=module_files,
        )
        decorator_object = _resolve_object_path(decorator_module, resolved_object_name)
        runtime_metadata = load_transform_metadata(decorator_object)
    except Exception as exc:  # noqa: BLE001
        runtime_error = exc

    if runtime_metadata is not None:
        return runtime_metadata, decorator_object
    if static_marker is not None:
        if runtime_error is not None:
            diagnostics.append(
                _diagnostic(
                    code="SX010",
                    message=f"Using static marker fallback after runtime lookup failed: {runtime_error}",
                    function=function,
                    level=DiagnosticLevel.INFO,
                )
            )
        return static_marker.metadata, decorator_object

    return None, decorator_object


def _is_ignored_builtin_decorator(decorator_expr: ast.expr) -> bool:
    candidate = decorator_expr.func if isinstance(decorator_expr, ast.Call) else decorator_expr
    return isinstance(candidate, ast.Name) and candidate.id in _IGNORED_BUILTIN_DECORATORS


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


def _fallback_failure_message(prefix: str, failures: Sequence[tuple[str, Exception]]) -> str:
    if not failures:
        return prefix
    details = "; ".join(f"{label}: {_format_exception(exc)}" for label, exc in failures)
    return f"{prefix}: {details}"


def _format_exception(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"
