from __future__ import annotations

from sigx_gen.builder import SignatureBuilder
from sigx_gen.model.transform_api import TransformContext


def add_audit_flag(ctx: TransformContext):
    builder = SignatureBuilder.from_signature(ctx.original)
    builder.add_kwonly("audit_context", annotation="Any", default="...")
    return builder.build()
