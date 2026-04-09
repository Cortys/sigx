"""Stub transform implementation for stacked factory decorators."""

from __future__ import annotations

from typing import cast

from sigx_gen.builder import SignatureBuilder
from sigx_gen.model.transform_api import TransformFactoryContext, TransformResult


def add_kwargs_transform(ctx: TransformFactoryContext) -> TransformResult:
    """Build a signature with keyword-only arguments from factory config."""
    builder = SignatureBuilder.from_signature(ctx.original)
    kwarg_list = cast("list[str]", ctx.bound_factory_args.arguments["kwarg_list"])
    for name in kwarg_list:
        builder.add_kwonly(name, annotation="Any", default="...")
    return builder.build()
