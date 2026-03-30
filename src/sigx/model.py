"""Runtime metadata model for decorator transform markers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TransformKind(StrEnum):
    """Kinds of supported runtime transform markers."""

    DECORATOR = "decorator"
    DECORATOR_FACTORY = "decorator_factory"


@dataclass(frozen=True, slots=True)
class TransformMetadata:
    """Metadata attached to a runtime decorator symbol.

    Attributes:
        kind: The decorator marker kind.
        ref: Dotted callback reference in ``module:function`` format.
        version: Metadata schema version.
    """

    kind: TransformKind
    ref: str
    version: int = 1


TRANSFORM_ATTR = "__sigx_transform__"
