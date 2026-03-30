from __future__ import annotations

import pytest

from sigx_gen.builder import SignatureBuilder
from sigx_gen.signature_ir import ParamKind, SignatureIR, SigParam


def _base_signature(*params: SigParam) -> SignatureIR:
    return SignatureIR(params=params, return_annotation="None")


def test_add_kwonly_without_existing_kwonly() -> None:
    sig = _base_signature(SigParam("name", ParamKind.POS_OR_KW, "str", None))
    builder = SignatureBuilder.from_signature(sig)

    builder.add_kwonly("debug")

    result = builder.build()
    assert [p.name for p in result.params] == ["name", "debug"]
    assert result.params[1].kind == ParamKind.KW_ONLY


def test_add_kwonly_with_existing_kwonly() -> None:
    sig = _base_signature(
        SigParam("name", ParamKind.POS_OR_KW, "str", None),
        SigParam("debug", ParamKind.KW_ONLY, "Any", "..."),
    )
    builder = SignatureBuilder.from_signature(sig)

    builder.add_kwonly("trace")

    result = builder.build()
    assert [p.name for p in result.params] == ["name", "debug", "trace"]


def test_add_kwonly_before_kwargs() -> None:
    sig = _base_signature(
        SigParam("name", ParamKind.POS_OR_KW, "str", None),
        SigParam("extras", ParamKind.VAR_KW, "Any", None),
    )
    builder = SignatureBuilder.from_signature(sig)

    builder.add_kwonly("debug")

    result = builder.build()
    assert [p.name for p in result.params] == ["name", "debug", "extras"]
    assert result.params[2].kind == ParamKind.VAR_KW


def test_add_kwonly_duplicate_errors() -> None:
    sig = _base_signature(SigParam("name", ParamKind.POS_OR_KW, "str", None))
    builder = SignatureBuilder.from_signature(sig)

    with pytest.raises(ValueError, match="already exists"):
        builder.add_kwonly("name")


def test_add_kwonly_if_missing_true() -> None:
    sig = _base_signature(SigParam("name", ParamKind.POS_OR_KW, "str", None))
    builder = SignatureBuilder.from_signature(sig)

    builder.add_kwonly("name", if_missing=True)

    result = builder.build()
    assert [p.name for p in result.params] == ["name"]


def test_rename_success_and_failure() -> None:
    sig = _base_signature(
        SigParam("a", ParamKind.POS_OR_KW, None, None),
        SigParam("b", ParamKind.KW_ONLY, None, None),
    )
    builder = SignatureBuilder.from_signature(sig)

    builder.rename("a", "renamed")
    assert builder.build().params[0].name == "renamed"

    with pytest.raises(ValueError, match="not found"):
        builder.rename("missing", "x")

    with pytest.raises(ValueError, match="already exists"):
        builder.rename("renamed", "b")


def test_remove_success_and_failure() -> None:
    sig = _base_signature(
        SigParam("a", ParamKind.POS_OR_KW, None, None),
        SigParam("args", ParamKind.VAR_POS, None, None),
        SigParam("kwargs", ParamKind.VAR_KW, None, None),
    )
    builder = SignatureBuilder.from_signature(sig)

    builder.remove("a")
    assert [p.name for p in builder.build().params] == ["args", "kwargs"]

    with pytest.raises(ValueError, match="not found"):
        builder.remove("a")

    with pytest.raises(ValueError, match="variadic"):
        builder.remove("args")

    with pytest.raises(ValueError, match="variadic"):
        builder.remove("kwargs")


def test_build_returns_immutable_signature() -> None:
    sig = _base_signature(SigParam("a", ParamKind.POS_OR_KW, None, None))
    result = SignatureBuilder.from_signature(sig).build()

    assert isinstance(result.params, tuple)
    assert result.return_annotation == "None"


def test_build_preserves_type_params() -> None:
    sig = SignatureIR(
        params=(SigParam("x", ParamKind.POS_OR_KW, "T", None),),
        return_annotation="T",
        type_params=("T",),
    )

    result = SignatureBuilder.from_signature(sig).build()

    assert result.type_params == ("T",)
