"""Import helpers for modules, metadata, and transform callbacks."""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from types import ModuleType

from sigx.model import TRANSFORM_ATTR, TransformMetadata


def load_module(module_name: str) -> ModuleType:
    """Import a Python module in-process.

    Args:
        module_name: Dotted module path.

    Returns:
        Imported module object.

    Note:
        Generation imports project code and should only be used for trusted
        codebases.
    """
    return import_module(module_name)


def load_transform_metadata(obj: object) -> TransformMetadata | None:
    """Read runtime transform metadata from a symbol.

    Args:
        obj: Decorator function or factory object.

    Returns:
        Metadata if present and valid, otherwise ``None``.
    """
    metadata = getattr(obj, TRANSFORM_ATTR, None)
    if isinstance(metadata, TransformMetadata):
        return metadata
    return None


def load_transform_callable(ref: str) -> Callable[..., object]:
    """Import a transform callback from a dotted reference.

    Args:
        ref: Callback reference in ``module:function`` format.

    Returns:
        Imported callable transform.

    Raises:
        ValueError: If the reference format is invalid.
        AttributeError: If the target object is missing.
        TypeError: If the resolved object is not callable.
    """
    module_name, symbol_name = _parse_transform_ref(ref)
    module = import_module(module_name)
    callback = getattr(module, symbol_name)
    if not callable(callback):
        raise TypeError(f"transform reference does not resolve to callable: {ref}")
    return callback


def _parse_transform_ref(ref: str) -> tuple[str, str]:
    if not isinstance(ref, str):
        raise ValueError("transform ref must be a string")
    if ref.count(":") != 1:
        raise ValueError("transform ref must use 'module:function' format")

    module_name, symbol_name = ref.split(":", maxsplit=1)
    if not module_name or not symbol_name or "." in symbol_name:
        raise ValueError("transform ref must use 'module:function' format")
    return module_name, symbol_name
