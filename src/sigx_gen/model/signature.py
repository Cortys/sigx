"""Immutable internal signature representation for generator transforms."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ParamKind(StrEnum):
    """Parameter kinds used by ``SignatureIR``."""

    POS_ONLY = "POS_ONLY"
    POS_OR_KW = "POS_OR_KW"
    VAR_POS = "VAR_POS"
    KW_ONLY = "KW_ONLY"
    VAR_KW = "VAR_KW"


@dataclass(frozen=True, slots=True)
class SigParam:
    """A single function parameter in signature IR.

    Attributes:
        name: Parameter name.
        kind: Parameter kind.
        annotation: Source annotation string, if present.
        default: Source default expression string, if present.
    """

    name: str
    kind: ParamKind
    annotation: str | None
    default: str | None


@dataclass(frozen=True, slots=True)
class SignatureIR:
    """Immutable internal representation of a callable signature.

    Attributes:
        type_params: Function-level type parameter declarations.
        params: Ordered parameter list.
        return_annotation: Return annotation string, if present.
        is_async: Whether the function is async.
    """

    params: tuple[SigParam, ...]
    return_annotation: str | None
    is_async: bool = False
    type_params: tuple[str, ...] = ()

    def get_param(self, name: str) -> SigParam | None:
        """Return a parameter by name.

        Args:
            name: Parameter name.

        Returns:
            The matching parameter, or ``None``.
        """
        index = self.index_of(name)
        if index is None:
            return None
        return self.params[index]

    def has_param(self, name: str) -> bool:
        """Check whether a parameter exists.

        Args:
            name: Parameter name.

        Returns:
            ``True`` if present, else ``False``.
        """
        return self.index_of(name) is not None

    def index_of(self, name: str) -> int | None:
        """Return the index of a named parameter.

        Args:
            name: Parameter name.

        Returns:
            Parameter index, or ``None`` if missing.
        """
        for index, param in enumerate(self.params):
            if param.name == name:
                return index
        return None
