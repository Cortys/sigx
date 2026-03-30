from __future__ import annotations

from pathlib import Path

from sigx_gen.engine import TransformedFunction
from sigx_gen.signature_ir import ParamKind, SignatureIR, SigParam
from sigx_gen.writer import render_module_outputs


def test_render_module_outputs_emits_overloads_for_multiple_signatures(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    out_root = tmp_path / "out"
    source_file = src_root / "pkg" / "jobs.py"

    function = TransformedFunction(
        module_name="pkg.jobs",
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
            SignatureIR(
                params=(
                    SigParam("name", ParamKind.POS_OR_KW, "str", None),
                    SigParam("b", ParamKind.KW_ONLY, "Any", "..."),
                ),
                return_annotation="None",
            ),
        ),
    )

    outputs = render_module_outputs((function,), src_root=src_root, out_root=out_root)
    output_path = out_root / "pkg" / "jobs.pyi"
    assert outputs[output_path] == (
        "from typing import Any, overload\n\n"
        "@overload\n"
        "def run(name: str, *, a: Any = ...) -> None: ...\n"
        "@overload\n"
        "def run(name: str, *, b: Any = ...) -> None: ...\n"
    )


def test_render_module_outputs_emits_method_overloads(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    out_root = tmp_path / "out"
    source_file = src_root / "pkg" / "jobs.py"

    method = TransformedFunction(
        module_name="pkg.jobs",
        file_path=source_file,
        qualname="Worker.run",
        function_name="run",
        class_name="Worker",
        is_method=True,
        signatures=(
            SignatureIR(
                params=(
                    SigParam("self", ParamKind.POS_OR_KW, None, None),
                    SigParam("a", ParamKind.KW_ONLY, "Any", "..."),
                ),
                return_annotation="None",
            ),
            SignatureIR(
                params=(
                    SigParam("self", ParamKind.POS_OR_KW, None, None),
                    SigParam("b", ParamKind.KW_ONLY, "Any", "..."),
                ),
                return_annotation="None",
            ),
        ),
    )

    outputs = render_module_outputs((method,), src_root=src_root, out_root=out_root)
    output_path = out_root / "pkg" / "jobs.pyi"
    assert outputs[output_path] == (
        "from typing import Any, overload\n\n"
        "class Worker:\n"
        "    @overload\n"
        "    def run(self, *, a: Any = ...) -> None: ...\n"
        "    @overload\n"
        "    def run(self, *, b: Any = ...) -> None: ...\n"
    )
