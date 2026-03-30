"""Runtime marker decorators for sigx."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from sigx.model import TRANSFORM_ATTR, TransformKind, TransformMetadata

F = TypeVar("F")


def stub_transform(ref: str, *, version: int = 1) -> Callable[[F], F]:
    """Mark a plain decorator with transform metadata.

    Args:
        ref: Callback reference in ``module:function`` format.
        version: Metadata schema version.

    Returns:
        A decorator that returns the original object unchanged.

    Raises:
        ValueError: If ``ref`` is empty or ``version`` is invalid.
    """
    _validate_marker_inputs(ref=ref, version=version)

    def _decorate(obj: F) -> F:
        setattr(
            obj,
            TRANSFORM_ATTR,
            TransformMetadata(kind=TransformKind.DECORATOR, ref=ref, version=version),
        )
        return obj

    return _decorate


def stub_transform_factory(ref: str, *, version: int = 1) -> Callable[[F], F]:
    """Mark a decorator factory with transform metadata.

    Args:
        ref: Callback reference in ``module:function`` format.
        version: Metadata schema version.

    Returns:
        A decorator that returns the original object unchanged.

    Raises:
        ValueError: If ``ref`` is empty or ``version`` is invalid.
    """
    _validate_marker_inputs(ref=ref, version=version)

    def _decorate(obj: F) -> F:
        setattr(
            obj,
            TRANSFORM_ATTR,
            TransformMetadata(kind=TransformKind.DECORATOR_FACTORY, ref=ref, version=version),
        )
        return obj

    return _decorate


def _validate_marker_inputs(ref: str, version: int) -> None:
    """Validate runtime marker configuration values.

    Args:
        ref: Callback reference string.
        version: Metadata schema version.

    Raises:
        ValueError: If values are outside supported bounds.
    """
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("ref must be a non-empty string")
    if version < 1:
        raise ValueError("version must be >= 1")
