from __future__ import annotations

from pathlib import Path
from typing import cast

from sigx_gen.emit.patch_base import StubPatchBackend, apply_patch_plan
from sigx_gen.model.diagnostics import Diagnostic
from sigx_gen.model.plan import ModulePlan, SymbolPlan, TransformPlan


class _FakeBackend:
    def patch_module(self, existing_text: str, _module_plan: ModulePlan) -> tuple[str, tuple[Diagnostic, ...]]:
        return existing_text + "# patched\n", ()


def _plan_for(path: Path) -> TransformPlan:
    return TransformPlan(
        modules=(
            ModulePlan(
                module_name="pkg.mod",
                source_file=Path("src/pkg/mod.py"),
                stub_file=path,
                typing_imports=(),
                module_imports=(),
                symbols=(
                    SymbolPlan(
                        qualname="run",
                        function_name="run",
                        class_name=None,
                        rendered_signatures=("() -> None",),
                    ),
                ),
            ),
        ),
    )


def test_apply_patch_plan_check_mode_reports_mismatch(tmp_path: Path) -> None:
    stub_file = tmp_path / "mod.pyi"
    stub_file.write_text("def run() -> None: ...\n", encoding="utf-8")
    result = apply_patch_plan(
        _plan_for(stub_file),
        backend=cast("StubPatchBackend", _FakeBackend()),
        check=True,
    )

    assert result.mismatches == (stub_file,)
    assert result.written_paths == ()


def test_apply_patch_plan_write_mode_writes_file(tmp_path: Path) -> None:
    stub_file = tmp_path / "mod.pyi"
    stub_file.write_text("def run() -> None: ...\n", encoding="utf-8")
    result = apply_patch_plan(
        _plan_for(stub_file),
        backend=cast("StubPatchBackend", _FakeBackend()),
        check=False,
    )

    assert result.written_paths == (stub_file,)
    assert "# patched" in stub_file.read_text(encoding="utf-8")
