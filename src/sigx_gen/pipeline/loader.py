"""Import helpers for modules, metadata, and transform callbacks."""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
import importlib.util
from pathlib import Path
import sys
from types import ModuleType

from sigx.model import TRANSFORM_ATTR, TransformMetadata


class ModuleLoadError(Exception):
    """Raised when every module loading strategy fails."""

    def __init__(self, module_name: str, import_error: Exception, file_error: Exception) -> None:
        """Build a combined module loading error."""
        self.module_name = module_name
        self.import_error = import_error
        self.file_error = file_error
        super().__init__(
            f"Failed to load module '{module_name}'; "
            f"importlib import failed: {_format_exception(import_error)}; "
            f"file fallback failed: {_format_exception(file_error)}"
        )


def load_module(
    module_name: str,
    *,
    module_files: dict[str, Path] | None = None,
) -> ModuleType:
    """Import a Python module in-process.

    Args:
        module_name: Dotted module path.
        module_files: Optional discovered module->file mapping used as fallback.

    Returns:
        Imported module object.

    Note:
        Generation imports project code and should only be used for trusted
        codebases.
    """
    try:
        return import_module(module_name)
    except Exception as import_error:
        if module_files is None or module_name not in module_files:
            raise
        try:
            return _load_module_from_file(module_name, module_files[module_name])
        except Exception as file_error:  # noqa: BLE001
            raise ModuleLoadError(module_name, import_error, file_error) from import_error


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


def load_transform_callable(
    ref: str,
    *,
    module_files: dict[str, Path] | None = None,
) -> Callable[..., object]:
    """Import a transform callback from a dotted reference.

    Args:
        ref: Callback reference in ``module:function`` format.
        module_files: Optional discovered module->file mapping used as fallback.

    Returns:
        Imported callable transform.

    Raises:
        ValueError: If the reference format is invalid.
        AttributeError: If the target object is missing.
        TypeError: If the resolved object is not callable.
    """
    module_name, symbol_name = _parse_transform_ref(ref)
    module = load_module(module_name, module_files=module_files)
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


def _load_module_from_file(module_name: str, file_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not build import spec for module '{module_name}' from '{file_path}'")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _format_exception(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"
