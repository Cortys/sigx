from __future__ import annotations

from pathlib import Path

from sigx_gen.emit.standalone import render_standalone_outputs
from sigx_gen.model.signature import ParamKind, SignatureIR, SigParam
from sigx_gen.pipeline.discovery import discover_modules
from sigx_gen.pipeline.transformer import TransformedFunction


def test_standalone_backend_renders_module_complete_output(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    pkg = src_root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "mod.py").write_text(
        (
            "VALUE: int = 1\n\n"
            "def run(name: str) -> None:\n"
            "    pass\n\n"
            "def helper(x: int) -> int:\n"
            "    return x\n\n"
            "class Worker:\n"
            "    def ping(self, x: int) -> int:\n"
            "        return x\n"
        ),
        encoding="utf-8",
    )
    modules = discover_modules(src_root)
    source_file = pkg / "mod.py"
    transformed = (
        TransformedFunction(
            module_name="pkg.mod",
            file_path=source_file,
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

    outputs = render_standalone_outputs(modules, transformed, src_root=src_root, out_root=tmp_path / "out")
    output_path = tmp_path / "out" / "pkg" / "mod.pyi"

    assert output_path in outputs
    assert "VALUE: int" in outputs[output_path]
    assert "def helper(x: int) -> int: ..." in outputs[output_path]
    assert "class Worker:" in outputs[output_path]
    assert "def ping(self, x: int) -> int: ..." in outputs[output_path]
    assert "def run(name: str, *, a: Any = ...) -> None: ..." in outputs[output_path]


def test_standalone_backend_skips_modules_without_transforms(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    pkg = src_root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "mod.py").write_text("def run() -> None:\n    pass\n", encoding="utf-8")

    modules = discover_modules(src_root)
    outputs = render_standalone_outputs(modules, (), src_root=src_root, out_root=tmp_path / "out")

    assert outputs == {}


def test_standalone_backend_keeps_type_checking_imports_for_annotations(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    pkg = src_root / "pkg"
    pkg.mkdir(parents=True)
    source_file = pkg / "mod.py"
    source_file.write_text(
        (
            "from typing import TYPE_CHECKING\n\n"
            "if TYPE_CHECKING:\n"
            "    from pkga.types import Model\n"
            "\n"
            "def run[T](x: Model) -> T:\n"
            "    ...\n"
        ),
        encoding="utf-8",
    )

    modules = discover_modules(src_root)
    transformed = (
        TransformedFunction(
            module_name="pkg.mod",
            file_path=source_file,
            qualname="run",
            function_name="run",
            class_name=None,
            is_method=False,
            signatures=(
                SignatureIR(
                    params=(SigParam("x", ParamKind.POS_OR_KW, "Model", None),),
                    return_annotation="T",
                    type_params=("T",),
                ),
            ),
        ),
    )

    outputs = render_standalone_outputs(modules, transformed, src_root=src_root, out_root=tmp_path / "out")
    output_path = tmp_path / "out" / "pkg" / "mod.pyi"

    assert "from pkga.types import Model" in outputs[output_path]
    assert "def run[T](x: Model) -> T: ..." in outputs[output_path]
