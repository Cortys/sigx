from __future__ import annotations

from pathlib import Path

from sigx_gen.model.signature import ParamKind, SignatureIR, SigParam
from sigx_gen.pipeline.discovery import discover_modules
from sigx_gen.pipeline.planner import build_transform_plan
from sigx_gen.pipeline.transformer import TransformedFunction


def test_build_transform_plan_creates_symbol_entries(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    pkg = src_root / "pkg"
    pkg.mkdir(parents=True)
    module_path = pkg / "mod.py"
    module_path.write_text(
        "from pkg.decorators import add\n\n@add\ndef run(name: str) -> None:\n    pass\n",
        encoding="utf-8",
    )

    modules = discover_modules(src_root)
    transformed = (
        TransformedFunction(
            module_name="pkg.mod",
            file_path=module_path,
            qualname="run",
            function_name="run",
            class_name=None,
            is_method=False,
            signatures=(
                SignatureIR(
                    params=(
                        SigParam("name", ParamKind.POS_OR_KW, "str", None),
                        SigParam("a", ParamKind.KW_ONLY, "Any", "..."),
                    ),
                    return_annotation="None",
                ),
            ),
        ),
    )

    plan = build_transform_plan(modules, transformed, src_root=src_root, stub_root=tmp_path / "stubs")

    assert len(plan.modules) == 1
    module_plan = plan.modules[0]
    assert module_plan.module_name == "pkg.mod"
    assert module_plan.stub_file == (tmp_path / "stubs" / "pkg" / "mod.pyi")
    assert module_plan.typing_imports == ("Any",)
    assert module_plan.symbols[0].qualname == "run"


def test_build_transform_plan_synthesizes_literal_typing_import(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    pkg = src_root / "pkg"
    pkg.mkdir(parents=True)
    module_path = pkg / "mod.py"
    module_path.write_text(
        "from pkg.decorators import add\n\n@add\ndef run(kind: str) -> None:\n    pass\n",
        encoding="utf-8",
    )

    modules = discover_modules(src_root)
    transformed = (
        TransformedFunction(
            module_name="pkg.mod",
            file_path=module_path,
            qualname="run",
            function_name="run",
            class_name=None,
            is_method=False,
            signatures=(
                SignatureIR(
                    params=(
                        SigParam(
                            "kind",
                            ParamKind.POS_OR_KW,
                            "Literal['a', 'b'] | type[X] | None",
                            None,
                        ),
                    ),
                    return_annotation="None",
                ),
            ),
        ),
    )

    plan = build_transform_plan(modules, transformed, src_root=src_root, stub_root=tmp_path / "stubs")

    assert len(plan.modules) == 1
    assert plan.modules[0].typing_imports == ("Literal",)
