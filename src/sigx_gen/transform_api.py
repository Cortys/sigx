"""Public callback context API for writing signature transforms."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from sigx_gen.signature_ir import SignatureIR


@dataclass(frozen=True, slots=True)
class TargetInfo:
    """Metadata describing the decorated function target.

    Attributes:
        module_name: Module containing the decorated target.
        qualname: Qualified name of the target.
        function_name: Bare function name.
        class_name: Owning class name if method.
        is_async: Whether target is async.
        is_method: Whether target belongs to a class.
        is_classmethod: Whether target has ``@classmethod`` marker.
        is_staticmethod: Whether target has ``@staticmethod`` marker.
    """

    module_name: str
    qualname: str
    function_name: str
    class_name: str | None
    is_async: bool
    is_method: bool
    is_classmethod: bool
    is_staticmethod: bool


@dataclass(frozen=True, slots=True)
class DecoratorApplication:
    """Resolved plain decorator application info.

    Attributes:
        syntax: Original source syntax.
        resolved_name: Resolved symbol path.
        transform_ref: Transform callback reference.
    """

    syntax: str
    resolved_name: str
    transform_ref: str


@dataclass(frozen=True, slots=True)
class DecoratorFactoryApplication:
    """Resolved decorator factory application info.

    Attributes:
        syntax: Original source syntax.
        resolved_name: Resolved symbol path.
        transform_ref: Transform callback reference.
        arg_exprs: Positional argument source expressions.
        kwarg_exprs: Keyword argument source expressions.
    """

    syntax: str
    resolved_name: str
    transform_ref: str
    arg_exprs: tuple[str, ...]
    kwarg_exprs: dict[str, str]


@dataclass(frozen=True, slots=True)
class BoundArgumentsView:
    """Bound decorator factory arguments exposed to transforms.

    Attributes:
        arguments: Bound argument mapping keyed by parameter name.
    """

    arguments: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class TransformContext:
    """Context provided to plain decorator transforms.

    Attributes:
        original: Current signature before applying this transform.
        target: Decorated function target metadata.
        decorator: Decorator application details.
    """

    original: SignatureIR
    target: TargetInfo
    decorator: DecoratorApplication


@dataclass(frozen=True, slots=True)
class TransformFactoryContext:
    """Context provided to decorator factory transforms.

    Attributes:
        original: Current signature before applying this transform.
        target: Decorated function target metadata.
        decorator: Decorator factory application details.
        bound_factory_args: Evaluated and bound factory arguments.
    """

    original: SignatureIR
    target: TargetInfo
    decorator: DecoratorFactoryApplication
    bound_factory_args: BoundArgumentsView


type PlainTransform = Callable[[TransformContext], SignatureIR]
type FactoryTransform = Callable[[TransformFactoryContext], SignatureIR]
