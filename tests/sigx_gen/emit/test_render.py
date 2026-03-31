from __future__ import annotations

from sigx_gen.emit.render import render_signature
from sigx_gen.model.signature import ParamKind, SignatureIR, SigParam


def test_render_no_kw_only() -> None:
    sig = SignatureIR(
        params=(
            SigParam("x", ParamKind.POS_OR_KW, "int", None),
            SigParam("y", ParamKind.POS_OR_KW, "str", "'a'"),
        ),
        return_annotation="None",
    )

    assert render_signature(sig) == "(x: int, y: str = 'a') -> None"


def test_render_kw_only_with_synthetic_star() -> None:
    sig = SignatureIR(
        params=(
            SigParam("x", ParamKind.POS_OR_KW, "int", None),
            SigParam("debug", ParamKind.KW_ONLY, "Any", "..."),
        ),
        return_annotation="None",
    )

    assert render_signature(sig) == "(x: int, *, debug: Any = ...) -> None"


def test_render_kw_only_with_var_pos() -> None:
    sig = SignatureIR(
        params=(
            SigParam("x", ParamKind.POS_OR_KW, "int", None),
            SigParam("args", ParamKind.VAR_POS, "int", None),
            SigParam("debug", ParamKind.KW_ONLY, "Any", "..."),
        ),
        return_annotation="None",
    )

    assert render_signature(sig) == "(x: int, *args: int, debug: Any = ...) -> None"


def test_render_kw_only_before_kwargs() -> None:
    sig = SignatureIR(
        params=(
            SigParam("x", ParamKind.POS_OR_KW, "int", None),
            SigParam("debug", ParamKind.KW_ONLY, "Any", "..."),
            SigParam("kwargs", ParamKind.VAR_KW, "object", None),
        ),
        return_annotation="None",
    )

    assert render_signature(sig) == "(x: int, *, debug: Any = ..., **kwargs: object) -> None"


def test_render_return_annotation() -> None:
    sig = SignatureIR(params=(SigParam("x", ParamKind.POS_OR_KW, "int", None),), return_annotation="str")
    assert render_signature(sig) == "(x: int) -> str"


def test_render_with_type_params() -> None:
    sig = SignatureIR(
        params=(SigParam("x", ParamKind.POS_OR_KW, "T", None),),
        return_annotation="T",
        type_params=("T: pkg.types.Bound = pkg.types.Default",),
    )

    assert render_signature(sig) == "[T: pkg.types.Bound = pkg.types.Default](x: T) -> T"
