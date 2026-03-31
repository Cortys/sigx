from __future__ import annotations

from sigx_gen.emit.imports import (
    collect_imported_names,
    collect_missing_module_imports,
)
from sigx_gen.model.signature import ParamKind, SignatureIR, SigParam


def test_collect_imported_names_parses_aliases() -> None:
    imported = collect_imported_names(
        (
            "import pkg.mod as pm",
            "from other import Type as Alias",
        )
    )

    assert imported == {"pm", "Alias"}


def test_collect_missing_module_imports_detects_dotted_roots() -> None:
    signatures = (
        SignatureIR(
            params=(SigParam("x", ParamKind.POS_OR_KW, "pkga.b.C", None),),
            return_annotation="None",
        ),
    )

    missing = collect_missing_module_imports(
        signatures,
        imported_names=set(),
        local_symbol_names={"local"},
    )

    assert missing == ("pkga",)


def test_collect_missing_module_imports_includes_type_param_bounds() -> None:
    signatures = (
        SignatureIR(
            params=(SigParam("x", ParamKind.POS_OR_KW, "T", None),),
            return_annotation="T",
            type_params=("T: pkga.types.Bound = pkga.types.Default",),
        ),
    )

    missing = collect_missing_module_imports(
        signatures,
        imported_names=set(),
        local_symbol_names=set(),
    )

    assert missing == ("pkga",)
