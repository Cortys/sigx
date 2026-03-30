"""Backward-compatible re-exports for transform callback API."""

from sigx_gen.model.transform_api import (
    BoundArgumentsView,
    DecoratorApplication,
    DecoratorFactoryApplication,
    FactoryTransform,
    PlainTransform,
    TargetInfo,
    TransformContext,
    TransformFactoryContext,
    TransformResult,
)

__all__ = [
    "BoundArgumentsView",
    "DecoratorApplication",
    "DecoratorFactoryApplication",
    "FactoryTransform",
    "PlainTransform",
    "TargetInfo",
    "TransformContext",
    "TransformFactoryContext",
    "TransformResult",
]
