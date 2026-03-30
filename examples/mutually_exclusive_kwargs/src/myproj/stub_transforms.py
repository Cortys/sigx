from __future__ import annotations

from sigx_gen.builder import SignatureBuilder
from sigx_gen.transform_api import TransformContext


def either_a_or_b(ctx: TransformContext):
    option_a = SignatureBuilder.from_signature(ctx.original)
    option_a.add_kwonly("a", annotation="Any", default="...")

    option_b = SignatureBuilder.from_signature(ctx.original)
    option_b.add_kwonly("b", annotation="Any", default="...")

    return [option_a.build(), option_b.build()]
