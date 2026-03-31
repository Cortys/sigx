"""Static marker extraction and fallback argument binding helpers."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import inspect

from sigx.model import TransformKind, TransformMetadata
from sigx_gen.model.symbols import DiscoveredFunction, ImportAlias


@dataclass(frozen=True, slots=True)
class StaticMarkerMetadata:
    """Marker metadata extracted statically from source AST.

    Attributes:
        metadata: Runtime-equivalent marker metadata.
        definition: Discovered decorator definition function.
    """

    metadata: TransformMetadata
    definition: DiscoveredFunction


def build_static_marker_index(
    discovered_functions: tuple[DiscoveredFunction, ...],
) -> dict[tuple[str, str], StaticMarkerMetadata]:
    """Build static marker lookup table for decorator definitions.

    Args:
        discovered_functions: Discovered functions from the source tree.

    Returns:
        Mapping of ``(module_name, object_name)`` to static marker metadata.
    """
    index: dict[tuple[str, str], StaticMarkerMetadata] = {}
    for function in discovered_functions:
        marker = _extract_marker_from_function(function)
        if marker is None:
            continue
        index[(function.module_name, function.function_name)] = marker
    return index


def lookup_static_marker(
    index: dict[tuple[str, str], StaticMarkerMetadata],
    *,
    module_name: str,
    object_name: str,
) -> StaticMarkerMetadata | None:
    """Lookup static marker metadata for a resolved decorator reference.

    Args:
        index: Static marker index map.
        module_name: Resolved module path.
        object_name: Resolved object path.

    Returns:
        Static marker metadata when available.
    """
    direct = index.get((module_name, object_name))
    if direct is not None:
        return direct

    parts = object_name.split(".")
    if len(parts) < 2:
        return None
    fallback_module = f"{module_name}.{'.'.join(parts[:-1])}"
    fallback_object = parts[-1]
    return index.get((fallback_module, fallback_object))


def bind_factory_args_static(
    *,
    definition: DiscoveredFunction,
    decorator_call: ast.Call,
) -> dict[str, object]:
    """Bind decorator factory call arguments without importing runtime modules.

    Args:
        definition: Discovered decorator factory function definition.
        decorator_call: Decorator call expression from use site.

    Returns:
        Bound argument mapping.

    Raises:
        ValueError: If argument values are non-literal or binding fails.
    """
    signature = _signature_from_function_node(definition.node)
    args = [ast.literal_eval(arg) for arg in decorator_call.args]
    kwargs = {
        keyword.arg: ast.literal_eval(keyword.value) for keyword in decorator_call.keywords if keyword.arg is not None
    }
    if any(keyword.arg is None for keyword in decorator_call.keywords):
        raise ValueError("Decorator factory call does not support **kwargs unpacking in static mode")

    bound = signature.bind(*args, **kwargs)
    return dict(bound.arguments)


def _extract_marker_from_function(function: DiscoveredFunction) -> StaticMarkerMetadata | None:
    alias_map = {alias.local_name: alias for alias in function.imports}
    for decorator_expr in function.decorators:
        marker_kind = _resolve_marker_kind(decorator_expr, alias_map)
        if marker_kind is None:
            continue
        if not isinstance(decorator_expr, ast.Call):
            continue
        marker_ref = _extract_string_argument(decorator_expr, "ref")
        if marker_ref is None:
            continue
        version = _extract_int_keyword(decorator_expr, "version", default=1)
        if version is None:
            continue

        return StaticMarkerMetadata(
            metadata=TransformMetadata(kind=marker_kind, ref=marker_ref, version=version),
            definition=function,
        )
    return None


def _resolve_marker_kind(
    decorator_expr: ast.expr,
    alias_map: dict[str, ImportAlias],
) -> TransformKind | None:
    if not isinstance(decorator_expr, ast.Call):
        return None
    target = decorator_expr.func

    marker_name: str | None = None
    if isinstance(target, ast.Name):
        alias = alias_map.get(target.id)
        if alias is None:
            marker_name = target.id
        else:
            resolved_module = getattr(alias, "resolved_module", None)
            resolved_attr = getattr(alias, "resolved_attr", None)
            if resolved_module == "sigx" and isinstance(resolved_attr, str):
                marker_name = resolved_attr
    elif isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
        alias = alias_map.get(target.value.id)
        if alias is not None and getattr(alias, "resolved_module", None) == "sigx":
            marker_name = target.attr

    if marker_name == "stub_transform":
        return TransformKind.DECORATOR
    if marker_name == "stub_transform_factory":
        return TransformKind.DECORATOR_FACTORY
    return None


def _extract_string_argument(call: ast.Call, keyword_name: str) -> str | None:
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        return call.args[0].value
    for keyword in call.keywords:
        if keyword.arg != keyword_name:
            continue
        if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
            return keyword.value.value
    return None


def _extract_int_keyword(call: ast.Call, keyword_name: str, *, default: int) -> int | None:
    for keyword in call.keywords:
        if keyword.arg != keyword_name:
            continue
        if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, int):
            return keyword.value.value
        return None
    return default


def _signature_from_function_node(node: ast.FunctionDef | ast.AsyncFunctionDef) -> inspect.Signature:
    params: list[inspect.Parameter] = []
    args = node.args

    positional = [*args.posonlyargs, *args.args]
    positional_defaults = args.defaults
    defaults_start = len(positional) - len(positional_defaults)
    for index, arg in enumerate(positional):
        kind = (
            inspect.Parameter.POSITIONAL_ONLY
            if index < len(args.posonlyargs)
            else inspect.Parameter.POSITIONAL_OR_KEYWORD
        )
        default: object = inspect.Parameter.empty
        if index >= defaults_start:
            default = ast.literal_eval(positional_defaults[index - defaults_start])
        params.append(inspect.Parameter(arg.arg, kind, default=default))

    if args.vararg is not None:
        params.append(inspect.Parameter(args.vararg.arg, inspect.Parameter.VAR_POSITIONAL))

    for kwarg, kw_default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        default = inspect.Parameter.empty if kw_default is None else ast.literal_eval(kw_default)
        params.append(inspect.Parameter(kwarg.arg, inspect.Parameter.KEYWORD_ONLY, default=default))

    if args.kwarg is not None:
        params.append(inspect.Parameter(args.kwarg.arg, inspect.Parameter.VAR_KEYWORD))

    return inspect.Signature(params)
