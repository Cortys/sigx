from __future__ import annotations

from sigx_gen.model.signature import ParamKind, SignatureIR, SigParam


def test_has_param() -> None:
    sig = SignatureIR(
        params=(
            SigParam(name="a", kind=ParamKind.POS_OR_KW, annotation="int", default=None),
            SigParam(name="b", kind=ParamKind.KW_ONLY, annotation="str", default='"x"'),
        ),
        return_annotation="None",
    )

    assert sig.has_param("a")
    assert not sig.has_param("missing")


def test_get_param() -> None:
    param = SigParam(name="a", kind=ParamKind.POS_OR_KW, annotation="int", default=None)
    sig = SignatureIR(params=(param,), return_annotation=None)

    assert sig.get_param("a") == param
    assert sig.get_param("missing") is None


def test_index_of() -> None:
    sig = SignatureIR(
        params=(
            SigParam(name="first", kind=ParamKind.POS_OR_KW, annotation=None, default=None),
            SigParam(name="second", kind=ParamKind.POS_OR_KW, annotation=None, default=None),
        ),
        return_annotation=None,
    )

    assert sig.index_of("first") == 0
    assert sig.index_of("second") == 1
    assert sig.index_of("other") is None
