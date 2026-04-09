"""Stub transform implementation for the plain decorator example."""

from __future__ import annotations

from sigx_gen.builder import SignatureBuilder
from sigx_gen.model.transform_api import TransformContext, TransformResult


def add_audit_flag(ctx: TransformContext) -> TransformResult:
    """Build a signature that adds an ``audit_context`` kw-only argument."""
    builder = SignatureBuilder.from_signature(ctx.original)
    builder.add_kwonly("audit_context", annotation="Any", default="...")
    return builder.build()
